"""Store-and-forward synchronization with the ground segment.

Outgoing items (medical reports, escalations, assessment summaries) are queued
locally with an idempotency key and retried with exponential back-off. The
Earth link status and one-way light-time delay are mission settings.

In the prototype the ground segment is SIMULATED in-process by
`SimulatedGroundStation` (it stores received items in `ground_inbox` and
acknowledges after the round-trip delay). A real deployment replaces it with
a transport implementing the same `send()` interface.
"""
from __future__ import annotations

import random
import threading
from datetime import timedelta

from .. import audit, db
from ..bus import BUS

MAX_BACKOFF_S = 300


def enqueue(conn, item_type: str, item_id: str, payload: dict, *, private: bool = False, priority: int = 5) -> str:
    phash = db.sha256(payload)
    key = f"{item_type}:{item_id}:{phash[:16]}"
    existing = db.one(conn, "SELECT id FROM sync_queue WHERE idempotency_key=?", (key,))
    if existing:
        return existing["id"]
    qid = db.new_id("SYNC")
    with db.transaction(conn):
        db.insert(conn, "sync_queue", {
            "id": qid, "item_type": item_type, "item_id": item_id, "payload": db.dumps(payload), "payload_hash": phash,
            "idempotency_key": key, "priority": priority, "status": "pending", "attempts": 0,
            "created_at": db.now_iso(), "last_attempt_at": None, "next_attempt_at": db.now_iso(),
            "delivered_at": None, "acknowledged_at": None, "acknowledged_by": None, "last_error": None,
            "is_private": int(private)})
    BUS.publish("sync.updated", {"id": qid, "status": "pending", "item_type": item_type})
    return qid


class SimulatedGroundStation:
    """Stand-in for the ground medical system (prototype only)."""

    def receive(self, conn, item: dict) -> str:
        prev = db.one(conn, "SELECT * FROM ground_inbox WHERE idempotency_key=?", (item["idempotency_key"],))
        if prev:
            if prev["payload_hash"] != item["payload_hash"]:
                return "conflict"
            return "duplicate"
        db.insert(conn, "ground_inbox", {"idempotency_key": item["idempotency_key"], "item_type": item["item_type"],
                                         "item_id": item["item_id"], "payload_hash": item["payload_hash"],
                                         "received_at": db.now_iso(), "acknowledged_at": None})
        return "received"


GROUND = SimulatedGroundStation()


def _current_hash(conn, item: dict) -> str | None:
    if item["item_type"] == "medical_report":
        r = db.one(conn, "SELECT content FROM medical_reports WHERE id=?", (item["item_id"],))
        if r:
            return db.sha256({"report_id": item["item_id"], "content": db.loads(r["content"])})
    return None


def process(conn, now=None, rng: random.Random | None = None) -> dict:
    """One synchronization pass. Returns counts. Safe to call repeatedly (idempotent)."""
    now = now or db.utcnow()
    rng = rng or random.Random()
    mission = db.one(conn, "SELECT * FROM missions ORDER BY start_utc DESC LIMIT 1")
    if not mission:
        return {}
    link, delay = mission["earth_link_status"], float(mission["comm_delay_seconds"] or 0)
    counts = {"sent": 0, "acknowledged": 0, "failed": 0, "conflict": 0, "waiting_for_link": 0}
    now_s = db.iso(now)
    # acknowledgements arrive one round-trip after delivery
    for item in db.all_(conn, "SELECT * FROM sync_queue WHERE status='delivered'"):
        if link == "offline":
            continue
        if db.parse_iso(item["delivered_at"]) + timedelta(seconds=delay) <= now:
            with db.transaction(conn):
                conn.execute("UPDATE sync_queue SET status='acknowledged', acknowledged_at=?, acknowledged_by=? WHERE id=?",
                             (now_s, "ground:flight-surgeon-console (simulated)", item["id"]))
                conn.execute("UPDATE ground_inbox SET acknowledged_at=? WHERE idempotency_key=?", (now_s, item["idempotency_key"]))
                if item["item_type"] == "medical_report":
                    conn.execute("UPDATE medical_reports SET sync_status='acknowledged' WHERE id=?", (item["item_id"],))
            counts["acknowledged"] += 1
            BUS.publish("sync.updated", {"id": item["id"], "status": "acknowledged", "item_type": item["item_type"]})
    due = db.all_(conn, "SELECT * FROM sync_queue WHERE status IN ('pending','failed') AND next_attempt_at<=? "
                        "ORDER BY priority, created_at LIMIT 50", (now_s,))
    for item in due:
        if link == "offline":
            counts["waiting_for_link"] += 1
            continue
        cur = _current_hash(conn, item)
        with db.transaction(conn):
            if cur is not None and cur != item["payload_hash"]:
                conn.execute("UPDATE sync_queue SET status='conflict', last_error=? WHERE id=?",
                             ("local record changed after queuing; newer version must be queued", item["id"]))
                counts["conflict"] += 1
                continue
            attempts = item["attempts"] + 1
            failed = link == "degraded" and rng.random() < 0.4
            if failed:
                backoff = min(MAX_BACKOFF_S, 5 * 2 ** (attempts - 1))
                conn.execute("UPDATE sync_queue SET status='failed', attempts=?, last_attempt_at=?, next_attempt_at=?, last_error=? WHERE id=?",
                             (attempts, now_s, db.iso(now + timedelta(seconds=backoff)), "transmission error (degraded link)", item["id"]))
                counts["failed"] += 1
                continue
            result = GROUND.receive(conn, item)
            if result == "conflict":
                conn.execute("UPDATE sync_queue SET status='conflict', attempts=?, last_attempt_at=?, last_error=? WHERE id=?",
                             (attempts, now_s, "ground holds different content for this idempotency key", item["id"]))
                counts["conflict"] += 1
                continue
            # delivery completes after the one-way light time
            delivered_at = db.iso(now + timedelta(seconds=delay))
            conn.execute("UPDATE sync_queue SET status='delivered', attempts=?, last_attempt_at=?, delivered_at=?, last_error=NULL WHERE id=?",
                         (attempts, now_s, delivered_at, item["id"]))
            if item["item_type"] == "medical_report":
                conn.execute("UPDATE medical_reports SET sync_status='transmitted' WHERE id=?", (item["item_id"],))
            counts["sent"] += 1
        BUS.publish("sync.updated", {"id": item["id"], "status": "delivered", "item_type": item["item_type"]})
    return counts


def status(conn) -> dict:
    mission = db.one(conn, "SELECT id, earth_link_status, comm_delay_seconds FROM missions ORDER BY start_utc DESC LIMIT 1")
    rows = db.all_(conn, "SELECT status, COUNT(*) c FROM sync_queue GROUP BY status")
    items = db.all_(conn, "SELECT id, item_type, item_id, status, attempts, priority, created_at, last_attempt_at, next_attempt_at, "
                          "delivered_at, acknowledged_at, acknowledged_by, last_error, is_private FROM sync_queue "
                          "ORDER BY created_at DESC LIMIT 100")
    return {"mission_id": mission["id"] if mission else None,
            "earth_link_status": mission["earth_link_status"] if mission else None,
            "comm_delay_seconds": mission["comm_delay_seconds"] if mission else None,
            "counts": {r["status"]: r["c"] for r in rows}, "items": items,
            "ground_segment": "SIMULATED in-process ground station (prototype)"}


def set_link(conn, actor, status_value: str, delay: float | None) -> dict:
    with db.transaction(conn):
        if delay is None:
            conn.execute("UPDATE missions SET earth_link_status=?", (status_value,))
        else:
            conn.execute("UPDATE missions SET earth_link_status=?, comm_delay_seconds=?", (status_value, delay))
        audit.record(conn, actor, "sync.set_link", "mission", None, {"status": status_value, "delay": delay})
    BUS.publish("sync.link", {"earth_link_status": status_value, "comm_delay_seconds": delay})
    return status(conn)


def retry(conn, actor, qid: str) -> None:
    with db.transaction(conn):
        conn.execute("UPDATE sync_queue SET status='pending', next_attempt_at=? WHERE id=? AND status IN ('failed','conflict')",
                     (db.now_iso(), qid))
        audit.record(conn, actor, "sync.retry", "sync_queue", qid, {})


class SyncWorker(threading.Thread):
    def __init__(self, interval: float = 2.0):
        super().__init__(daemon=True, name="astra-sync")
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.wait(self.interval):
            try:
                with db.session() as conn:
                    process(conn)
            except Exception as exc:  # keep worker alive; errors are visible in logs
                print("[sync] error:", exc)
