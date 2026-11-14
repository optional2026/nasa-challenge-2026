"""Routes: environment, daily routine, simulator control, synchronization, audit, health."""
from __future__ import annotations

from datetime import timedelta

from .. import audit, db, schemas
from ..services import environment, knowledge, sync, trends
from .common import default_mission, map_errors, mission_day, scoped_astronaut
from .framework import Api, ApiError, Ctx
from .routes_data import ALL_USERS, HEALTH_ROLES

SIM_ROLES = ("astronaut", "medical_officer", "flight_surgeon", "admin")


def routine_tasks(conn, ast: str) -> list[dict]:
    """Today's required assessments with due status computed from the schedule and the latest records."""
    now = db.utcnow()
    today = db.iso(now.replace(hour=0, minute=0, second=0, microsecond=0))
    out = []
    for t in db.all_(conn, "SELECT * FROM assessment_schedule WHERE astronaut_id=? AND active=1 ORDER BY required DESC, id", (ast,)):
        codes = db.loads(t["metric_codes"], [])
        q = ",".join("?" * len(codes))
        last = db.one(conn, f"SELECT MAX(measured_at) m FROM observations WHERE astronaut_id=? AND metric_code IN ({q})", (ast, *codes))["m"]
        history = db.all_(conn, f"SELECT substr(measured_at,1,10) d, COUNT(*) c FROM observations WHERE astronaut_id=? "
                                f"AND metric_code IN ({q}) AND measured_at>=? GROUP BY d ORDER BY d", (ast, *codes, db.iso(now - timedelta(days=7))))
        age_h = (now - db.parse_iso(last)).total_seconds() / 3600 if last else None
        if age_h is None:
            status = "never_recorded"
        elif t["interval_hours"] <= 24 and last >= today:
            status = "done"
        elif t["interval_hours"] > 24 and age_h < t["interval_hours"]:
            status = "done"
        elif age_h > 2 * t["interval_hours"]:
            status = "overdue"
        else:
            status = "due"
        out.append({"task_code": t["task_code"], "title": t["title"], "metric_codes": codes, "interval_hours": t["interval_hours"],
                    "required": bool(t["required"]), "clinician_directed": bool(t["clinician_directed"]), "last_recorded_at": last,
                    "age_hours": round(age_h, 1) if age_h is not None else None, "status": status,
                    "completion_history": {h["d"]: h["c"] for h in history}})
    return out


def register(api: Api) -> None:
    # ---------------------------------------------------------------- environment
    @api.route("GET", "/environment", summary="Environment status: latest readings, open events, mission phase", tags=["environment"],
               roles=ALL_USERS)
    def env_status(ctx: Ctx):
        m = default_mission(ctx.conn)
        phase = db.one(ctx.conn, "SELECT * FROM mission_environments WHERE mission_id=? AND start_utc<=? ORDER BY start_utc DESC LIMIT 1",
                       (m["id"], db.now_iso()))
        return {"mission_id": m["id"], "mission_name": m["name"], "mission_day": mission_day(m), "phase": phase,
                "phases": db.all_(ctx.conn, "SELECT * FROM mission_environments WHERE mission_id=? ORDER BY start_utc", (m["id"],)),
                "readings": environment.latest_readings(ctx.conn, m["id"]),
                "open_events": environment.events(ctx.conn, m["id"], open_only=True),
                "note": "Environmental sensor readings describe the cabin, not an astronaut."}

    @api.route("GET", "/environment/history", summary="Environmental history (optionally bucketed)", tags=["environment"],
               query=schemas.EnvironmentQuery, roles=ALL_USERS)
    def env_history(ctx: Ctx):
        q = ctx.query
        metrics = [q.metric_code] if q.metric_code else environment.ENV_METRICS
        start = db.hours_ago(q.hours)
        out = {}
        for mc in metrics:
            if mc not in knowledge.indicators():
                raise ApiError(422, "invalid", f"unknown metric {mc}")
            rows = trends.series(ctx.conn, None, mc, start=start, location=q.location, limit=20000)
            out[mc] = {"unit": knowledge.indicators()[mc]["canonical_unit"],
                       "points": [{"t": r["measured_at"], "v": r["value_num"], "location": r["location"], "id": r["id"],
                                   "synthetic": bool(r["is_synthetic"])} for r in rows]}
        return {"hours": q.hours, "series": out}

    @api.route("GET", "/environment/events", summary="Environmental events", tags=["environment"], query=schemas.EnvironmentQuery,
               roles=ALL_USERS)
    def env_events(ctx: Ctx):
        m = default_mission(ctx.conn)
        return environment.events(ctx.conn, m["id"], hours=ctx.query.hours)

    @api.route("GET", "/environment/radiation", summary="Radiation exposure history and dosimeters", tags=["environment"],
               roles=ALL_USERS)
    def env_radiation(ctx: Ctx):
        m = default_mission(ctx.conn)
        ast = ctx.principal.astronaut_id if ctx.principal.role == "astronaut" else None
        data = environment.radiation_summary(ctx.conn, m["id"], ast)
        hours = int(ctx.request.query_params.get("hours", 240))
        rows = trends.series(ctx.conn, None, "radiation_dose_rate", start=db.hours_ago(hours), limit=20000)
        data["area_dose_rate"] = [{"t": r["measured_at"], "v": r["value_num"], "location": r["location"], "id": r["id"]} for r in rows]
        if ast or ctx.principal.role in ("medical_officer", "flight_surgeon"):
            target = ast or ctx.request.query_params.get("astronaut_id")
            if target:
                scoped_astronaut(ctx, target)
                pr = trends.series(ctx.conn, target, "radiation_dose_cumulative", start=db.hours_ago(hours), limit=20000)
                data["personal_cumulative"] = [{"t": r["measured_at"], "v": r["value_num"], "id": r["id"]} for r in pr]
        return data

    @api.route("GET", "/environment/overlay", summary="Medical series alongside an environmental series (context only)",
               tags=["environment"], roles=HEALTH_ROLES)
    def env_overlay(ctx: Ctx):
        qp = ctx.request.query_params
        ast = scoped_astronaut(ctx, qp.get("astronaut_id"))
        m = default_mission(ctx.conn)
        metric, env_metric = qp.get("metric_code", "heart_rate"), qp.get("env_metric", "cabin_co2")
        if knowledge.indicators().get(metric, {}).get("privacy") == "private":
            raise ApiError(403, "forbidden", "private indicators are not available in overlays")
        return environment.overlay(ctx.conn, m["id"], ast, metric, env_metric, float(qp.get("hours", 240)))

    # ---------------------------------------------------------------- routine
    @api.route("GET", "/routine", summary="Today's required assessments and completion history", tags=["views"],
               query=schemas.AstronautQuery, roles=HEALTH_ROLES)
    def routine(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        devs = db.all_(ctx.conn, "SELECT id, device_type, model, status, last_seen_at, battery_pct, is_simulated, hardware_validated "
                                 "FROM devices WHERE astronaut_id IS NULL OR astronaut_id=? ORDER BY id", (ast,))
        for d in devs:
            d["is_simulated"] = bool(d["is_simulated"])
            d["hardware_validated"] = bool(d["hardware_validated"])
        return {"astronaut_id": ast, "date_utc": db.now_iso()[:10], "tasks": routine_tasks(ctx.conn, ast), "devices": devs}

    # ---------------------------------------------------------------- simulator
    from simulator.source import RUNNER

    def _sim(fn):
        try:
            return fn()
        except (RuntimeError, ValueError) as e:
            raise ApiError(409, "simulator_state", str(e))

    @api.route("GET", "/simulator", summary="Simulator status (SYNTHETIC data source)", tags=["simulator"], roles=SIM_ROLES)
    def sim_status(ctx: Ctx):
        return RUNNER.status()

    @api.route("POST", "/simulator/start", summary="Start a scenario", tags=["simulator"], body=schemas.SimulatorStartIn, roles=SIM_ROLES)
    def sim_start(ctx: Ctx):
        b = ctx.body
        res = _sim(lambda: RUNNER.start(b.scenario, b.speed, b.days, b.seed))
        with db.transaction(ctx.conn):
            audit.record(ctx.conn, ctx.principal, "simulator.start", "simulator", res["run_id"], b.model_dump())
        return res

    @api.route("POST", "/simulator/pause", summary="Pause", tags=["simulator"], roles=SIM_ROLES)
    def sim_pause(ctx: Ctx):
        return _sim(RUNNER.pause)

    @api.route("POST", "/simulator/resume", summary="Resume", tags=["simulator"], roles=SIM_ROLES)
    def sim_resume(ctx: Ctx):
        return _sim(RUNNER.resume)

    @api.route("POST", "/simulator/stop", summary="Stop", tags=["simulator"], roles=SIM_ROLES)
    def sim_stop(ctx: Ctx):
        res = _sim(RUNNER.stop)
        with db.transaction(ctx.conn):
            audit.record(ctx.conn, ctx.principal, "simulator.stop", "simulator", res["run_id"], {})
        return res

    @api.route("POST", "/simulator/speed", summary="Change speed", tags=["simulator"], body=schemas.SimulatorSpeedIn, roles=SIM_ROLES)
    def sim_speed(ctx: Ctx):
        return _sim(lambda: RUNNER.set_speed(ctx.body.speed))

    @api.route("POST", "/simulator/reset", summary="Stop and delete all simulator-generated records", tags=["simulator"],
               roles=SIM_ROLES)
    def sim_reset(ctx: Ctx):
        return _sim(lambda: RUNNER.reset(ctx.principal))

    # ---------------------------------------------------------------- sync
    @api.route("GET", "/sync", summary="Synchronization queue and Earth-link status", tags=["sync"], roles=ALL_USERS)
    def sync_status(ctx: Ctx):
        st = sync.status(ctx.conn)
        if ctx.principal.role == "astronaut":
            for it in st["items"]:
                if it["is_private"]:
                    it["item_id"] = "[private]"
        return st

    @api.route("POST", "/sync/link", summary="Set Earth link status / delay (mission operations)", tags=["sync"], body=schemas.LinkIn,
               roles=("admin", "medical_officer", "flight_surgeon", "astronaut"))
    def sync_link(ctx: Ctx):
        return sync.set_link(ctx.conn, ctx.principal, ctx.body.earth_link_status, ctx.body.comm_delay_seconds)

    @api.route("POST", "/sync/run", summary="Run one synchronization pass now", tags=["sync"], roles=ALL_USERS)
    def sync_run(ctx: Ctx):
        return {"result": sync.process(ctx.conn), "status": sync.status(ctx.conn)}

    @api.route("POST", "/sync/{queue_id}/retry", summary="Retry a failed or conflicted item", tags=["sync"], roles=ALL_USERS)
    def sync_retry(ctx: Ctx):
        sync.retry(ctx.conn, ctx.principal, ctx.path["queue_id"])
        return sync.status(ctx.conn)

    # ---------------------------------------------------------------- audit / health
    @api.route("GET", "/audit", summary="Audit log (administrator, flight surgeon)", tags=["audit"], query=schemas.ListQuery,
               roles=("admin", "flight_surgeon"))
    def audit_list(ctx: Ctx):
        rows = db.all_(ctx.conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?", (ctx.query.limit, ctx.query.offset))
        for r in rows:
            r["details"] = db.loads(r["details"], {})
        return rows

    @api.route("GET", "/health", summary="Service health", tags=["system"], auth="none")
    def health(ctx: Ctx):
        n = db.one(ctx.conn, "SELECT COUNT(*) c FROM observations")["c"]
        return {"status": "ok", "observations": n, "external_dependencies": "none (offline-capable)", "time": db.now_iso()}
