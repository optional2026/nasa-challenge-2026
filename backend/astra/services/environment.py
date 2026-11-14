"""Environmental monitoring subsystem: cabin conditions, radiation history,
exposure events. Environmental readings are stored as observations with
subject_type='environment' (no astronaut) so they are never confused with
direct medical measurements. Temporal overlap with medical observations is
displayed but never presented as causation."""
from __future__ import annotations

from datetime import timedelta

from .. import db
from ..bus import BUS
from . import knowledge, trends

ENV_METRICS = ["cabin_co2", "cabin_o2", "cabin_temperature", "cabin_humidity", "air_tvoc", "air_pm25",
               "radiation_dose_rate", "radiation_dose_cumulative"]


def track_event(conn, *, rule, event_type, location, active, value, unit, obs_ids, anchor, description,
                track_peak=False) -> str | None:
    """Open/update/close an environment event for (type, location)."""
    mission = db.one(conn, "SELECT id FROM missions ORDER BY start_utc DESC LIMIT 1")
    open_ev = db.one(conn, "SELECT * FROM environment_events WHERE event_type=? AND location IS ? AND ended_at IS NULL",
                     (event_type, location))
    synthetic = bool(db.one(conn, "SELECT MAX(is_synthetic) s FROM observations WHERE id IN (%s)" % ",".join("?" * len(obs_ids)),
                            obs_ids)["s"]) if obs_ids else False
    sim = db.one(conn, "SELECT sim_run_id FROM observations WHERE id=?", (obs_ids[-1],))["sim_run_id"] if obs_ids else None
    if active and not open_ev:
        eid = db.new_id("ENV")
        db.insert(conn, "environment_events", {
            "id": eid, "mission_id": mission["id"], "event_type": event_type, "severity": rule["severity"],
            "location": location, "started_at": anchor, "ended_at": None, "peak_value": value, "unit": unit,
            "description": description, "rule_id": rule["id"], "alert_id": None, "is_synthetic": int(synthetic),
            "sim_run_id": sim})
        conn.executemany("INSERT OR IGNORE INTO environment_event_observations VALUES (?,?)", [(eid, o) for o in obs_ids])
        BUS.publish("environment.warning", {"id": eid, "event_type": event_type, "location": location,
                                            "severity": rule["severity"], "description": description})
        return eid
    if active and open_ev:
        if track_peak and value > (open_ev["peak_value"] or 0):
            conn.execute("UPDATE environment_events SET peak_value=?, description=? WHERE id=?", (value, description, open_ev["id"]))
        elif not track_peak:
            conn.execute("UPDATE environment_events SET peak_value=MAX(COALESCE(peak_value,0),?) WHERE id=?", (value, open_ev["id"]))
        conn.executemany("INSERT OR IGNORE INTO environment_event_observations VALUES (?,?)", [(open_ev["id"], o) for o in obs_ids[-5:]])
        return open_ev["id"]
    if not active and open_ev:
        conn.execute("UPDATE environment_events SET ended_at=? WHERE id=?", (anchor, open_ev["id"]))
        BUS.publish("environment.event_ended", {"id": open_ev["id"], "event_type": event_type, "location": location})
    return None


def latest_readings(conn, mission_id: str) -> list[dict]:
    out = []
    for m in ENV_METRICS:
        rows = db.all_(conn, """SELECT o.* FROM observations o JOIN (SELECT location, MAX(measured_at) mt FROM observations
                                WHERE mission_id=? AND metric_code=? AND astronaut_id IS NULL GROUP BY location) x
                                ON x.location IS o.location AND x.mt=o.measured_at
                                WHERE o.mission_id=? AND o.metric_code=? AND o.astronaut_id IS NULL""", (mission_id, m, mission_id, m))
        ind = knowledge.indicators()[m]
        for r in rows:
            age_min = (db.utcnow() - db.parse_iso(r["measured_at"])).total_seconds() / 60
            out.append({"metric_code": m, "name": ind["name"], "location": r["location"], "value": r["value_num"],
                        "unit": r["unit"], "measured_at": r["measured_at"], "age_minutes": round(age_min, 1),
                        "device_id": r["device_id"], "quality": r["quality"], "observation_id": r["id"],
                        "is_synthetic": bool(r["is_synthetic"])})
    return out


def events(conn, mission_id: str, hours: float = 24 * 30, open_only: bool = False) -> list[dict]:
    start = db.iso(db.utcnow() - timedelta(hours=hours))
    sql = "SELECT * FROM environment_events WHERE mission_id=? AND (started_at>=? OR ended_at IS NULL)"
    if open_only:
        sql += " AND ended_at IS NULL"
    rows = db.all_(conn, sql + " ORDER BY started_at DESC", (mission_id, start))
    for r in rows:
        r["is_synthetic"] = bool(r["is_synthetic"])
        r["observation_ids"] = [x["observation_id"] for x in db.all_(conn, "SELECT observation_id FROM environment_event_observations WHERE event_id=?", (r["id"],))]
    return rows


def radiation_summary(conn, mission_id: str, astronaut_id: str | None = None) -> dict:
    """Mission exposure: latest cumulative dose per dosimeter, current dose rates, event history."""
    dosimeters = db.all_(conn, """SELECT o.device_id, o.astronaut_id, o.location, o.value_num AS cumulative_mGy, o.measured_at,
                                  d.model, d.serial FROM observations o
                                  JOIN (SELECT device_id, MAX(measured_at) mt FROM observations WHERE mission_id=?
                                        AND metric_code='radiation_dose_cumulative' GROUP BY device_id) x
                                  ON x.device_id=o.device_id AND x.mt=o.measured_at
                                  LEFT JOIN devices d ON d.id=o.device_id
                                  WHERE o.metric_code='radiation_dose_cumulative' AND o.mission_id=?""", (mission_id, mission_id))
    if astronaut_id is not None:
        dosimeters = [d for d in dosimeters if d["astronaut_id"] in (None, astronaut_id)]
    rad_events = [e for e in events(conn, mission_id, hours=24 * 3650) if e["event_type"] == "radiation_event"]
    return {"dosimeters": dosimeters, "events": rad_events,
            "units": {"dose_rate": "uGy/h (absorbed dose rate)", "cumulative": "mGy (absorbed dose)"},
            "note": "Absorbed dose (Gy) is not effective dose (Sv). Exposure records are not a diagnosis."}


def overlay(conn, mission_id: str, astronaut_id: str, metric_code: str, env_metric: str, hours: float = 240) -> dict:
    """Medical series alongside an environmental series and events. Association only, never causation."""
    start = db.iso(db.utcnow() - timedelta(hours=hours))
    med = trends.series(conn, astronaut_id, metric_code, start=start)
    env = trends.series(conn, None, env_metric, start=start)
    return {"medical": [{"t": r["measured_at"], "v": r["value_num"], "id": r["id"]} for r in med],
            "environment": [{"t": r["measured_at"], "v": r["value_num"], "id": r["id"], "location": r["location"]} for r in env],
            "events": events(conn, mission_id, hours=hours),
            "disclaimer": "Shown together for context only. A temporal relationship does not establish causation."}
