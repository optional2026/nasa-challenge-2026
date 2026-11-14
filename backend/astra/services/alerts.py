"""Alert management: creation with de-duplication, acknowledgement, escalation
status and resolution. Severity categories are INFORMATION, REASSESSMENT,
MEDICAL_REVIEW and URGENT (never a generic numeric score)."""
from __future__ import annotations

from .. import audit, db
from ..bus import BUS
from ..security import MEDICAL_ROLES, REDACTED, Principal, can_view_private

SEVERITY_ORDER = {"INFORMATION": 1, "REASSESSMENT": 2, "MEDICAL_REVIEW": 3, "URGENT": 4}


def upsert(conn, *, finding: dict, astronaut_id, mission_id, assessment_id, synthetic, sim_run_id) -> tuple[str, bool]:
    """Create an alert or update the open alert with the same dedup key. Returns (alert_id, created)."""
    now = db.now_iso()
    existing = db.one(conn, "SELECT * FROM alerts WHERE dedup_key=? AND resolution_status='open'", (finding["dedup_key"],))
    rule = finding["rule"]
    if existing:
        new_sev = finding["severity"]
        changes = {"updated_at": now, "occurrence_count": existing["occurrence_count"] + 1,
                   "assessment_id": assessment_id, "explanation": finding["explanation"],
                   "baseline_context": db.dumps(finding.get("baseline_comparison") or {})}
        if SEVERITY_ORDER[new_sev] > SEVERITY_ORDER[existing["severity"]]:
            changes.update({"severity": new_sev, "title": finding["title"], "next_step": finding["next_step"],
                            "ack_status": "unacknowledged"})
        db.update(conn, "alerts", "id", existing["id"], changes)
        aid, created = existing["id"], False
    else:
        aid, created = db.new_id("ALR"), True
        db.insert(conn, "alerts", {
            "id": aid, "astronaut_id": astronaut_id, "mission_id": mission_id, "assessment_id": assessment_id,
            "medical_event_id": None, "severity": finding["severity"], "category": finding["category"],
            "rule_id": rule["id"], "rule_version": rule["version"], "rule_class": rule["rule_class"],
            "title": finding["title"], "explanation": finding["explanation"],
            "baseline_context": db.dumps(finding.get("baseline_comparison") or {}),
            "related_symptoms": db.dumps(finding.get("symptoms") or []), "next_step": finding["next_step"],
            "protocol_id": rule.get("protocol_id"), "created_at": now, "updated_at": now,
            "dedup_key": finding["dedup_key"], "is_private": int(finding.get("private", False)),
            "is_synthetic": int(synthetic), "sim_run_id": sim_run_id})
    conn.executemany("INSERT OR IGNORE INTO alert_observations VALUES (?,?)",
                     [(aid, o) for o in finding.get("evidence", [])])
    return aid, created


def decode(conn, a: dict, p: Principal | None = None, with_obs: bool = False) -> dict:
    a = dict(a)
    a["baseline_context"] = db.loads(a["baseline_context"], {})
    a["related_symptoms"] = db.loads(a["related_symptoms"], [])
    a["is_private"] = bool(a["is_private"])
    a["is_synthetic"] = bool(a["is_synthetic"])
    a["redacted"] = False
    if with_obs:
        a["observation_ids"] = [r["observation_id"] for r in db.all_(conn, "SELECT observation_id FROM alert_observations WHERE alert_id=?", (a["id"],))]
    if a["is_private"] and p is not None and not can_view_private(p, a["astronaut_id"]):
        a.update({"title": "Private behavioral-health item", "explanation": REDACTED, "baseline_context": {},
                  "related_symptoms": [], "redacted": True, "observation_ids": []})
    return a


def acknowledge(conn, actor: Principal, alert_id: str, note: str | None) -> dict:
    a = db.one(conn, "SELECT * FROM alerts WHERE id=?", (alert_id,))
    if not a:
        raise LookupError(alert_id)
    now = db.now_iso()
    with db.transaction(conn):
        db.update(conn, "alerts", "id", alert_id, {"ack_status": "acknowledged", "ack_by": actor.actor, "ack_at": now,
                                                   "updated_at": now})
        audit.record(conn, actor, "alert.acknowledge", "alert", alert_id, {"note": note})
        if a["medical_event_id"]:
            from . import medical_events
            medical_events.add_action(conn, actor, a["medical_event_id"], "note",
                                      f"Alert {alert_id} acknowledged" + (f": {note}" if note else ""))
    BUS.publish("alert.acknowledged", {"id": alert_id, "severity": a["severity"]}, astronaut_id=a["astronaut_id"],
                private=bool(a["is_private"]))
    return decode(conn, db.one(conn, "SELECT * FROM alerts WHERE id=?", (alert_id,)), actor)


def resolve(conn, actor: Principal, alert_id: str, note: str | None) -> dict:
    a = db.one(conn, "SELECT * FROM alerts WHERE id=?", (alert_id,))
    if not a:
        raise LookupError(alert_id)
    if a["resolution_status"] == "resolved":
        raise ValueError("alert already resolved")
    if SEVERITY_ORDER[a["severity"]] >= SEVERITY_ORDER["MEDICAL_REVIEW"] and actor.role not in MEDICAL_ROLES:
        raise PermissionError("medical-review and urgent alerts can only be resolved by medical personnel")
    if a["medical_event_id"]:
        e = db.one(conn, "SELECT state FROM medical_events WHERE id=?", (a["medical_event_id"],))
        if e and e["state"] != "RESOLVED":
            raise ValueError("resolve the linked medical event first; an event never disappears because an alert is closed")
    if not note:
        raise ValueError("a resolution note is required")
    now = db.now_iso()
    with db.transaction(conn):
        db.update(conn, "alerts", "id", alert_id, {"resolution_status": "resolved", "resolved_by": actor.actor,
                                                   "resolved_at": now, "resolution_note": note, "updated_at": now})
        audit.record(conn, actor, "alert.resolve", "alert", alert_id, {"note": note})
    BUS.publish("alert.resolved", {"id": alert_id, "severity": a["severity"]}, astronaut_id=a["astronaut_id"],
                private=bool(a["is_private"]))
    return decode(conn, db.one(conn, "SELECT * FROM alerts WHERE id=?", (alert_id,)), actor)
