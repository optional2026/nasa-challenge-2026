"""Crew Side → Earth Side store-and-forward replication.

ONBOARD (Crew Side)
  * SQLite triggers (installed only on the onboard deployment) add every new or changed health record to the
    persistent ``replication_outbox`` in the SAME transaction that stores the record. The record is therefore saved
    locally first and can never be lost between "saved" and "queued". No business logic had to change.
  * ``SyncWorker`` (a server thread, independent of browser sessions and logins) sends pending records in change
    order to the Earth server: HMAC-SHA256 signed requests, HTTPS required unless the Earth server is on loopback.
  * A record becomes SYNCED only when Earth acknowledges exactly the version that was sent. Transport errors keep
    it queued (FAILED + retry with back-off); a permanent rejection by Earth is REJECTED (visible, audited).
  * The link gate (``link_available``) is consulted before ANY network I/O. The CMO demonstration control sets a
    persistent simulated outage; while it is active the worker cannot deliver anything to Earth.

EARTH (Earth Side)
  * ``receive_batch`` verifies the signature and peer identity, validates every record (known type, column
    whitelist, record identity, mission/astronaut scope, timestamps, integrity hash) and stores it idempotently.
  * Conflict rules: health observations and logs are IMMUTABLE — a second copy with different content is rejected,
    never overwritten. Onboard-owned workflow state (alerts, medical events, environment events, reports) is applied
    only when its revision is newer than the stored one. Earth-side clinical follow-up is stored separately as
    ``ground_annotations`` (attributable, never edits onboard records) and delivered to the CMO via the downlink.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from .. import audit, config, db
from ..bus import BUS

PROTOCOL = "astra-replication/1"
MAX_BATCH = 200
SIGNATURE_WINDOW_S = 300
SEND_TIMEOUT = (3.0, 20.0)
MAX_BACKOFF_S = 60
MAX_DEFERRALS = 12  # a record Earth keeps deferring (missing parent) becomes REJECTED and visible


# ------------------------------------------------------------------ what is replicated
@dataclass(frozen=True)
class Spec:
    record_type: str
    table: str
    key: tuple[str, ...] = ("id",)
    mutable: bool = False          # onboard-owned workflow state: newer revisions replace older ones on Earth
    update_cols: tuple[str, ...] | None = None  # columns whose change re-queues the record (None = any column)
    time_col: str | None = None    # original event timestamp shown in status lists
    parents: tuple[tuple[str, str], ...] = ()   # (column, table) whose mission scope must match (link tables)


SPECS: dict[str, Spec] = {s.record_type: s for s in [
    Spec("observation", "observations", time_col="measured_at"),
    Spec("sleep_record", "sleep_records", time_col="sleep_end"),
    Spec("mood_assessment", "mood_assessments", time_col="assessed_at"),
    Spec("exercise_record", "exercise_records", time_col="start_at"),
    Spec("nutrition_record", "nutrition_records", time_col="recorded_at"),
    Spec("medication_record", "medication_records", time_col="administered_at"),
    Spec("medical_history", "medical_history", time_col="recorded_at"),
    Spec("health_assessment", "health_assessments", time_col="created_at"),
    Spec("assessment_observation", "assessment_observations", ("assessment_id", "observation_id"),
         parents=(("assessment_id", "health_assessments"), ("observation_id", "observations"))),
    Spec("medical_event", "medical_events", mutable=True, time_col="opened_at"),
    Spec("alert", "alerts", mutable=True, time_col="created_at"),
    Spec("alert_observation", "alert_observations", ("alert_id", "observation_id"),
         parents=(("alert_id", "alerts"), ("observation_id", "observations"))),
    Spec("medical_event_transition", "medical_event_transitions", time_col="at",
         parents=(("event_id", "medical_events"),)),
    Spec("medical_event_action", "medical_event_actions", time_col="performed_at",
         parents=(("event_id", "medical_events"),)),
    Spec("medical_report", "medical_reports", mutable=True, time_col="created_at",
         update_cols=("event_id", "astronaut_id", "mission_id", "content", "rendered_text", "content_hash", "is_private")),
    Spec("environment_event", "environment_events", mutable=True, time_col="started_at"),
    Spec("environment_event_observation", "environment_event_observations", ("event_id", "observation_id"),
         parents=(("event_id", "environment_events"), ("observation_id", "observations"))),
]}
TABLE_TO_TYPE = {s.table: s.record_type for s in SPECS.values()}
# Columns kept local to each side (not part of the replicated content / integrity hash).
LOCAL_COLS = {"medical_reports": {"sync_status"}}


def _cols(conn, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _key_expr(spec: Spec, ref: str = "NEW") -> str:
    return " || '|' || ".join(f"CAST({ref}.{k} AS TEXT)" for k in spec.key)


def install_triggers(conn) -> None:
    """Onboard only. Idempotent. Records that existed before installation (the pre-flight reference dataset that
    both sides are provisioned with) are not queued."""
    now = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
    for spec in SPECS.values():
        key = _key_expr(spec)
        upsert = (f"INSERT INTO replication_outbox(record_type, record_id, status, version, change_seq, enqueued_at, changed_at) "
                  f"VALUES ('{spec.record_type}', {key}, 'PENDING', 1, "
                  f"(SELECT COALESCE(MAX(change_seq),0)+1 FROM replication_outbox), {now}, {now}) "
                  f"ON CONFLICT(record_type, record_id) DO UPDATE SET status='PENDING', version=version+1, "
                  f"change_seq=excluded.change_seq, changed_at=excluded.changed_at, next_attempt_at=NULL, last_error=NULL;")
        conn.execute(f"CREATE TRIGGER IF NOT EXISTS repl_{spec.table}_ins AFTER INSERT ON {spec.table} BEGIN {upsert} END")
        of = f" OF {', '.join(spec.update_cols)}" if spec.update_cols else ""
        conn.execute(f"CREATE TRIGGER IF NOT EXISTS repl_{spec.table}_upd AFTER UPDATE{of} ON {spec.table} BEGIN {upsert} END")


def _fetch(conn, spec: Spec, record_id: str) -> dict | None:
    parts = record_id.split("|")
    if len(parts) != len(spec.key):
        return None
    where = " AND ".join(f"CAST({k} AS TEXT)=?" for k in spec.key)
    row = db.one(conn, f"SELECT * FROM {spec.table} WHERE {where}", parts)
    if row is not None:
        for c in LOCAL_COLS.get(spec.table, ()):
            row.pop(c, None)
    return row


def content_hash(payload: dict) -> str:
    return db.sha256(payload)


# ------------------------------------------------------------------ state (both sides)
def get_state(conn, key: str, default=None):
    r = db.one(conn, "SELECT value FROM replication_state WHERE key=?", (key,))
    return r["value"] if r else default


def set_state(conn, key: str, value) -> None:
    conn.execute("INSERT INTO replication_state(key, value, updated_at) VALUES (?,?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                 (key, None if value is None else str(value), db.now_iso()))


def simulated_outage(conn) -> bool:
    """True while the CMO demonstration control holds the Earth link down (persistent in the onboard database)."""
    return config.allow_link_simulation() and get_state(conn, "simulated_outage") == "1"


def link_available(conn) -> tuple[bool, str | None]:
    """Transport gate checked immediately before every delivery / downlink request."""
    if config.deployment() != "onboard":
        return False, "not an onboard deployment"
    if simulated_outage(conn):
        return False, "Earth link unavailable (SIMULATED outage set by the CMO)"
    if not config.earth_url():
        return False, "ASTRA_EARTH_URL is not configured"
    if not config.sync_key():
        return False, "server-to-server sync key (ASTRA_SYNC_KEY) is not configured"
    return True, None


# ------------------------------------------------------------------ signing / transport
def sign(key: str, method: str, path: str, ts: str, node: str, body: bytes) -> str:
    msg = b"\n".join([PROTOCOL.encode(), method.upper().encode(), path.encode(), ts.encode(), node.encode(),
                      hashlib.sha256(body).hexdigest().encode()])
    return hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()


def signed_headers(method: str, path: str, body: bytes) -> dict:
    ts = str(int(time.time()))
    node = config.node_id()
    return {"Content-Type": "application/json", "X-Astra-Protocol": PROTOCOL, "X-Astra-Node": node,
            "X-Astra-Timestamp": ts, "X-Astra-Signature": sign(config.sync_key() or "", method, path, ts, node, body)}


def verify_request(method: str, path: str, headers: dict, body: bytes) -> str:
    """Earth side: returns the authenticated peer node id or raises PermissionError."""
    key = config.sync_key()
    if not key:
        raise PermissionError("replication is not configured on this server (no sync key)")
    node = headers.get("x-astra-node", "")
    ts = headers.get("x-astra-timestamp", "")
    sig = headers.get("x-astra-signature", "")
    if headers.get("x-astra-protocol") != PROTOCOL:
        raise PermissionError("unsupported replication protocol")
    if node != config.sync_peer_id():
        raise PermissionError("unknown replication peer")
    try:
        skew = abs(time.time() - int(ts))
    except ValueError:
        raise PermissionError("invalid timestamp")
    if skew > SIGNATURE_WINDOW_S:
        raise PermissionError("request timestamp outside the allowed window")
    if not hmac.compare_digest(sign(key, method, path, ts, node, body), sig):
        raise PermissionError("invalid signature")
    return node


class TransportError(Exception):
    pass


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    import requests
    base = config.earth_url() or ""
    u = urlparse(base)
    if u.scheme != "https" and not (_is_loopback(u.hostname) or config.sync_allow_insecure()):
        raise TransportError("refusing to replicate health records over unencrypted HTTP to a non-loopback host; "
                             "use an https:// ASTRA_EARTH_URL")
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    full_path = config.API_PREFIX + path
    headers = signed_headers(method, full_path, body)
    try:
        r = requests.request(method, base + full_path, data=body or None, headers=headers, timeout=SEND_TIMEOUT,
                             verify=config.sync_ca_bundle() or True)
    except requests.RequestException as exc:
        raise TransportError(f"Earth server unreachable: {exc.__class__.__name__}")
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise TransportError(f"Earth server answered {r.status_code}: {msg}")
    return r.json()


# ------------------------------------------------------------------ onboard: one synchronization pass
_PASS_LOCK = threading.Lock()


def _publish_status(conn) -> None:
    st = link_status(conn)
    BUS.publish("replication.status", {k: st[k] for k in ("link_state", "sync_state", "counts", "last_success_at")})


def run_pass(conn) -> dict:
    """Deliver due records and fetch ground notes. Safe to call concurrently (serialised) and repeatedly."""
    with _PASS_LOCK:
        res = _run_pass(conn)
    _publish_status(conn)
    return res


def _run_pass(conn) -> dict:
    out = {"sent": 0, "acknowledged": 0, "rejected": 0, "deferred": 0, "discarded": 0, "downlink": 0, "link": "available"}
    now = db.utcnow()
    now_s = db.iso(now)
    with db.transaction(conn):
        # a SENDING row at the start of a pass belongs to an interrupted earlier pass (crash, restart): resend it
        conn.execute("UPDATE replication_outbox SET status='PENDING' WHERE status='SENDING'")
    ok, why = link_available(conn)
    if not ok:
        out["link"] = "unavailable"
        out["reason"] = why
        with db.transaction(conn):
            set_state(conn, "last_link_check", now_s)
            set_state(conn, "link_reason", why)
        return out
    rows = db.all_(conn, "SELECT * FROM replication_outbox WHERE status IN ('PENDING','FAILED') "
                         "AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY change_seq LIMIT ?", (now_s, MAX_BATCH))
    envelopes, claimed = [], []
    if rows:
        with db.transaction(conn):
            for r in rows:
                spec = SPECS.get(r["record_type"])
                row = _fetch(conn, spec, r["record_id"]) if spec else None
                if row is None:
                    # removed locally before it could be sent (only synthetic demo data is ever deleted onboard)
                    conn.execute("UPDATE replication_outbox SET status='DISCARDED', last_error=? WHERE seq=?",
                                 ("record deleted onboard before transmission (synthetic demo-data reset)", r["seq"]))
                    out["discarded"] += 1
                    continue
                conn.execute("UPDATE replication_outbox SET status='SENDING', sent_version=version, attempts=attempts+1, "
                             "last_attempt_at=? WHERE seq=?", (now_s, r["seq"]))
                envelopes.append({"record_type": r["record_type"], "record_id": r["record_id"], "revision": r["version"],
                                  "payload_hash": content_hash(row), "payload": row})
                claimed.append(r)
    try:
        if envelopes:
            mission = db.one(conn, "SELECT id FROM missions ORDER BY start_utc DESC LIMIT 1")
            batch = {"protocol": PROTOCOL, "batch_id": db.new_id("RB"), "node_id": config.node_id(),
                     "mission_id": mission["id"] if mission else None, "sent_at": now_s, "records": envelopes}
            # the gate is re-checked right before the network call (the CMO may have just cut the link)
            ok, why = link_available(conn)
            if not ok:
                raise TransportError(why or "link unavailable")
            resp = _request("POST", "/replication/batch", batch)
            out["sent"] = len(envelopes)
            _apply_acks(conn, claimed, envelopes, resp, out)
        out["downlink"] = _downlink(conn)
        with db.transaction(conn):
            set_state(conn, "earth_reachable", "1")
            set_state(conn, "last_success_at", db.now_iso())
            set_state(conn, "last_error", None)
            set_state(conn, "link_reason", None)
            if envelopes:
                set_state(conn, "last_batch", db.dumps({k: out[k] for k in ("sent", "acknowledged", "rejected", "deferred")}))
    except TransportError as exc:
        out["link"] = "unreachable"
        out["error"] = str(exc)
        with db.transaction(conn):
            for r in claimed:
                attempts = r["attempts"] + 1
                backoff = min(MAX_BACKOFF_S, 2 ** min(attempts, 6))
                conn.execute("UPDATE replication_outbox SET status='FAILED', last_error=?, next_attempt_at=? "
                             "WHERE seq=? AND status='SENDING'", (str(exc), db.iso(now + timedelta(seconds=backoff)), r["seq"]))
            simulated = simulated_outage(conn)
            set_state(conn, "earth_reachable", None if simulated else "0")
            set_state(conn, "last_error", str(exc))
            if claimed:
                audit.record(conn, "system:astra-sync", "replication.send_failed", "replication_batch", None,
                             {"records": len(claimed), "error": str(exc)})
    return out


def _apply_acks(conn, claimed: list[dict], envelopes: list[dict], resp: dict, out: dict) -> None:
    results = {(x.get("record_type"), x.get("record_id")): x for x in resp.get("results", [])}
    now_s = db.now_iso()
    with db.transaction(conn):
        for r, env in zip(claimed, envelopes):
            res = results.get((r["record_type"], r["record_id"]))
            st = (res or {}).get("status")
            if st in ("stored", "updated", "duplicate", "stale"):
                # SYNCED only if nothing changed locally while the batch was in flight; otherwise send the new version
                conn.execute("UPDATE replication_outbox SET status=CASE WHEN version=sent_version THEN 'SYNCED' ELSE 'PENDING' END, "
                             "synced_at=?, synced_hash=?, last_error=NULL, next_attempt_at=NULL WHERE seq=?",
                             (now_s, env["payload_hash"], r["seq"]))
                if r["record_type"] == "medical_report":
                    conn.execute("UPDATE medical_reports SET sync_status='acknowledged' WHERE id=?", (r["record_id"],))
                out["acknowledged"] += 1
            elif st == "rejected":
                conn.execute("UPDATE replication_outbox SET status='REJECTED', last_error=? WHERE seq=?",
                             (f"rejected by Earth: {res.get('error')}", r["seq"]))
                audit.record(conn, "system:astra-sync", "replication.rejected", r["record_type"], r["record_id"],
                             {"error": res.get("error")})
                out["rejected"] += 1
            elif r["attempts"] + 1 >= MAX_DEFERRALS:
                conn.execute("UPDATE replication_outbox SET status='REJECTED', last_error=? WHERE seq=?",
                             (f"not accepted by Earth after {MAX_DEFERRALS} attempts: {(res or {}).get('error')}", r["seq"]))
                audit.record(conn, "system:astra-sync", "replication.rejected", r["record_type"], r["record_id"],
                             {"error": (res or {}).get("error"), "attempts": r["attempts"] + 1})
                out["rejected"] += 1
            else:  # deferred (e.g. parent record not yet on Earth) or missing from the answer: retry later
                attempts = r["attempts"] + 1
                conn.execute("UPDATE replication_outbox SET status='FAILED', last_error=?, next_attempt_at=? WHERE seq=?",
                             (f"deferred by Earth: {(res or {}).get('error', 'no acknowledgement')}",
                              db.iso(db.utcnow() + timedelta(seconds=min(MAX_BACKOFF_S, 2 ** min(attempts, 6)))), r["seq"]))
                out["deferred"] += 1
        audit.record(conn, "system:astra-sync", "replication.batch_sent", "replication_batch", resp.get("batch_id"),
                     {k: out[k] for k in ("sent", "acknowledged", "rejected", "deferred")})


def _downlink(conn) -> int:
    """Fetch ground follow-up notes created on Earth since the last confirmed cursor (the cursor sent in the request
    acknowledges everything up to it)."""
    ok, why = link_available(conn)
    if not ok:
        raise TransportError(why or "link unavailable")
    cursor = int(get_state(conn, "downlink_cursor", "0") or 0)
    resp = _request("GET", f"/replication/downlink?after={cursor}")
    n = 0
    with db.transaction(conn):
        for a in resp.get("annotations", []):
            if db.one(conn, "SELECT 1 FROM ground_annotations WHERE id=?", (a["id"],)):
                continue
            db.insert(conn, "ground_annotations", {
                "id": a["id"], "earth_seq": a["seq"], "mission_id": a["mission_id"], "astronaut_id": a.get("astronaut_id"),
                "subject_type": a.get("subject_type"), "subject_id": a.get("subject_id"), "kind": a["kind"],
                "text": a["text"], "author": a["author"], "author_role": a["author_role"], "created_at": a["created_at"],
                "delivered_at": None, "received_onboard_at": db.now_iso()})
            n += 1
            BUS.publish("ground_annotation.received", {"id": a["id"], "kind": a["kind"]}, astronaut_id=a.get("astronaut_id"))
        if resp.get("annotations"):
            set_state(conn, "downlink_cursor", max(a["seq"] for a in resp["annotations"]))
        if n:
            audit.record(conn, "system:astra-sync", "replication.downlink", "ground_annotation", None, {"received": n})
    return n


# ------------------------------------------------------------------ onboard: worker
class SyncWorker(threading.Thread):
    """Onboard background service. Runs from server start to shutdown, regardless of who is logged in."""

    def __init__(self, interval: float | None = None):
        super().__init__(daemon=True, name="astra-replication")
        self.interval = interval if interval is not None else config.sync_interval()
        self.stop_event = threading.Event()
        self.wake = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            try:
                with db.session() as conn:
                    run_pass(conn)
            except Exception as exc:  # keep the service alive; the error is visible in logs and link status
                print("[replication] error:", exc)
            self.wake.wait(self.interval)
            self.wake.clear()


WORKER: SyncWorker | None = None


def wake_worker() -> None:
    if WORKER is not None:
        WORKER.wake.set()


# ------------------------------------------------------------------ onboard: CMO link simulation
def set_simulated_outage(conn, actor, outage: bool) -> dict:
    with db.transaction(conn):
        before = get_state(conn, "simulated_outage") == "1"
        set_state(conn, "simulated_outage", "1" if outage else "0")
        set_state(conn, "simulated_outage_changed_at", db.now_iso())
        set_state(conn, "simulated_outage_changed_by", actor.actor)
        if not outage:
            # retry everything that waited for the link immediately (REJECTED records stay rejected)
            conn.execute("UPDATE replication_outbox SET next_attempt_at=NULL WHERE status IN ('PENDING','FAILED')")
            set_state(conn, "earth_reachable", None)
        audit.record(conn, actor, "link_simulation.enabled" if outage else "link_simulation.disabled", "earth_link", None,
                     {"simulated_outage": outage, "previous": before, "note": "DEMONSTRATION control — not network management"})
    BUS.publish("sync.link", {"simulated_outage": outage})
    _publish_status(conn)
    if not outage:
        wake_worker()
    return link_status(conn)


# ------------------------------------------------------------------ status views
def outbox_counts(conn) -> dict:
    return {r["status"]: r["c"] for r in db.all_(conn, "SELECT status, COUNT(*) c FROM replication_outbox GROUP BY status")}


def link_status(conn) -> dict:
    dep = config.deployment()
    if dep == "earth":
        return earth_status(conn, None)
    counts = outbox_counts(conn)
    sim = simulated_outage(conn)
    reach = get_state(conn, "earth_reachable")
    ok, why = link_available(conn) if dep == "onboard" else (False, "standalone prototype")
    if sim:
        link_state = "unavailable_simulated"
    elif not ok:
        link_state = "not_configured"
    elif reach == "1":
        link_state = "available"
    elif reach == "0":
        link_state = "unreachable"
    else:
        link_state = "checking"
    if counts.get("SENDING"):
        sync_state = "in_progress"
    elif counts.get("FAILED"):
        sync_state = "failed" if link_state == "available" else "pending"
    elif counts.get("PENDING"):
        sync_state = "pending"
    elif counts.get("REJECTED"):
        sync_state = "rejected"
    else:
        sync_state = "complete"
    u = urlparse(config.earth_url() or "")
    return {
        "deployment": dep, "node_id": config.node_id(),
        "earth_server": f"{u.scheme}://{u.netloc}" if u.netloc else None,
        "encrypted_transport": u.scheme == "https",
        "simulation_allowed": dep == "onboard" and config.allow_link_simulation(),
        "simulated_outage": sim,
        "simulated_outage_changed_at": get_state(conn, "simulated_outage_changed_at"),
        "simulated_outage_changed_by": get_state(conn, "simulated_outage_changed_by"),
        "link_state": link_state, "link_reason": why if not ok else None, "sync_state": sync_state,
        "counts": {s: counts.get(s, 0) for s in ("PENDING", "SENDING", "SYNCED", "FAILED", "REJECTED", "DISCARDED")},
        "unsynced": sum(counts.get(s, 0) for s in ("PENDING", "SENDING", "FAILED")),
        "last_success_at": get_state(conn, "last_success_at"),
        "last_error": get_state(conn, "last_error"),
        "last_batch": db.loads(get_state(conn, "last_batch"), None),
    }


def _astronaut_of(conn, spec: Spec, row: dict) -> str | None:
    if "astronaut_id" in row:
        return row["astronaut_id"]
    for col, table in spec.parents:
        if table in ("observations", "health_assessments", "alerts", "medical_events"):
            p = db.one(conn, f"SELECT astronaut_id FROM {table} WHERE id=?", (row[col],))
            if p and p["astronaut_id"]:
                return p["astronaut_id"]
    return None


def unsynced_records(conn, astronaut_ids: set[str] | None, limit: int = 100) -> list[dict]:
    """Onboard: records not yet acknowledged by Earth (PENDING / SENDING / FAILED / REJECTED), newest change first,
    restricted to `astronaut_ids` (None = all)."""
    out = []
    rows = db.all_(conn, "SELECT * FROM replication_outbox WHERE status IN ('PENDING','SENDING','FAILED','REJECTED') "
                         "ORDER BY change_seq DESC LIMIT 2000")
    for r in rows:
        spec = SPECS.get(r["record_type"])
        row = _fetch(conn, spec, r["record_id"]) if spec else None
        if row is None:
            continue
        ast = _astronaut_of(conn, spec, row)
        if astronaut_ids is not None and ast not in astronaut_ids:
            continue
        out.append({"record_type": r["record_type"], "record_id": r["record_id"], "astronaut_id": ast,
                    "status": r["status"], "attempts": r["attempts"], "version": r["version"],
                    "original_time": row.get(spec.time_col) if spec.time_col else None,
                    "metric_code": row.get("metric_code"), "is_private": bool(row.get("is_private")),
                    "queued_at": r["enqueued_at"], "changed_at": r["changed_at"], "last_attempt_at": r["last_attempt_at"],
                    "last_error": r["last_error"]})
        if len(out) >= limit:
            break
    return out


def record_sync_info(conn, record_type: str, record_id: str) -> dict | None:
    """Per-record replication metadata for detail views (both sides)."""
    dep = config.deployment()
    if dep == "onboard":
        r = db.one(conn, "SELECT status, version, attempts, enqueued_at, synced_at, last_error FROM replication_outbox "
                         "WHERE record_type=? AND record_id=?", (record_type, record_id))
        return {"side": "onboard", **r} if r else {"side": "onboard", "status": "NOT_QUEUED (pre-flight reference data)"}
    if dep == "earth":
        r = db.one(conn, "SELECT origin_node, revision, first_received_at, last_received_at FROM replicated_records "
                         "WHERE record_type=? AND record_id=?", (record_type, record_id))
        return {"side": "earth", **r} if r else {"side": "earth", "origin_node": None,
                                                 "note": "Earth-side reference data (not received from the spacecraft)"}
    return None


# ------------------------------------------------------------------ Earth: receiving
class BatchError(ValueError):
    pass


_TS_COLS_SUFFIX = ("_at", "_utc")
_TS_COLS = {"sleep_start", "sleep_end", "at"}


def _validate_record(conn, spec: Spec, env: dict, peer_mission: str) -> dict:
    payload = env.get("payload")
    if not isinstance(payload, dict) or not payload:
        raise BatchError("payload must be a non-empty object")
    if content_hash(payload) != env.get("payload_hash"):
        raise BatchError("payload integrity hash mismatch")
    cols = set(_cols(conn, spec.table)) - LOCAL_COLS.get(spec.table, set())
    unknown = set(payload) - cols
    if unknown:
        raise BatchError(f"unknown columns for {spec.table}: {sorted(unknown)}")
    missing = [k for k in spec.key if payload.get(k) in (None, "")]
    if missing:
        raise BatchError(f"record identity incomplete: {missing}")
    if "|".join(str(payload[k]) for k in spec.key) != env.get("record_id"):
        raise BatchError("record_id does not match the record's key columns")
    for c, v in payload.items():
        if v is not None and (c in _TS_COLS or c.endswith(_TS_COLS_SUFFIX)) and c != "sim_run_id":
            try:
                db.parse_iso(v)
            except (ValueError, TypeError):
                raise BatchError(f"{c} is not a valid timezone-aware timestamp")
    if spec.table == "observations":
        if db.parse_iso(payload["measured_at"]) > db.utcnow() + timedelta(seconds=config.FUTURE_SKEW_SECONDS):
            raise BatchError("measured_at is in the future")
    # scope: the peer may only deliver records of ITS mission and of astronauts assigned to that mission
    if "mission_id" in payload and payload["mission_id"] != peer_mission:
        raise BatchError("record belongs to a mission this spacecraft is not authorised for")
    ast = payload.get("astronaut_id")
    if ast is not None:
        a = db.one(conn, "SELECT mission_id FROM astronauts WHERE id=?", (ast,))
        if not a or a["mission_id"] != peer_mission:
            raise BatchError("astronaut is not assigned to this spacecraft's mission")
    for col, table in spec.parents:
        pid = payload.get(col)
        prow = db.one(conn, f"SELECT * FROM {table} WHERE id=?", (pid,))
        if prow is None:
            raise _Deferred(f"parent {table} '{pid}' not yet received")
        if prow.get("mission_id") and prow["mission_id"] != peer_mission:
            raise BatchError(f"parent {table} '{pid}' belongs to another mission")
    return payload


class _Deferred(Exception):
    pass


def receive_batch(conn, node: str, batch: dict) -> dict:
    """Earth side. Store a signed batch idempotently; returns one acknowledgement per record."""
    if config.deployment() != "earth":
        raise BatchError("this server is not an Earth deployment")
    peer_mission = config.sync_peer_mission() or batch.get("mission_id")
    if not peer_mission or not db.one(conn, "SELECT id FROM missions WHERE id=?", (peer_mission,)):
        raise BatchError("unknown mission for this replication peer")
    if batch.get("node_id") != node:
        raise BatchError("batch node_id does not match the authenticated peer")
    if batch.get("mission_id") != peer_mission:
        raise BatchError("batch mission does not match the peer's authorised mission")
    records = batch.get("records")
    if not isinstance(records, list) or len(records) > MAX_BATCH * 5:
        raise BatchError("records must be a list (bounded size)")
    batch_id = str(batch.get("batch_id") or db.new_id("RB"))[:64]
    now_s = db.now_iso()
    results, touched = [], {}
    counts = {"stored": 0, "updated": 0, "duplicate": 0, "stale": 0, "rejected": 0, "deferred": 0}
    with db.transaction(conn):
        for env in records:
            rt = env.get("record_type") if isinstance(env, dict) else None
            rid = env.get("record_id") if isinstance(env, dict) else None
            res = {"record_type": rt, "record_id": rid}
            try:
                spec = SPECS.get(rt)
                if spec is None:
                    raise BatchError(f"record type '{rt}' is not replicated")
                rev = env.get("revision")
                if not isinstance(rev, int) or rev < 1:
                    raise BatchError("revision must be a positive integer")
                payload = _validate_record(conn, spec, env, peer_mission)
                status = _store(conn, spec, env, payload, node, batch_id, now_s)
                res["status"] = status
                if status in ("stored", "updated"):
                    ast = _astronaut_of(conn, spec, payload)
                    touched.setdefault((ast, bool(payload.get("is_private"))), set()).add(rt)
            except _Deferred as d:
                res.update(status="deferred", error=str(d))
            except BatchError as e:
                res.update(status="rejected", error=str(e))
            except sqlite3.IntegrityError as e:
                msg = str(e)
                res.update(status="deferred" if "FOREIGN KEY" in msg else "rejected", error=msg)
            counts[res["status"]] += 1
            results.append(res)
        db.insert(conn, "replication_batches", {"batch_id": batch_id + ":" + now_s, "origin_node": node, "received_at": now_s,
                                                "records": len(records), "stored": counts["stored"] + counts["updated"],
                                                "duplicates": counts["duplicate"] + counts["stale"],
                                                "rejected": counts["rejected"], "deferred": counts["deferred"]})
        set_state(conn, "last_received_at", now_s)
        set_state(conn, "last_received_from", node)
        audit.record(conn, f"peer:{node}", "replication.batch_received", "replication_batch", batch_id, counts)
        if counts["rejected"]:
            audit.record(conn, f"peer:{node}", "replication.records_rejected", "replication_batch", batch_id,
                         {"rejected": [r for r in results if r["status"] == "rejected"][:20]})
    for (ast, private), types in touched.items():
        BUS.publish("observations.created", {"count": len(types), "source": "replication", "record_types": sorted(types)},
                    astronaut_id=ast, private=private)
        if types & {"alert"}:
            BUS.publish("alert.updated", {"source": "replication"}, astronaut_id=ast, private=private)
        if types & {"medical_event", "medical_event_action", "medical_event_transition", "medical_report"}:
            BUS.publish("medical_event.updated", {"source": "replication"}, astronaut_id=ast, private=private)
    BUS.publish("replication.received", {"batch_id": batch_id, **counts})
    return {"batch_id": batch_id, "received_at": now_s, "counts": counts, "results": results}


def _store(conn, spec: Spec, env: dict, payload: dict, node: str, batch_id: str, now_s: str) -> str:
    rid, rev, phash = env["record_id"], env["revision"], env["payload_hash"]
    known = db.one(conn, "SELECT * FROM replicated_records WHERE record_type=? AND record_id=?", (spec.record_type, rid))
    where = " AND ".join(f"{k}=?" for k in spec.key)
    keyvals = [payload[k] for k in spec.key]
    if known:
        if known["origin_node"] != node:
            raise BatchError("record id already received from another origin")
        if known["payload_hash"] == phash:
            conn.execute("UPDATE replicated_records SET last_received_at=? WHERE record_type=? AND record_id=?",
                         (now_s, spec.record_type, rid))
            return "duplicate"
        if not spec.mutable:
            raise BatchError("immutable health record already stored with different content (conflict; not overwritten)")
        if rev <= known["revision"]:
            return "stale"  # an older or concurrent version; the newer onboard state is already on Earth
        changes = {k: v for k, v in payload.items() if k not in spec.key}
        conn.execute("SAVEPOINT repl")
        try:
            db.update_where(conn, spec.table, where, keyvals, changes)
            conn.execute("UPDATE replicated_records SET revision=?, payload_hash=?, last_received_at=?, batch_id=? "
                         "WHERE record_type=? AND record_id=?", (rev, phash, now_s, batch_id, spec.record_type, rid))
        except Exception:
            conn.execute("ROLLBACK TO repl")
            conn.execute("RELEASE repl")
            raise
        conn.execute("RELEASE repl")
        return "updated"
    if db.one(conn, f"SELECT 1 FROM {spec.table} WHERE {where}", keyvals):
        # exists on Earth but was not received from the spacecraft (e.g. Earth reference data): never overwrite
        raise BatchError("a different Earth-side record already uses this id (not overwritten)")
    conn.execute("SAVEPOINT repl")
    try:
        db.insert(conn, spec.table, payload)
        db.insert(conn, "replicated_records", {
            "record_type": spec.record_type, "record_id": rid, "origin_node": node,
            "astronaut_id": _astronaut_of(conn, spec, payload), "mission_id": payload.get("mission_id"),
            "revision": rev, "payload_hash": phash, "first_received_at": now_s, "last_received_at": now_s,
            "batch_id": batch_id})
    except Exception:
        conn.execute("ROLLBACK TO repl")
        conn.execute("RELEASE repl")
        raise
    conn.execute("RELEASE repl")
    return "stored"


def downlink(conn, node: str, after: int) -> dict:
    """Earth side: ground notes for the peer's mission with seq > after. Requesting `after=N` confirms that the
    onboard server has stored every note up to N (acknowledgement by cursor)."""
    mission = config.sync_peer_mission()
    now_s = db.now_iso()
    with db.transaction(conn):
        n = conn.execute("UPDATE ground_annotations SET delivered_at=? WHERE delivered_at IS NULL AND seq<=? AND mission_id=?",
                         (now_s, after, mission)).rowcount
        if n:
            audit.record(conn, f"peer:{node}", "replication.downlink_acknowledged", "ground_annotation", None, {"count": n})
    rows = db.all_(conn, "SELECT * FROM ground_annotations WHERE seq>? AND mission_id=? ORDER BY seq LIMIT 200", (after, mission))
    return {"annotations": rows}


def earth_status(conn, astronaut_ids: set[str] | None) -> dict:
    """Earth side: what has arrived from the spacecraft and how fresh it is (never presented as live)."""
    params: list = []
    scope = ""
    if astronaut_ids is not None:
        ids = sorted(astronaut_ids) or [""]
        scope = f" WHERE astronaut_id IN ({','.join('?' * len(ids))})"
        params = ids
    per = db.all_(conn, f"SELECT astronaut_id, COUNT(*) n, MAX(first_received_at) last_received FROM replicated_records{scope} "
                        "GROUP BY astronaut_id", params)
    latest = {}
    for p in per:
        if p["astronaut_id"]:
            r = db.one(conn, "SELECT MAX(o.measured_at) m FROM observations o JOIN replicated_records rr "
                             "ON rr.record_type='observation' AND rr.record_id=o.id WHERE o.astronaut_id=?", (p["astronaut_id"],))
            latest[p["astronaut_id"]] = r["m"]
    batches = db.all_(conn, "SELECT * FROM replication_batches ORDER BY received_at DESC LIMIT 10")
    return {
        "deployment": "earth", "node_id": config.node_id(), "peer": config.sync_peer_id(),
        "peer_mission": config.sync_peer_mission(),
        "last_received_at": get_state(conn, "last_received_at"),
        "records_received": sum(p["n"] for p in per),
        "per_astronaut": [{"astronaut_id": p["astronaut_id"], "records": p["n"], "last_received_at": p["last_received"],
                           "latest_measured_at": latest.get(p["astronaut_id"])} for p in per],
        "recent_batches": batches,
        "notes_pending_delivery": db.one(conn, "SELECT COUNT(*) c FROM ground_annotations WHERE delivered_at IS NULL")["c"],
        "freshness_note": "Data on the Earth server is the latest received from the spacecraft. It is not live: "
                          "records arrive after the communication delay and only while the Earth link is available.",
    }
