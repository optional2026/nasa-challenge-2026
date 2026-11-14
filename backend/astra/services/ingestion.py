"""Unified ingestion pipeline.

Manual forms, medical devices, wearables, environmental sensors and the
simulator all pass through `ingest()`: schema validation → identity and
authorization → metric/unit/value validation → timestamp validation →
idempotency → storage with provenance → assessment → alerts → real-time events.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from .. import audit, config, db, units
from ..bus import BUS
from ..schemas import ObservationIn
from ..security import MEDICAL_ROLES, Principal, can_view_astronaut
from . import knowledge

ORDINAL_TYPES = {"ordinal"}


class ItemError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _validate_value(ind: dict, value: Any, unit: str) -> dict:
    """Return storage columns for the value. Raises ItemError."""
    vt = ind["value_type"]
    out: dict[str, Any] = {"value_num": None, "value_text": None, "value_bool": None, "value_json": None}
    if unit not in ind["allowed_units"]:
        raise ItemError([f"unsupported unit '{unit}' for {ind['code']}; allowed: {', '.join(ind['allowed_units'])}"])
    if vt in ("numeric", "ordinal"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ItemError([f"{ind['code']} requires a numeric value"])
        if value != value:  # NaN
            raise ItemError(["value is NaN"])
        if vt == "ordinal" and float(value) != int(value):
            raise ItemError([f"{ind['code']} requires a whole-number level"])
        if ind["canonical_unit"] == "as_reported":  # test-specific units (e.g. kg for grip strength); compared per test only
            canonical = float(value)
        else:
            canonical = units.to_canonical(float(value), unit, ind["canonical_unit"], ind["allowed_units"])
        lo, hi = ind.get("plausible_min"), ind.get("plausible_max")
        if lo is not None and canonical < lo or hi is not None and canonical > hi:
            raise ItemError([f"{ind['code']} value {value} {unit} is outside the plausible input range "
                             f"[{lo}, {hi}] {ind['canonical_unit']} (input validation, not a clinical threshold)"])
        out["value_num"] = round(canonical, 6)
    elif vt == "boolean":
        if not isinstance(value, bool):
            raise ItemError([f"{ind['code']} requires true/false"])
        out["value_bool"] = int(value)
    elif vt == "categorical":
        if not isinstance(value, str) or not value:
            raise ItemError([f"{ind['code']} requires a category code"])
        if ind["code"] == "symptom" and value not in knowledge.symptom_codes():
            raise ItemError([f"unknown symptom code '{value}' (see GET /api/v1/symptoms)"])
        out["value_text"] = value
    elif vt == "structured":
        if not isinstance(value, dict) or not value:
            raise ItemError([f"{ind['code']} requires a structured object"])
        out["value_json"] = db.dumps(value)
        out["value_text"] = str(value.get("summary") or value.get("test") or value.get("finding") or "")[:200]
    else:
        raise ItemError([f"unsupported value type {vt}"])
    return out


def _check_time(measured_at: str) -> str:
    dt = db.parse_iso(measured_at)
    now = db.utcnow()
    if dt > now + timedelta(seconds=config.FUTURE_SKEW_SECONDS):
        raise ItemError([f"measured_at {measured_at} is in the future"])
    if dt < now - timedelta(days=config.MAX_AGE_DAYS):
        raise ItemError([f"measured_at {measured_at} is older than {config.MAX_AGE_DAYS} days"])
    return db.iso(dt)


def _authorize(conn, p: Principal, obs: ObservationIn, ind: dict, device: dict | None) -> None:
    errs = []
    if p.kind == "device":
        if obs.device_id and obs.device_id != p.device_id:
            errs.append("device_id does not match the authenticated device")
        if p.mission_id != obs.mission_id:
            errs.append("device is not registered to this mission")
        if device and device["astronaut_id"] and obs.astronaut_id and device["astronaut_id"] != obs.astronaut_id:
            errs.append("device is assigned to a different astronaut")
    elif p.kind == "user":
        if p.role == "admin":
            errs.append("administrators cannot submit health or environmental measurements")
        elif p.role == "astronaut":
            if ind["subject"] != "environment" and obs.astronaut_id != p.astronaut_id:
                errs.append("astronauts may only submit their own measurements")
            if ind.get("clinician_only"):
                errs.append(f"{ind['code']} must be entered by authorized medical personnel")
            if obs.source_type == "clinician":
                errs.append("source_type 'clinician' requires a medical role")
        elif p.role == "medical_officer":
            if ind["subject"] != "environment" and obs.astronaut_id and not can_view_astronaut(p, obs.astronaut_id):
                errs.append("the Crew Medical Officer may only record measurements for astronauts in their crew")
    if errs:
        raise ItemError(errs)


def _normalize_symptom_items(obs: ObservationIn, obs_id: str) -> list[dict]:
    items = []
    for n, s in enumerate(obs.symptoms, start=1):
        items.append({
            "observation_id": f"{obs_id}-S{n}", "astronaut_id": obs.astronaut_id, "mission_id": obs.mission_id,
            "metric_code": "symptom", "value": s.code, "unit": "category",
            "measured_at": obs.measured_at, "source_type": "manual", "device_id": None,  # symptoms are self-reported
            "quality": "unverified", "location": None, "notes": s.notes,
            "context": {"severity": s.severity, "onset_at": s.onset_at, "related_observation_id": obs_id},
            "synthetic": obs.synthetic,
        })
    return items


def ingest(conn, principal: Principal, raw_items: list[dict], *, batch_id: str | None = None,
           sim_run_id: str | None = None, run_assessment: bool = True, extra_private: bool = False) -> dict:
    """Validate and store observations; run assessment; publish events. Returns TelemetryResult dict."""
    from . import assessment_engine  # local import avoids cycle

    inds = knowledge.indicators()
    accepted: list[dict] = []
    rejected: list[dict] = []
    stored: list[dict] = []
    received_at = db.now_iso()
    queue = [(i, item) for i, item in enumerate(raw_items)]
    devices_seen: set[str] = set()

    with db.transaction(conn):
        while queue:
            index, item = queue.pop(0)
            oid = item.get("observation_id") if isinstance(item, dict) else None
            try:
                if not isinstance(item, dict):
                    raise ItemError(["observation must be a JSON object"])
                try:
                    obs = ObservationIn.model_validate(item)
                except ValidationError as ve:
                    raise ItemError([f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in ve.errors()])
                ind = inds.get(obs.metric_code)
                if ind is None:
                    raise ItemError([f"unknown metric_code '{obs.metric_code}' (see GET /api/v1/indicators)"])
                mission = db.one(conn, "SELECT id FROM missions WHERE id=?", (obs.mission_id,))
                if not mission:
                    raise ItemError([f"unknown mission '{obs.mission_id}'"])
                subject = "astronaut" if obs.astronaut_id else "environment"
                if ind["subject"] == "astronaut" and not obs.astronaut_id:
                    raise ItemError([f"{obs.metric_code} requires astronaut_id"])
                if ind["subject"] == "environment" and obs.astronaut_id:
                    raise ItemError([f"{obs.metric_code} is an environmental reading; astronaut_id must be omitted"])
                if obs.astronaut_id:
                    a = db.one(conn, "SELECT mission_id FROM astronauts WHERE id=?", (obs.astronaut_id,))
                    if not a:
                        raise ItemError([f"unknown astronaut '{obs.astronaut_id}'"])
                    if a["mission_id"] != obs.mission_id:
                        raise ItemError([f"astronaut '{obs.astronaut_id}' is not assigned to mission '{obs.mission_id}'"])
                device = None
                device_id = obs.device_id or (principal.device_id if principal.kind == "device" and obs.metric_code != "symptom" else None)
                if device_id:
                    device = db.one(conn, "SELECT * FROM devices WHERE id=?", (device_id,))
                    if not device:
                        raise ItemError([f"unknown device '{device_id}'"])
                    supported = db.loads(device["metadata"], {}).get("metrics", [])
                    if supported and obs.metric_code not in supported and obs.metric_code != "symptom":
                        raise ItemError([f"device '{device_id}' ({device['device_type']}) does not report {obs.metric_code}"])
                if obs.source_type in ("medical_device", "wearable", "environmental_sensor") and not device_id:
                    raise ItemError([f"source_type '{obs.source_type}' requires device_id"])
                _authorize(conn, principal, obs, ind, device)
                measured_at = _check_time(obs.measured_at)
                cols = _validate_value(ind, obs.value, obs.unit)

                obs_id = obs.observation_id or db.new_id("OBS")
                # payload hash covers the sender's content (not server timestamps) -> idempotency
                content = obs.model_dump(exclude={"observation_id"})
                content["measured_at"] = measured_at
                content["device_id"] = device_id
                phash = db.sha256(content)
                existing = db.one(conn, "SELECT payload_hash, metric_code FROM observations WHERE id=?", (obs_id,))
                if existing:
                    if existing["payload_hash"] == phash:
                        accepted.append({"index": index, "observation_id": obs_id, "metric_code": obs.metric_code,
                                         "status": "duplicate"})
                        continue
                    raise ItemError([f"observation_id '{obs_id}' already exists with different content (conflict)"])

                synthetic = bool(obs.synthetic or (device and device["is_simulated"]) or obs.source_type == "simulator"
                                 or sim_run_id)
                private = ind.get("privacy") == "private" or extra_private
                row = {
                    "id": obs_id, "subject_type": subject, "astronaut_id": obs.astronaut_id,
                    "mission_id": obs.mission_id, "location": obs.location, "metric_code": obs.metric_code,
                    **cols, "unit": ind["canonical_unit"] if cols["value_num"] is not None and ind["canonical_unit"] != "as_reported" else obs.unit,
                    "original_value": db.dumps(obs.value), "original_unit": obs.unit,
                    "measured_at": measured_at, "received_at": received_at, "source_type": obs.source_type,
                    "device_id": device_id, "quality": obs.quality, "context": db.dumps(obs.context),
                    "notes": obs.notes, "entered_by": principal.actor, "payload_hash": phash, "batch_id": batch_id,
                    "is_synthetic": int(synthetic), "sim_run_id": sim_run_id, "is_private": int(private),
                }
                db.insert(conn, "observations", row)
                stored.append(row)
                accepted.append({"index": index, "observation_id": obs_id, "metric_code": obs.metric_code,
                                 "status": "accepted"})
                if device_id:
                    devices_seen.add(device_id)
                for s_item in _normalize_symptom_items(obs, obs_id):
                    queue.append((index, s_item))
            except ItemError as e:
                rejected.append({"index": index, "observation_id": oid, "errors": e.errors})
            except units.UnitError as e:
                rejected.append({"index": index, "observation_id": oid, "errors": [str(e)]})
            except ValueError as e:
                rejected.append({"index": index, "observation_id": oid, "errors": [str(e)]})
        for dev in devices_seen:
            conn.execute("UPDATE devices SET last_seen_at=?, status=CASE WHEN status IN ('disconnected','error') "
                         "THEN 'connected' ELSE status END WHERE id=?", (received_at, dev))
        if stored:
            audit.record(conn, principal, "observations.ingest", "observation_batch", batch_id,
                         {"accepted": len(stored), "rejected": len(rejected),
                          "sources": sorted({r["source_type"] for r in stored})})

    # ------------------------------------------------ real-time + assessment
    groups: dict[tuple, list[dict]] = {}
    for r in stored:
        groups.setdefault((r["astronaut_id"], r["mission_id"]), []).append(r)
    assessments, created, updated = [], [], []
    for (ast_id, mission_id), rows in groups.items():
        pub = [r for r in rows if not r["is_private"]]
        priv = [r for r in rows if r["is_private"]]
        for subset, private in ((pub, False), (priv, True)):
            if subset:
                BUS.publish("observations.created", {
                    "count": len(subset), "mission_id": mission_id,
                    "metrics": sorted({r["metric_code"] for r in subset}),
                    "observation_ids": [r["id"] for r in subset][:50],
                    "latest_measured_at": max(r["measured_at"] for r in subset),
                }, astronaut_id=ast_id, private=private)
        if run_assessment:
            res = assessment_engine.assess(conn, astronaut_id=ast_id, mission_id=mission_id,
                                           trigger="observations", observations=rows, sim_run_id=sim_run_id)
            assessments.extend(res["assessment_ids"])
            created.extend(res["alerts_created"])
            updated.extend(res["alerts_updated"])
    for dev in devices_seen:
        BUS.publish("device.status", {"device_id": dev, "status": "connected", "last_seen_at": received_at})

    status = "complete" if not rejected else ("partial" if accepted else "rejected")
    return {"processing_status": status, "batch_id": batch_id, "accepted": accepted, "rejected": rejected,
            "validation_errors": sum(len(r["errors"]) for r in rejected), "assessments": assessments,
            "alerts_created": created, "alerts_updated": updated}


def handle_telemetry(conn, principal: Principal, payload: dict, idempotency_key: str | None = None,
                     sim_run_id: str | None = None) -> dict:
    """Entry point shared by POST /api/v1/telemetry and the in-process simulator transport."""
    from ..schemas import TelemetryBatchIn
    batch = TelemetryBatchIn.model_validate(payload)
    if idempotency_key:
        prev = db.one(conn, "SELECT response FROM telemetry_batches WHERE idempotency_key=?", (idempotency_key,))
        if prev:
            res = db.loads(prev["response"])
            res["idempotent_replay"] = True
            return res
    res = ingest(conn, principal, batch.observations, batch_id=batch.batch_id or db.new_id("BATCH"),
                 sim_run_id=sim_run_id)
    if idempotency_key:
        conn.execute("INSERT OR IGNORE INTO telemetry_batches VALUES (?,?,?)",
                     (idempotency_key, db.dumps(res), db.now_iso()))
    return res


def decode_observation(row: dict) -> dict:
    r = dict(row)
    r["context"] = db.loads(r.get("context"), {})
    if r.get("value_json"):
        r["value"] = db.loads(r["value_json"])
    elif r.get("value_bool") is not None:
        r["value"] = bool(r["value_bool"])
    elif r.get("value_num") is not None:
        r["value"] = r["value_num"]
    else:
        r["value"] = r.get("value_text")
    r["original_value"] = db.loads(r.get("original_value"))
    r["is_synthetic"] = bool(r.get("is_synthetic"))
    r["is_private"] = bool(r.get("is_private"))
    r.pop("payload_hash", None)
    return r


def device_principal(conn, key: str) -> Principal:
    """Authenticate a device API key (shared by the HTTP layer and the in-process simulator transport)."""
    from .. import security
    dev = db.one(conn, "SELECT * FROM devices WHERE api_key_hash=?", (security.hash_device_key(key),))
    if not dev:
        raise PermissionError("device key not recognised")
    return Principal(kind="device", name=dev["id"], role="device", device_id=dev["id"],
                     astronaut_id=dev["astronaut_id"], mission_id=dev["mission_id"])
