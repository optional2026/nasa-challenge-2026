"""Individual baselines.

A baseline is computed ONLY from observations whose quality is 'valid'
inside an explicit period, stored as a versioned DRAFT, and becomes active
only after approval by authorized medical personnel. New observations never
silently redefine an approved baseline.
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from .. import audit, db
from ..bus import BUS
from ..security import Principal

# metrics whose baseline is computed from daily totals instead of single observations
DAILY_TOTAL_METRICS = {"water_intake", "energy_intake"}


def context_key_for(metric: str, context: dict | None) -> str:
    context = context or {}
    if metric == "heart_rate":
        act = context.get("activity")
        return "resting" if act in (None, "", "resting") else str(act)
    if metric in ("physical_performance", "balance_assessment", "coordination_test"):
        return str(context.get("test") or "")
    if metric in DAILY_TOTAL_METRICS:
        return "daily_total"
    return ""


def daily_totals(rows: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        totals[r["measured_at"][:10]] += r["value_num"] or 0.0
    return dict(totals)


def _window_values(conn, astronaut_id: str, metric: str, context_key: str, start: str, end: str):
    rows = db.all_(conn, """SELECT id, value_num, measured_at, context FROM observations
                            WHERE astronaut_id=? AND metric_code=? AND measured_at>=? AND measured_at<=?
                              AND quality='valid' AND value_num IS NOT NULL ORDER BY measured_at""",
                   (astronaut_id, metric, start, end))
    rows = [r for r in rows if context_key_for(metric, db.loads(r["context"], {})) == context_key]
    if metric in DAILY_TOTAL_METRICS:
        totals = daily_totals(rows)
        return list(totals.values()), [r["id"] for r in rows]
    return [r["value_num"] for r in rows], [r["id"] for r in rows]


def propose(conn, actor: Principal | str, astronaut_id: str, metric: str, start: str, end: str,
            source: str = "in_flight_window", context_key: str = "", notes: str | None = None,
            synthetic: bool = False) -> dict:
    values, obs_ids = _window_values(conn, astronaut_id, metric, context_key, start, end)
    if len(values) < 3:
        raise ValueError(f"at least 3 valid observations are required in the period (found {len(values)})")
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    prev = db.one(conn, """SELECT MAX(version) v FROM health_baselines WHERE astronaut_id=? AND metric_code=?
                           AND context_key=?""", (astronaut_id, metric, context_key))
    version = (prev["v"] or 0) + 1
    bid = db.new_id("BL")
    days = max(1, round((db.parse_iso(end) - db.parse_iso(start)).total_seconds() / 86400))
    actor_name = actor.actor if isinstance(actor, Principal) else actor
    with db.transaction(conn):
        db.insert(conn, "health_baselines", {
            "id": bid, "astronaut_id": astronaut_id, "metric_code": metric, "context_key": context_key,
            "version": version, "status": "draft", "source": source, "mean": round(mean, 4), "sd": round(sd, 4),
            "n": len(values), "ref_low": None, "ref_high": None, "ref_approved_by": None,
            "period_start": start, "period_end": end, "establishment_days": days,
            "created_by": actor_name, "created_at": db.now_iso(), "approved_by": None, "approved_at": None,
            "notes": notes, "is_synthetic": int(synthetic),
        })
        conn.executemany("INSERT INTO baseline_observations VALUES (?,?)", [(bid, o) for o in obs_ids])
        audit.record(conn, actor, "baseline.propose", "health_baseline", bid,
                     {"metric": metric, "context_key": context_key, "n": len(values), "version": version})
    return get(conn, bid)


def approve(conn, actor: Principal, baseline_id: str, ref_low=None, ref_high=None, notes=None) -> dict:
    b = db.one(conn, "SELECT * FROM health_baselines WHERE id=?", (baseline_id,))
    if not b:
        raise LookupError(baseline_id)
    if b["status"] != "draft":
        raise ValueError(f"only draft baselines can be approved (status={b['status']})")
    if (ref_low is None) != (ref_high is None) or (ref_low is not None and ref_low >= ref_high):
        raise ValueError("reference range requires ref_low < ref_high (or neither)")
    now = db.now_iso()
    with db.transaction(conn):
        conn.execute("""UPDATE health_baselines SET status='retired' WHERE astronaut_id=? AND metric_code=?
                        AND context_key=? AND status='approved'""", (b["astronaut_id"], b["metric_code"], b["context_key"]))
        db.update(conn, "health_baselines", "id", baseline_id, {
            "status": "approved", "approved_by": actor.actor, "approved_at": now,
            "ref_low": ref_low, "ref_high": ref_high, "ref_approved_by": actor.actor if ref_low is not None else None,
            "notes": notes if notes is not None else b["notes"]})
        audit.record(conn, actor, "baseline.approve", "health_baseline", baseline_id,
                     {"ref_low": ref_low, "ref_high": ref_high})
    BUS.publish("baseline.updated", {"id": baseline_id, "metric_code": b["metric_code"]}, astronaut_id=b["astronaut_id"])
    return get(conn, baseline_id)


def retire(conn, actor: Principal, baseline_id: str) -> dict:
    with db.transaction(conn):
        conn.execute("UPDATE health_baselines SET status='retired' WHERE id=?", (baseline_id,))
        audit.record(conn, actor, "baseline.retire", "health_baseline", baseline_id, {})
    return get(conn, baseline_id)


def get(conn, baseline_id: str) -> dict | None:
    b = db.one(conn, "SELECT * FROM health_baselines WHERE id=?", (baseline_id,))
    if b:
        b["is_synthetic"] = bool(b["is_synthetic"])
        b["observation_count"] = db.one(conn, "SELECT COUNT(*) c FROM baseline_observations WHERE baseline_id=?", (baseline_id,))["c"]
    return b


def approved(conn, astronaut_id: str, metric: str, context_key: str = "") -> dict | None:
    return db.one(conn, """SELECT * FROM health_baselines WHERE astronaut_id=? AND metric_code=? AND context_key=?
                           AND status='approved' ORDER BY version DESC LIMIT 1""", (astronaut_id, metric, context_key))


def list_for(conn, astronaut_id: str, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM health_baselines WHERE astronaut_id=?"
    params: list = [astronaut_id]
    if status:
        sql += " AND status=?"
        params.append(status)
    rows = db.all_(conn, sql + " ORDER BY metric_code, context_key, version DESC", params)
    for r in rows:
        r["is_synthetic"] = bool(r["is_synthetic"])
    return rows
