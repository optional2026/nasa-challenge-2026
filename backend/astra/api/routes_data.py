"""Routes: authentication, crew/mission, devices, telemetry, measurements,
knowledge base, daily records."""
from __future__ import annotations

from .. import audit, db, schemas, security
from ..devices.adapters import ADAPTERS, AdapterError, adapter_for
from ..security import MEDICAL_ROLES, can_view_private
from ..services import ingestion, knowledge, records, trends
from .common import default_mission, filter_private, map_errors, mission_day, scoped_astronaut
from .framework import Api, ApiError, Ctx, forbidden, not_found

ALL_USERS = ("astronaut", "medical_officer", "flight_surgeon", "admin")
HEALTH_ROLES = ("astronaut", "medical_officer", "flight_surgeon")  # may create/act on health records
# may READ health views; the Earth-based administrator gets read-only, privacy-filtered access (no clinical actions)
VIEW_ROLES = HEALTH_ROLES + ("admin",)
MED = MEDICAL_ROLES


def register(api: Api) -> None:
    # ---------------------------------------------------------------- auth
    @api.route("POST", "/auth/login", summary="Log in and receive a session token", tags=["auth"], body=schemas.LoginIn,
               response=schemas.LoginOut, auth="none")
    def login(ctx: Ctx):
        """Every role (astronaut, Crew Medical Officer, flight surgeon, administrator) signs in with a username and
        password. The password is verified against its scrypt hash; the same error is returned for an unknown user,
        a deactivated user and a wrong password. Role and permissions come from the server-side user record."""
        u = db.one(ctx.conn, "SELECT * FROM users WHERE username=? AND active=1", (ctx.body.username,))
        if not u or not security.verify_password(ctx.body.password, u["password_hash"]):
            with db.transaction(ctx.conn):
                audit.record(ctx.conn, f"anonymous:{ctx.body.username}", "auth.login_failed", "user", ctx.body.username, {})
            raise ApiError(401, "invalid_credentials", "invalid username or password")
        from .. import sides
        if not sides.role_allowed(u["role"]):  # checked after the password, so it reveals nothing to strangers
            with db.transaction(ctx.conn):
                audit.record(ctx.conn, f"user:{u['username']}", "auth.login_wrong_side", "user", str(u["id"]), {})
            raise ApiError(403, "wrong_side", sides.wrong_side_message(u["role"]))
        with db.transaction(ctx.conn):
            audit.record(ctx.conn, f"user:{u['username']}", "auth.login", "user", str(u["id"]), {})
        return {"token": security.issue_token(u), "user": _user_public(u)}

    @api.route("GET", "/auth/me", summary="Current user", tags=["auth"])
    def me(ctx: Ctx):
        u = db.one(ctx.conn, "SELECT * FROM users WHERE id=?", (ctx.principal.user_id,))
        return _user_public(u)

    # ---------------------------------------------------------------- user management (administrator)
    @api.route("GET", "/users", summary="List registered users (administrator)", tags=["users"], roles=("admin",))
    def users(ctx: Ctx):
        return [_user_admin(u) for u in db.all_(ctx.conn, """SELECT u.*, a.name astronaut_name, a.call_sign, a.crew_role, a.crew,
                                                                     a.mission_id, u.mission_id user_mission_id, m.name mission_name
                                                              FROM users u LEFT JOIN astronauts a ON a.id=u.astronaut_id
                                                              LEFT JOIN missions m ON m.id=a.mission_id ORDER BY u.id""")]

    @api.route("POST", "/users", summary="Register a crew account (administrator)", tags=["users"], body=schemas.UserCreateIn,
               roles=("admin",), status_code=201)
    def user_create(ctx: Ctx):
        """Creates the astronaut health record (with the standard daily-routine schedule) and the linked account.
        Only astronaut and Crew Medical Officer accounts can be registered; nobody can self-register. A password
        that satisfies the server password policy is required."""
        from ..seed import SCHEDULE
        b = ctx.body
        _check_password(b.password, b.username)
        if db.one(ctx.conn, "SELECT id FROM users WHERE username=?", (b.username,)):
            raise ApiError(409, "username_taken", f"username '{b.username}' is already registered")
        mission_id = b.mission_id or default_mission(ctx.conn)["id"]
        if not db.one(ctx.conn, "SELECT id FROM missions WHERE id=?", (mission_id,)):
            raise not_found("mission", mission_id)
        now = db.now_iso()
        with db.transaction(ctx.conn):
            ast_id = _next_astronaut_id(ctx.conn)
            db.insert(ctx.conn, "astronauts", {"id": ast_id, "mission_id": mission_id, "name": b.name, "call_sign": b.call_sign,
                                               "crew_role": b.crew_role or ("Crew Medical Officer" if b.role == "medical_officer" else "Astronaut"),
                                               "birth_year": b.birth_year, "glucose_monitoring_enabled": 0, "is_synthetic": 0,
                                               "created_at": now, "crew": b.crew})
            for code, title, metrics, interval, required, clin in SCHEDULE:
                db.insert(ctx.conn, "assessment_schedule", {"astronaut_id": ast_id, "task_code": code, "title": title,
                                                            "metric_codes": db.dumps(metrics), "interval_hours": interval,
                                                            "required": required, "clinician_directed": clin, "active": 1})
            # The administrator-chosen initial password is stored only as a salted scrypt hash and never returned.
            db.insert(ctx.conn, "users", {"username": b.username, "display_name": b.display_name,
                                          "password_hash": security.hash_password(b.password),
                                          "role": b.role, "astronaut_id": ast_id, "active": 1, "created_at": now})
            uid = db.one(ctx.conn, "SELECT id FROM users WHERE username=?", (b.username,))["id"]
            audit.record(ctx.conn, ctx.principal, "user.create", "user", str(uid),
                         {"username": b.username, "role": b.role, "astronaut_id": ast_id, "mission_id": mission_id, "crew": b.crew})
        return _user_admin_by_id(ctx.conn, uid)

    @api.route("PATCH", "/users/{user_id}", summary="Edit a user, role (crew roles only) and mission/crew assignment (administrator)",
               tags=["users"], body=schemas.UserUpdateIn, roles=("admin",))
    def user_update(ctx: Ctx):
        u = _user_row(ctx)
        b = ctx.body.model_dump(exclude_unset=True)
        if u["role"] not in security.ADMIN_ASSIGNABLE_ROLES:
            allowed = {"display_name", "mission_id"} if u["role"] == "flight_surgeon" else {"display_name"}
            if set(b) - allowed:
                raise forbidden("only the display name (and, for a flight surgeon, the assigned mission) of Earth-side "
                                "accounts can be edited here")
            if "mission_id" in b and b["mission_id"] is not None and not db.one(ctx.conn, "SELECT id FROM missions WHERE id=?", (b["mission_id"],)):
                raise not_found("mission", b["mission_id"])
            with db.transaction(ctx.conn):
                changes = {k: b[k] for k in b if k == "mission_id" or b[k] is not None}
                if changes:
                    db.update(ctx.conn, "users", "id", u["id"], changes)
                audit.record(ctx.conn, ctx.principal, "user.update", "user", str(u["id"]), {"changes": b, "previous_role": u["role"]})
            return _user_admin_by_id(ctx.conn, u["id"])
        astro_changes = {k: b[k] for k in ("name", "call_sign", "crew_role", "mission_id", "crew") if k in b}
        if "mission_id" in astro_changes and not db.one(ctx.conn, "SELECT id FROM missions WHERE id=?", (astro_changes["mission_id"],)):
            raise not_found("mission", astro_changes["mission_id"])
        if any(astro_changes.get(k) is None for k in ("name", "mission_id", "crew") if k in astro_changes):
            raise ApiError(422, "invalid", "name, mission_id and crew cannot be empty")
        user_changes = {k: b[k] for k in ("display_name", "role") if k in b and b[k] is not None}
        with db.transaction(ctx.conn):
            if user_changes:
                db.update(ctx.conn, "users", "id", u["id"], user_changes)
            if astro_changes and u["astronaut_id"]:
                db.update(ctx.conn, "astronauts", "id", u["astronaut_id"], astro_changes)
            audit.record(ctx.conn, ctx.principal, "user.update", "user", str(u["id"]),
                         {"changes": b, "previous_role": u["role"]})
        return _user_admin_by_id(ctx.conn, u["id"])

    @api.route("POST", "/users/{user_id}/deactivate", summary="Deactivate an account (administrator)", tags=["users"], roles=("admin",))
    def user_deactivate(ctx: Ctx):
        """Signs the account out everywhere (tokens are re-checked on every request) and removes it from the
        sign-in screen. The astronaut's health records are retained."""
        u = _user_row(ctx)
        if u["id"] == ctx.principal.user_id:
            raise ApiError(409, "cannot_deactivate_self", "administrators cannot deactivate their own account")
        with db.transaction(ctx.conn):
            ctx.conn.execute("UPDATE users SET active=0 WHERE id=?", (u["id"],))
            audit.record(ctx.conn, ctx.principal, "user.deactivate", "user", str(u["id"]), {"username": u["username"]})
        return _user_admin_by_id(ctx.conn, u["id"])

    @api.route("POST", "/users/{user_id}/activate", summary="Re-activate an account (administrator)", tags=["users"], roles=("admin",))
    def user_activate(ctx: Ctx):
        u = _user_row(ctx)
        with db.transaction(ctx.conn):
            ctx.conn.execute("UPDATE users SET active=1 WHERE id=?", (u["id"],))
            audit.record(ctx.conn, ctx.principal, "user.activate", "user", str(u["id"]), {"username": u["username"]})
        return _user_admin_by_id(ctx.conn, u["id"])

    @api.route("POST", "/users/{user_id}/password", summary="Set a new password for a crew account (administrator)",
               tags=["users"], body=schemas.PasswordResetIn, roles=("admin",))
    def user_password_reset(ctx: Ctx):
        """Replaces the password hash of an astronaut or Crew Medical Officer account. Existing passwords can never
        be read or retrieved — only replaced. Earth-side demo accounts are managed by server configuration."""
        u = _user_row(ctx)
        if u["role"] not in security.ADMIN_ASSIGNABLE_ROLES:
            raise forbidden("passwords of Earth-side accounts are managed by server configuration, not through user management")
        _check_password(ctx.body.password, u["username"])
        with db.transaction(ctx.conn):
            ctx.conn.execute("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(ctx.body.password), u["id"]))
            audit.record(ctx.conn, ctx.principal, "user.password_reset", "user", str(u["id"]), {"username": u["username"]})
        return _user_admin_by_id(ctx.conn, u["id"])

    def _user_row(ctx: Ctx) -> dict:
        try:
            uid = int(ctx.path["user_id"])
        except ValueError:
            raise not_found("user", ctx.path["user_id"])
        u = db.one(ctx.conn, "SELECT * FROM users WHERE id=?", (uid,))
        if not u:
            raise not_found("user", uid)
        return u

    # ---------------------------------------------------------------- crew / mission
    @api.route("GET", "/missions", summary="Missions", tags=["mission"], roles=ALL_USERS)
    def missions(ctx: Ctx):
        out = []
        for m in db.all_(ctx.conn, "SELECT * FROM missions ORDER BY start_utc DESC"):
            out.append(_mission(ctx.conn, m))
        return out

    @api.route("GET", "/missions/{mission_id}", summary="Mission detail incl. phases", tags=["mission"], roles=ALL_USERS)
    def mission_detail(ctx: Ctx):
        m = db.one(ctx.conn, "SELECT * FROM missions WHERE id=?", (ctx.path["mission_id"],))
        if not m:
            raise not_found("mission", ctx.path["mission_id"])
        return _mission(ctx.conn, m)

    @api.route("GET", "/astronauts", summary="Crew list (no health data)", tags=["crew"], roles=ALL_USERS)
    def astronauts(ctx: Ctx):
        rows = db.all_(ctx.conn, "SELECT id, mission_id, name, call_sign, crew_role, crew, is_synthetic FROM astronauts ORDER BY id")
        for r in rows:
            r["can_view_health"] = security.can_view_astronaut(ctx.principal, r["id"])
        return rows

    @api.route("GET", "/astronauts/{astronaut_id}", summary="Astronaut profile, schedule and medical history", tags=["crew"],
               roles=VIEW_ROLES)
    def astronaut_detail(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.path["astronaut_id"])
        a = db.one(ctx.conn, "SELECT * FROM astronauts WHERE id=?", (ast,))
        a["schedule"] = db.all_(ctx.conn, "SELECT * FROM assessment_schedule WHERE astronaut_id=? ORDER BY id", (ast,))
        for s in a["schedule"]:
            s["metric_codes"] = db.loads(s["metric_codes"], [])
        hist = db.all_(ctx.conn, "SELECT * FROM medical_history WHERE astronaut_id=? ORDER BY recorded_at", (ast,))
        a["medical_history"], a["medical_history_hidden"] = filter_private(ctx, hist) if ctx.principal.role not in MED else (hist, 0)
        a["medications"] = db.all_(ctx.conn, "SELECT * FROM medication_records WHERE astronaut_id=? ORDER BY administered_at DESC", (ast,))
        a["glucose_monitoring_enabled"] = bool(a["glucose_monitoring_enabled"])
        return a

    @api.route("POST", "/astronauts/{astronaut_id}/glucose-monitoring", summary="Enable/disable clinician-directed glucose monitoring",
               tags=["crew"], body=schemas.AlertActionIn, roles=MED)
    def glucose_toggle(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.path["astronaut_id"])
        a = db.one(ctx.conn, "SELECT glucose_monitoring_enabled g FROM astronauts WHERE id=?", (ast,))
        new = 0 if a["g"] else 1
        with db.transaction(ctx.conn):
            ctx.conn.execute("UPDATE astronauts SET glucose_monitoring_enabled=? WHERE id=?", (new, ast))
            ctx.conn.execute("UPDATE assessment_schedule SET active=? WHERE astronaut_id=? AND task_code='glucose'", (new, ast))
            audit.record(ctx.conn, ctx.principal, "astronaut.glucose_monitoring", "astronaut", ast,
                         {"enabled": bool(new), "note": ctx.body.note})
        return {"astronaut_id": ast, "glucose_monitoring_enabled": bool(new)}

    # ---------------------------------------------------------------- devices
    @api.route("GET", "/devices", summary="Devices and connection status", tags=["devices"], roles=ALL_USERS)
    def devices(ctx: Ctx):
        rows = db.all_(ctx.conn, "SELECT * FROM devices ORDER BY id")
        for r in rows:
            r.pop("api_key_hash", None)
            r["metadata"] = db.loads(r["metadata"], {})
            r["is_simulated"] = bool(r["is_simulated"])
            r["hardware_validated"] = bool(r["hardware_validated"])
            if r["last_seen_at"]:
                age = (db.utcnow() - db.parse_iso(r["last_seen_at"])).total_seconds()
                r["seconds_since_seen"] = round(age)
        return rows

    @api.route("GET", "/devices/adapters", summary="Device adapter catalogue with example native payloads", tags=["devices"],
               roles=ALL_USERS)
    def adapters(ctx: Ctx):
        return [{"device_type": a.device_type, "adapter": type(a).__name__, "source_type": a.source_type,
                 "metrics": list(a.metrics), "example_reading": a.example,
                 "hardware_validated": False} for a in ADAPTERS.values()]

    @api.route("POST", "/devices/{device_id}/status", summary="Device heartbeat / status (device key)", tags=["devices"],
               body=schemas.DeviceStatusIn, auth="user_or_device")
    def device_status(ctx: Ctx):
        dev_id = ctx.path["device_id"]
        if ctx.principal.kind == "device" and ctx.principal.device_id != dev_id:
            raise forbidden("device key does not match device")
        if ctx.principal.kind == "user" and ctx.principal.role != "admin":
            raise forbidden("only the device or an administrator can set device status")
        with db.transaction(ctx.conn):
            ctx.conn.execute("UPDATE devices SET status=?, battery_pct=COALESCE(?, battery_pct), last_seen_at=? WHERE id=?",
                             (ctx.body.status, ctx.body.battery_pct, db.now_iso(), dev_id))
        from ..bus import BUS
        BUS.publish("device.status", {"device_id": dev_id, "status": ctx.body.status, "battery_pct": ctx.body.battery_pct})
        return {"device_id": dev_id, "status": ctx.body.status}

    @api.route("POST", "/devices/{device_id}/readings", summary="Submit a device-native reading (converted by the device adapter)",
               tags=["devices"], body=schemas.DeviceReadingIn, response=schemas.TelemetryResult, auth="user_or_device")
    def device_reading(ctx: Ctx):
        dev = db.one(ctx.conn, "SELECT * FROM devices WHERE id=?", (ctx.path["device_id"],))
        if not dev:
            raise not_found("device", ctx.path["device_id"])
        if ctx.principal.kind != "device" or ctx.principal.device_id != dev["id"]:
            raise forbidden("device readings must be authenticated with this device's key")
        rid = ctx.body.reading_id or db.new_id("RD")
        if dev["astronaut_id"] and ctx.body.astronaut_id and ctx.body.astronaut_id != dev["astronaut_id"]:
            raise forbidden("device is assigned to a different astronaut")
        dev_view = dict(dev, astronaut_id=dev["astronaut_id"] or ctx.body.astronaut_id)
        try:
            obs = adapter_for(dev["device_type"]).to_observations(ctx.body.reading, device=dev_view, measured_at=ctx.body.measured_at,
                                                                   reading_id=rid)
        except AdapterError as e:
            raise ApiError(422, "adapter_error", str(e))
        return ingestion.ingest(ctx.conn, ctx.principal, obs, batch_id=rid)

    # ---------------------------------------------------------------- telemetry
    @api.route("POST", "/telemetry", summary="Telemetry ingestion (unified observation format)", tags=["ingestion"],
               body=schemas.TelemetryBatchIn, response=schemas.TelemetryResult, auth="user_or_device")
    def telemetry(ctx: Ctx):
        """Validates each observation independently (metric, unit, value range, timestamp, identity, device),
        stores accepted observations with provenance, runs the assessment engine, creates alerts and publishes
        real-time events. Idempotent by observation_id and optional `Idempotency-Key` header."""
        sim_run = ctx.headers.get("x-simulator-run")
        if sim_run and not (ctx.principal.kind == "device" and db.one(ctx.conn, "SELECT is_simulated FROM devices WHERE id=?",
                                                                       (ctx.principal.device_id,))["is_simulated"]):
            sim_run = None
        return ingestion.handle_telemetry(ctx.conn, ctx.principal, ctx.body.model_dump(), ctx.headers.get("idempotency-key"),
                                          sim_run_id=sim_run)

    @api.route("POST", "/measurements/manual", summary="Manual measurement entry (one panel)", tags=["ingestion"],
               body=schemas.ManualMeasurementIn, response=schemas.TelemetryResult, roles=HEALTH_ROLES, status_code=201)
    def manual(ctx: Ctx):
        b = ctx.body
        ast = b.astronaut_id or ctx.principal.astronaut_id
        if not ast:
            raise ApiError(400, "astronaut_required", "astronaut_id is required")
        a = db.one(ctx.conn, "SELECT * FROM astronauts WHERE id=?", (ast,))
        if not a:
            raise not_found("astronaut", ast)
        panel = b.client_submission_id or db.new_id("PNL")
        items = []
        for n, it in enumerate(b.items):
            ctx_obj = dict(b.context, panel_id=panel)
            if b.method:
                ctx_obj["method"] = b.method
            oid = (f"OBS-M-{db.sha256([ast, b.client_submission_id, it.metric_code])[:20].upper()}"
                   if b.client_submission_id else None)
            items.append({"observation_id": oid, "astronaut_id": ast, "mission_id": a["mission_id"],
                          "metric_code": it.metric_code, "value": it.value, "unit": it.unit, "measured_at": b.measured_at,
                          "source_type": b.source_type, "device_id": b.device_id, "quality": b.quality,
                          "context": ctx_obj, "notes": b.notes,
                          "symptoms": [s.model_dump() for s in b.symptoms] if n == 0 else []})
        res = ingestion.ingest(ctx.conn, ctx.principal, items, batch_id=panel)
        if res["rejected"] and not res["accepted"]:
            raise ApiError(422, "validation_error", "measurement rejected", res["rejected"])
        return res

    @api.route("GET", "/measurements/history", summary="Measurement history with pagination, filters and aggregation",
               tags=["measurements"], query=schemas.HistoryQuery, roles=ALL_USERS)
    def history(ctx: Ctx):
        q = ctx.query
        env = False
        if q.metric_code and knowledge.indicators().get(q.metric_code, {}).get("subject") == "environment":
            env = True
        ast = None if env and not q.astronaut_id else scoped_astronaut(ctx, q.astronaut_id)
        sql = "SELECT * FROM observations WHERE " + ("astronaut_id IS NULL" if ast is None else "astronaut_id=?")
        params: list = [] if ast is None else [ast]
        for col, val in (("metric_code", q.metric_code), ("source_type", q.source_type), ("quality", q.quality),
                         ("location", q.location)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        if q.start:
            sql += " AND measured_at>=?"
            params.append(db.iso(db.parse_iso(q.start)))
        if q.end:
            sql += " AND measured_at<=?"
            params.append(db.iso(db.parse_iso(q.end)))
        total = db.one(ctx.conn, sql.replace("SELECT *", "SELECT COUNT(*) c", 1), params)["c"]
        rows = db.all_(ctx.conn, sql + f" ORDER BY measured_at {q.order.upper()} LIMIT ? OFFSET ?", params + [q.limit, q.offset])
        if q.context_key is not None and q.metric_code:
            from ..services.baselines import context_key_for
            rows = [r for r in rows if context_key_for(q.metric_code, db.loads(r["context"], {})) == q.context_key]
        rows, hidden = filter_private(ctx, rows)
        items = [ingestion.decode_observation(r) for r in rows]
        out = {"total": total, "limit": q.limit, "offset": q.offset, "hidden_private": hidden, "bucket": q.bucket}
        if q.bucket and q.bucket != "raw":
            out["buckets"] = trends.aggregate(rows, q.bucket)
        out["items"] = items
        return out

    @api.route("GET", "/measurements/latest", summary="Latest observation per metric", tags=["measurements"],
               query=schemas.LatestQuery, roles=VIEW_ROLES)
    def latest(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        codes = ctx.query.metric_code
        if isinstance(codes, str):
            codes = [codes]
        return _latest(ctx, ast, codes)

    @api.route("GET", "/measurements/{observation_id}", summary="Observation detail with provenance and linked assessments",
               tags=["measurements"], roles=ALL_USERS)
    def observation_detail(ctx: Ctx):
        r = db.one(ctx.conn, "SELECT * FROM observations WHERE id=?", (ctx.path["observation_id"],))
        if not r:
            raise not_found("observation", ctx.path["observation_id"])
        if r["astronaut_id"]:
            scoped_astronaut(ctx, r["astronaut_id"])
            if r["is_private"] and not can_view_private(ctx.principal, r["astronaut_id"]):
                raise forbidden("private record")
        o = ingestion.decode_observation(r)
        o["indicator"] = knowledge.indicators().get(o["metric_code"])
        o["assessments"] = db.all_(ctx.conn, """SELECT a.id, a.status, a.created_at FROM assessment_observations ao
                                               JOIN health_assessments a ON a.id=ao.assessment_id WHERE ao.observation_id=?""", (o["id"],))
        o["alerts"] = db.all_(ctx.conn, """SELECT a.id, a.severity, a.title FROM alert_observations ao JOIN alerts a ON a.id=ao.alert_id
                                          WHERE ao.observation_id=?""", (o["id"],))
        o["symptoms"] = [ingestion.decode_observation(s) for s in db.all_(ctx.conn,
                         "SELECT * FROM observations WHERE metric_code='symptom' AND json_extract(context,'$.related_observation_id')=?", (o["id"],))]
        if o["device_id"]:
            d = db.one(ctx.conn, "SELECT id, device_type, model, is_simulated, hardware_validated FROM devices WHERE id=?", (o["device_id"],))
            o["device"] = d
        from ..services import replication
        o["replication"] = replication.record_sync_info(ctx.conn, "observation", o["id"])
        return o

    # ---------------------------------------------------------------- knowledge
    @api.route("GET", "/indicators", summary="Health indicator definitions", tags=["knowledge"], auth="none")
    def indicators(ctx: Ctx):
        return knowledge.list_indicators(ctx.conn)

    @api.route("GET", "/symptoms", summary="Symptom vocabulary", tags=["knowledge"], auth="none")
    def symptoms(ctx: Ctx):
        return list(knowledge.symptom_codes().values())

    @api.route("GET", "/hazards", summary="Five hazards with related risks and sources", tags=["knowledge"], auth="none")
    def hazards(ctx: Ctx):
        return knowledge.list_hazards(ctx.conn)

    @api.route("GET", "/risks", summary="Risk definitions", tags=["knowledge"], auth="none")
    def risks(ctx: Ctx):
        bs = ctx.request.query_params.get("body_system")
        hz = ctx.request.query_params.get("hazard_id")
        return knowledge.list_risks(ctx.conn, bs, hz)

    @api.route("GET", "/risks/{risk_id}", summary="Risk detail", tags=["knowledge"], auth="none")
    def risk(ctx: Ctx):
        r = knowledge.get_risk(ctx.conn, ctx.path["risk_id"])
        if not r:
            raise not_found("risk", ctx.path["risk_id"])
        return r

    @api.route("GET", "/countermeasures", summary="Countermeasure references", tags=["knowledge"], auth="none")
    def countermeasures(ctx: Ctx):
        return knowledge.list_countermeasures(ctx.conn)

    @api.route("GET", "/sources", summary="Evidence sources with verification status", tags=["knowledge"], auth="none")
    def sources(ctx: Ctx):
        return db.all_(ctx.conn, "SELECT * FROM evidence_sources ORDER BY id")

    # ---------------------------------------------------------------- records
    def _rec(fn, body, ctx):
        sim = ctx.headers.get("x-simulator-run") if getattr(body, "synthetic", False) else None
        try:
            return fn(ctx.conn, ctx.principal, body, sim_run_id=sim)
        except records.RecordError as e:
            raise ApiError(422, "validation_error", str(e), e.details)

    @api.route("POST", "/sleep", summary="Sleep assessment", tags=["records"], body=schemas.SleepIn, roles=HEALTH_ROLES, status_code=201)
    @map_errors
    def sleep_create(ctx: Ctx):
        return _rec(records.create_sleep, ctx.body, ctx)

    @api.route("GET", "/sleep", summary="Sleep records", tags=["records"], query=schemas.AstronautQuery, roles=VIEW_ROLES)
    def sleep_list(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        return db.all_(ctx.conn, "SELECT * FROM sleep_records WHERE astronaut_id=? AND sleep_end>=? ORDER BY sleep_end DESC",
                       (ast, db.hours_ago(24 * ctx.query.days)))

    @api.route("POST", "/mood", summary="Private daily check-in (mood, stress, fatigue …)", tags=["records"], body=schemas.MoodIn,
               roles=HEALTH_ROLES, status_code=201)
    @map_errors
    def mood_create(ctx: Ctx):
        return _rec(records.create_mood, ctx.body, ctx)

    @api.route("GET", "/mood", summary="Private check-ins (astronaut and flight surgeon only)", tags=["records"],
               query=schemas.AstronautQuery, roles=VIEW_ROLES)
    def mood_list(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        if not can_view_private(ctx.principal, ast):
            raise forbidden("private check-ins are visible only to the astronaut and the flight surgeon")
        rows = db.all_(ctx.conn, "SELECT * FROM mood_assessments WHERE astronaut_id=? AND assessed_at>=? ORDER BY assessed_at DESC",
                       (ast, db.hours_ago(24 * ctx.query.days)))
        with db.transaction(ctx.conn):
            audit.record(ctx.conn, ctx.principal, "mood.read", "mood_assessment", ast, {"count": len(rows)})
        return [records.decode_mood(r) for r in rows]

    @api.route("POST", "/exercise", summary="Exercise record", tags=["records"], body=schemas.ExerciseIn, roles=HEALTH_ROLES,
               status_code=201)
    @map_errors
    def exercise_create(ctx: Ctx):
        return _rec(records.create_exercise, ctx.body, ctx)

    @api.route("GET", "/exercise", summary="Exercise records and adherence", tags=["records"], query=schemas.AstronautQuery,
               roles=VIEW_ROLES)
    def exercise_list(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        rows = db.all_(ctx.conn, "SELECT * FROM exercise_records WHERE astronaut_id=? AND start_at>=? ORDER BY start_at DESC",
                       (ast, db.hours_ago(24 * ctx.query.days)))
        sessions = [r for r in rows if r["category"] != "performance_test"]
        done = sum(1 if r["completion_status"] == "completed" else 0.5 if r["completion_status"] == "partial" else 0 for r in sessions)
        return {"items": rows, "adherence": {"logged_sessions": len(sessions), "completed_equivalent": done,
                                             "ratio": round(done / len(sessions), 2) if sessions else None,
                                             "note": "Adherence is not a measurement of bone density."}}

    @api.route("POST", "/nutrition", summary="Nutrition / hydration record", tags=["records"], body=schemas.NutritionIn,
               roles=HEALTH_ROLES, status_code=201)
    @map_errors
    def nutrition_create(ctx: Ctx):
        return _rec(records.create_nutrition, ctx.body, ctx)

    @api.route("GET", "/nutrition", summary="Nutrition records with daily water totals", tags=["records"],
               query=schemas.AstronautQuery, roles=VIEW_ROLES)
    def nutrition_list(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        rows = db.all_(ctx.conn, "SELECT * FROM nutrition_records WHERE astronaut_id=? AND recorded_at>=? ORDER BY recorded_at DESC",
                       (ast, db.hours_ago(24 * ctx.query.days)))
        totals: dict[str, float] = {}
        for r in rows:
            if r["water_ml"]:
                totals[r["recorded_at"][:10]] = totals.get(r["recorded_at"][:10], 0) + r["water_ml"]
        return {"items": rows, "daily_water_ml": [{"date": d, "total_ml": round(v)} for d, v in sorted(totals.items())],
                "note": "Daily totals depend on complete logging. ASTRA does not estimate nutrient deficiencies."}

    @api.route("POST", "/medications", summary="Record medication given under an approved instruction", tags=["records"],
               body=schemas.MedicationIn, roles=MED, status_code=201)
    @map_errors
    def medication_create(ctx: Ctx):
        return records.create_medication(ctx.conn, ctx.principal, ctx.body)

    @api.route("POST", "/medical-history", summary="Add medical history entry", tags=["records"], body=schemas.MedicalHistoryIn,
               roles=MED, status_code=201)
    @map_errors
    def history_create(ctx: Ctx):
        return records.create_history(ctx.conn, ctx.principal, ctx.body)


def _user_public(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "display_name": u["display_name"], "role": u["role"],
            "astronaut_id": u["astronaut_id"]}


def _user_admin(u: dict) -> dict:
    """User row for the administrator's user list (account and assignment only — no health data)."""
    return _user_public(u) | {
        "active": bool(u["active"]), "created_at": u["created_at"],
        "sign_in": "password",
        "assigned_mission_id": u.get("user_mission_id") if u["role"] in security.EARTH_ROLES else None,
        "editable_role": u["role"] in security.ADMIN_ASSIGNABLE_ROLES,
        "astronaut": {"id": u["astronaut_id"], "name": u.get("astronaut_name"), "call_sign": u.get("call_sign"),
                      "crew_role": u.get("crew_role"), "crew": u.get("crew"), "mission_id": u.get("mission_id"),
                      "mission_name": u.get("mission_name")} if u["astronaut_id"] else None,
    }


def _check_password(password: str, username: str) -> None:
    probs = security.password_problems(password, username)
    if probs:
        raise ApiError(422, "weak_password", "; ".join(probs), {"password": probs})


def _user_admin_by_id(conn, uid: int) -> dict:
    return _user_admin(db.one(conn, """SELECT u.*, a.name astronaut_name, a.call_sign, a.crew_role, a.crew, a.mission_id, u.mission_id user_mission_id,
                                              m.name mission_name FROM users u LEFT JOIN astronauts a ON a.id=u.astronaut_id
                                       LEFT JOIN missions m ON m.id=a.mission_id WHERE u.id=?""", (uid,)))


def _next_astronaut_id(conn) -> str:
    n = 0
    for r in db.all_(conn, "SELECT id FROM astronauts WHERE id LIKE 'AST-%'"):
        try:
            n = max(n, int(r["id"][4:]))
        except ValueError:
            continue
    return f"AST-{n + 1:03d}"


def _mission(conn, m: dict) -> dict:
    m = dict(m)
    m["phases"] = db.all_(conn, "SELECT * FROM mission_environments WHERE mission_id=? ORDER BY start_utc", (m["id"],))
    now = db.now_iso()
    m["current_phase"] = next((p for p in reversed(m["phases"]) if p["start_utc"] <= now and (p["end_utc"] is None or p["end_utc"] > now)), None)
    m["mission_day"] = mission_day(m)
    m["crew"] = db.all_(conn, "SELECT id, name, call_sign, crew_role, crew FROM astronauts WHERE mission_id=?", (m["id"],))
    m["is_synthetic"] = bool(m["is_synthetic"])
    return m


def _latest(ctx: Ctx, ast: str, codes: list[str] | None) -> list[dict]:
    rows = db.all_(ctx.conn, """SELECT o.* FROM observations o JOIN (SELECT metric_code, MAX(measured_at) mt FROM observations
                                WHERE astronaut_id=? GROUP BY metric_code) x ON x.metric_code=o.metric_code AND x.mt=o.measured_at
                                WHERE o.astronaut_id=?""", (ast, ast))
    if codes:
        rows = [r for r in rows if r["metric_code"] in codes]
    rows, _ = filter_private(ctx, rows)
    out = []
    seen = set()
    for r in sorted(rows, key=lambda r: r["metric_code"]):
        if r["metric_code"] in seen:
            continue
        seen.add(r["metric_code"])
        o = ingestion.decode_observation(r)
        o["age_hours"] = round((db.utcnow() - db.parse_iso(r["measured_at"])).total_seconds() / 3600, 2)
        out.append(o)
    return out
