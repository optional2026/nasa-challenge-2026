"""Trend analysis: baseline comparison, recent vs historical, sustained and rapid
changes, missing sequences and aggregation for charts. Every result lists the
observation IDs it was computed from so the user can inspect them."""
from __future__ import annotations

import statistics
from datetime import timedelta

from .. import db
from . import baselines

MIN_SD_FRACTION = 0.002  # guards against near-zero SD (0.2% of |mean|)


def effective_sd(b: dict) -> float:
    sd = b["sd"] or 0.0
    floor = max(abs(b["mean"] or 0.0) * MIN_SD_FRACTION, 1e-6)
    return max(sd, floor)


def zscore(value: float, b: dict) -> float:
    return (value - b["mean"]) / effective_sd(b)


def series(conn, astronaut_id: str | None, metric: str, start: str | None = None, end: str | None = None,
           context_key: str | None = None, valid_only: bool = False, location: str | None = None,
           limit: int = 5000) -> list[dict]:
    sql = "SELECT * FROM observations WHERE metric_code=?"
    params: list = [metric]
    if astronaut_id is None:
        sql += " AND astronaut_id IS NULL"
    else:
        sql += " AND astronaut_id=?"
        params.append(astronaut_id)
    if start:
        sql += " AND measured_at>=?"
        params.append(start)
    if end:
        sql += " AND measured_at<=?"
        params.append(end)
    if valid_only:
        sql += " AND quality='valid'"
    if location:
        sql += " AND location=?"
        params.append(location)
    sql += " ORDER BY measured_at DESC LIMIT ?"
    params.append(limit)
    rows = db.all_(conn, sql, params)
    rows.reverse()
    if context_key is not None:
        rows = [r for r in rows if baselines.context_key_for(metric, db.loads(r["context"], {})) == context_key]
    return rows


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {"n": len(values), "mean": round(statistics.fmean(values), 3),
            "sd": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values)}


def slope_per_day(rows: list[dict]) -> float | None:
    pts = [(db.parse_iso(r["measured_at"]).timestamp() / 86400.0, r["value_num"]) for r in rows if r["value_num"] is not None]
    if len(pts) < 3:
        return None
    xs, ys = zip(*pts)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in pts) / den, 4)


def analyze(conn, astronaut_id: str, metric: str, days: float = 14, recent_days: float = 3,
            context_key: str | None = None, end: str | None = None, k_sd: float = 2.5,
            expected_interval_hours: float | None = None) -> dict:
    if context_key is None:
        context_key = "resting" if metric == "heart_rate" else ("daily_total" if metric in baselines.DAILY_TOTAL_METRICS else "")
    end_dt = db.parse_iso(end) if end else db.utcnow()
    start = db.iso(end_dt - timedelta(days=days))
    rows = series(conn, astronaut_id, metric, start=start, end=db.iso(end_dt), context_key=context_key)
    valid = [r for r in rows if r["quality"] == "valid" and r["value_num"] is not None]
    recent_cut = db.iso(end_dt - timedelta(days=recent_days))
    recent = [r for r in valid if r["measured_at"] >= recent_cut]
    older = [r for r in valid if r["measured_at"] < recent_cut]
    b = baselines.approved(conn, astronaut_id, metric, context_key)
    out: dict = {
        "astronaut_id": astronaut_id, "metric_code": metric, "context_key": context_key,
        "period": {"start": start, "end": db.iso(end_dt), "recent_start": recent_cut},
        "baseline": None, "historical": stats([r["value_num"] for r in older]),
        "recent": stats([r["value_num"] for r in recent]), "slope_per_day": slope_per_day(valid),
        "consecutive_beyond_baseline": 0, "latest_z": None, "rapid_changes": [], "gaps": [],
        "quality_counts": {}, "observation_ids": [r["id"] for r in rows], "findings": [],
    }
    for r in rows:
        out["quality_counts"][r["quality"]] = out["quality_counts"].get(r["quality"], 0) + 1
    if b:
        out["baseline"] = {k: b[k] for k in ("id", "version", "mean", "sd", "n", "ref_low", "ref_high",
                                             "approved_by", "approved_at", "period_start", "period_end", "source")}
        if valid:
            zs = [zscore(r["value_num"], b) for r in valid]
            out["latest_z"] = round(zs[-1], 2)
            sign = 1 if zs[-1] > 0 else -1
            c = 0
            for z in reversed(zs):
                if abs(z) > k_sd and (1 if z > 0 else -1) == sign:
                    c += 1
                else:
                    break
            out["consecutive_beyond_baseline"] = c
            for prev, cur in zip(valid, valid[1:]):
                gap_min = (db.parse_iso(cur["measured_at"]) - db.parse_iso(prev["measured_at"])).total_seconds() / 60
                if gap_min <= 120 and abs(cur["value_num"] - prev["value_num"]) / effective_sd(b) > 4:
                    out["rapid_changes"].append({"from": prev["id"], "to": cur["id"], "delta": round(cur["value_num"] - prev["value_num"], 2)})
            if out["recent"]["n"]:
                out["recent_vs_baseline_sd"] = round((out["recent"]["mean"] - b["mean"]) / effective_sd(b), 2)
    else:
        out["findings"].append("No approved individual baseline: comparison is informational only.")
    if expected_interval_hours and rows:
        times = [db.parse_iso(r["measured_at"]) for r in rows] + [end_dt]
        for a, c in zip(times, times[1:]):
            h = (c - a).total_seconds() / 3600
            if h > 2 * expected_interval_hours:
                out["gaps"].append({"from": db.iso(a), "to": db.iso(c), "hours": round(h, 1)})
    if out["slope_per_day"] is not None and out["historical"]["n"] and out["recent"]["n"]:
        out["findings"].append(f"Recent mean {out['recent']['mean']} vs earlier mean {out['historical']['mean']} in this period.")
    return out


def aggregate(rows: list[dict], bucket: str) -> list[dict]:
    """Bucketed mean/min/max for numeric observations (UTC buckets)."""
    if bucket == "raw":
        return rows
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("value_num") is None:
            continue
        dt = db.parse_iso(r["measured_at"])
        if bucket == "hour":
            key = dt.strftime("%Y-%m-%dT%H:00:00.000Z")
        elif bucket == "day":
            key = dt.strftime("%Y-%m-%dT00:00:00.000Z")
        else:
            monday = dt - timedelta(days=dt.weekday())
            key = monday.strftime("%Y-%m-%dT00:00:00.000Z")
        groups.setdefault(key, []).append(r)
    out = []
    for key in sorted(groups):
        vals = [g["value_num"] for g in groups[key]]
        out.append({"bucket_start": key, "mean": round(statistics.fmean(vals), 3), "min": min(vals), "max": max(vals),
                    "count": len(vals), "sum": round(sum(vals), 3),
                    "quality_questionable": sum(1 for g in groups[key] if g["quality"] != "valid"),
                    "observation_ids": [g["id"] for g in groups[key]][:200]})
    return out
