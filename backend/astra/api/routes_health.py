"""Routes: baselines, rules, assessments, trends, alerts, medical events,
protocols, reports, and page-level aggregate views (overview, body systems,
daily routine)."""
from __future__ import annotations

from datetime import timedelta

from .. import audit, db, schemas
from ..bus import BUS
from ..security import MEDICAL_ROLES, can_view_private
from ..services import alerts as alert_svc
from ..services import (assessment_engine, baselines, environment, knowledge, medical_events, reports, sync,
                        trends)
from .common import default_mission, filter_private, map_errors, mission_day, scoped_astronaut
from .framework import Api, ApiError, Ctx, forbidden, not_found
from .routes_data import ALL_USERS, HEALTH_ROLES, _latest

MED = MEDICAL_ROLES
BODY_SYSTEMS = {
    "cardiovascular": {"label": "Cardiovascular", "metrics": ["heart_rate", "bp_systolic", "bp_diastolic"]},
    "respiratory": {"label": "Respiratory", "metrics": ["spo2", "respiratory_rate"]},
    "neurological": {"label": "Neurological, sensorimotor & vision", "metrics": ["sleep_duration", "motion_sickness_score", "balance_assessment"]},
    "musculoskeletal": {"label": "Musculoskeletal", "metrics": ["exercise_session", "physical_performance", "pain_score"]},
    "immune": {"label": "Immune", "metrics": ["body_temperature"]},
    "behavioral": {"label": "Behavioral health", "metrics": ["mood", "stress", "fatigue", "cognitive_pvt_rt"]},
    "renal_metabolic": {"label": "Renal, nutrition & metabolic", "metrics": ["water_intake", "energy_intake", "blood_glucose"]},
}


def _visible_alert_rows(ctx: Ctx, rows: list[dict]) -> list[dict]:
    """Health alerts: astronaut sees own; medical roles see all (private redacted for CMO). Environment alerts: everyone."""
    p = ctx.principal
    out = []
    for a in rows:
        if a["astronaut_id"] is None:
            out.append(a)
        elif p.role in MED or (p.role == "astronaut" and p.astronaut_id == a["astronaut_id"]):
            if a["is_private"] and not (can_view_private(p, a["astronaut_id"]) or p.role == "medical_officer"):
                continue
            out.append(a)
    return out


def register(api: Api) -> None:
    # ---------------------------------------------------------------- measurements alias
    @api.route("GET", "/measurements", summary="Alias of /measurements/history", tags=["measurements"],
               query=schemas.HistoryQuery, roles=ALL_USERS)
    def measurements_alias(ctx: Ctx):
        spec = next(s for s in api.specs if s.path == "/measurements/history")
        return spec.handler(ctx)

    # ---------------------------------------------------------------- baselines
    @api.route("GET", "/baselines", summary="Individual baselines (all versions)", tags=["baselines"],
               query=schemas.AstronautQuery, roles=HEALTH_ROLES)
    def baseline_list(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        rows = baselines.list_for(ctx.conn, ast)
        if not can_view_private(ctx.principal, ast):
            priv = {c for c, i in knowledge.indicators().items() if i.get("privacy") == "private"}
            rows = [r for r in rows if r["metric_code"] not in priv]
        return rows

    @api.route("POST", "/baselines", summary="Propose a baseline from a period of valid observations (draft)", tags=["baselines"],
               body=schemas.BaselineProposeIn, roles=MED, status_code=201)
    @map_errors
    def baseline_propose(ctx: Ctx):
        b = ctx.body
        scoped_astronaut(ctx, b.astronaut_id)
        return baselines.propose(ctx.conn, ctx.principal, b.astronaut_id, b.metric_code, db.iso(db.parse_iso(b.period_start)),
                                 db.iso(db.parse_iso(b.period_end)), b.source, b.context_key, b.notes)

    @api.route("POST", "/baselines/{baseline_id}/approve", summary="Approve a draft baseline (optionally with reference range)",
               tags=["baselines"], body=schemas.BaselineApproveIn, roles=MED)
    @map_errors
    def baseline_approve(ctx: Ctx):
        return baselines.approve(ctx.conn, ctx.principal, ctx.path["baseline_id"], ctx.body.ref_low, ctx.body.ref_high, ctx.body.notes)

    @api.route("POST", "/baselines/{baseline_id}/retire", summary="Retire a baseline version", tags=["baselines"], roles=MED)
    @map_errors
    def baseline_retire(ctx: Ctx):
        return baselines.retire(ctx.conn, ctx.principal, ctx.path["baseline_id"])

    # ---------------------------------------------------------------- rules
    @api.route("GET", "/rules", summary="Centralized rule configuration (all versions)", tags=["rules"], roles=ALL_USERS)
    def rules(ctx: Ctx):
        return knowledge.all_rules(ctx.conn)

    @api.route("POST", "/rules/{rule_id}/versions", summary="Create a new rule version (flight surgeon)", tags=["rules"],
               body=schemas.RuleUpdateIn, roles=("flight_surgeon",), status_code=201)
    def rule_update(ctx: Ctx):
        cur = db.one(ctx.conn, "SELECT * FROM assessment_rules WHERE id=? ORDER BY version DESC LIMIT 1", (ctx.path["rule_id"],))
        if not cur:
            raise not_found("rule", ctx.path["rule_id"])
        new = dict(cur)
        new["version"] = cur["version"] + 1
        b = ctx.body
        if b.active is not None:
            new["active"] = int(b.active)
        if b.params is not None:
            new["params"] = db.dumps({**db.loads(cur["params"], {}), **b.params})
        if b.approval_status:
            new["approval_status"] = b.approval_status
        if b.effective_date:
            new["effective_date"] = b.effective_date
        if cur["rule_class"] == "DEMONSTRATION_ONLY" and b.approval_status and "APPROVED" in b.approval_status.upper():
            raise ApiError(422, "invalid", "a DEMONSTRATION_ONLY rule cannot be marked approved; create a clinician rule instead")
        with db.transaction(ctx.conn):
            db.insert(ctx.conn, "assessment_rules", new)
            audit.record(ctx.conn, ctx.principal, "rule.new_version", "assessment_rule", cur["id"],
                         {"from": cur["version"], "to": new["version"], "changes": b.model_dump(exclude_none=True)})
        return knowledge.decode_rule(new)

    # ---------------------------------------------------------------- assessments / trends
    @api.route("GET", "/assessments", summary="Assessment history", tags=["assessments"], query=schemas.ListQuery,
               roles=HEALTH_ROLES)
    def assessment_list(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        sql = "SELECT * FROM health_assessments WHERE astronaut_id=?"
        params = [ast]
        if ctx.query.status:
            sql += " AND status=?"
            params.append(ctx.query.status)
        rows = db.all_(ctx.conn, sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?", params + [ctx.query.limit, ctx.query.offset])
        rows, hidden = filter_private(ctx, rows)
        return {"items": [assessment_engine.decode(r) for r in rows], "hidden_private": hidden}

    @api.route("GET", "/assessments/{assessment_id}", summary="Assessment detail (findings, evidence, limitations)",
               tags=["assessments"], roles=HEALTH_ROLES)
    def assessment_detail(ctx: Ctx):
        r = db.one(ctx.conn, "SELECT * FROM health_assessments WHERE id=?", (ctx.path["assessment_id"],))
        if not r:
            raise not_found("assessment", ctx.path["assessment_id"])
        scoped_astronaut(ctx, r["astronaut_id"])
        if r["is_private"] and not can_view_private(ctx.principal, r["astronaut_id"]):
            raise forbidden("private assessment")
        a = assessment_engine.decode(r)
        a["observation_ids"] = [x["observation_id"] for x in db.all_(ctx.conn, "SELECT observation_id FROM assessment_observations WHERE assessment_id=?", (r["id"],))]
        a["evidence_sources"] = [db.one(ctx.conn, "SELECT * FROM evidence_sources WHERE id=?", (s,)) for s in a["evidence_refs"]]
        return a

    @api.route("POST", "/assessments", summary="Run a full assessment now (all rules + missing-data checks)", tags=["assessments"],
               body=schemas.AssessmentRunIn, roles=HEALTH_ROLES, status_code=201)
    def assessment_run(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.body.astronaut_id)
        res = assessment_engine.full_assessment(ctx.conn, ast, trigger=f"manual:{ctx.principal.actor}")
        r = db.one(ctx.conn, "SELECT * FROM health_assessments WHERE id=?", (res["assessment_id"],))
        return assessment_engine.decode(r) | {"alerts_created": res["alerts_created"]}

    @api.route("GET", "/trends", summary="Trend analysis for one indicator", tags=["assessments"], roles=HEALTH_ROLES)
    def trend(ctx: Ctx):
        qp = ctx.request.query_params
        ast = scoped_astronaut(ctx, qp.get("astronaut_id"))
        metric = qp.get("metric_code")
        if metric not in knowledge.indicators():
            raise ApiError(422, "invalid", "metric_code is required and must be a known indicator")
        if knowledge.indicators()[metric].get("privacy") == "private" and not can_view_private(ctx.principal, ast):
            raise forbidden("private indicator")
        days = float(qp.get("days", 14))
        sched = db.one(ctx.conn, "SELECT interval_hours FROM assessment_schedule WHERE astronaut_id=? AND metric_codes LIKE ?",
                       (ast, f'%"{metric}"%'))
        return trends.analyze(ctx.conn, ast, metric, days=days, recent_days=float(qp.get("recent_days", 3)),
                              context_key=qp.get("context_key"), expected_interval_hours=sched["interval_hours"] if sched else None)

    # ---------------------------------------------------------------- alerts
    @api.route("GET", "/alerts", summary="Alerts (filtered by role and privacy)", tags=["alerts"], query=schemas.ListQuery,
               roles=HEALTH_ROLES)
    def alert_list(ctx: Ctx):
        q = ctx.query
        sql, params = "SELECT * FROM alerts WHERE 1=1", []
        if q.astronaut_id:
            scoped_astronaut(ctx, q.astronaut_id)
            sql += " AND (astronaut_id=? OR astronaut_id IS NULL)"
            params.append(q.astronaut_id)
        if q.status:
            sql += " AND resolution_status=?"
            params.append(q.status)
        if q.severity:
            sql += " AND severity=?"
            params.append(q.severity)
        if q.category:
            sql += " AND category=?"
            params.append(q.category)
        rows = db.all_(ctx.conn, sql + " ORDER BY CASE resolution_status WHEN 'open' THEN 0 ELSE 1 END, "
                       "CASE severity WHEN 'URGENT' THEN 0 WHEN 'MEDICAL_REVIEW' THEN 1 WHEN 'REASSESSMENT' THEN 2 ELSE 3 END, "
                       "updated_at DESC LIMIT ? OFFSET ?", params + [q.limit, q.offset])
        rows = _visible_alert_rows(ctx, rows)
        return [alert_svc.decode(ctx.conn, a, ctx.principal) for a in rows]

    @api.route("GET", "/alerts/{alert_id}", summary="Alert detail", tags=["alerts"], roles=HEALTH_ROLES)
    def alert_detail(ctx: Ctx):
        a = db.one(ctx.conn, "SELECT * FROM alerts WHERE id=?", (ctx.path["alert_id"],))
        if not a or not _visible_alert_rows(ctx, [a]):
            raise not_found("alert", ctx.path["alert_id"])
        d = alert_svc.decode(ctx.conn, a, ctx.principal, with_obs=True)
        rule = db.one(ctx.conn, "SELECT * FROM assessment_rules WHERE id=? AND version=?", (a["rule_id"], a["rule_version"]))
        d["rule"] = knowledge.decode_rule(rule) if rule else None
        d["rule_source"] = db.one(ctx.conn, "SELECT * FROM evidence_sources WHERE id=?", (rule["source_id"],)) if rule and rule["source_id"] else None
        d["protocol"] = knowledge.get_protocol(ctx.conn, a["protocol_id"]) if a["protocol_id"] else None
        return d

    @api.route("POST", "/alerts/{alert_id}/acknowledge", summary="Acknowledge an alert (does not resolve the medical event)",
               tags=["alerts"], body=schemas.AlertActionIn, roles=HEALTH_ROLES)
    @map_errors
    def alert_ack(ctx: Ctx):
        a = db.one(ctx.conn, "SELECT * FROM alerts WHERE id=?", (ctx.path["alert_id"],))
        if not a or not _visible_alert_rows(ctx, [a]):
            raise not_found("alert", ctx.path["alert_id"])
        return alert_svc.acknowledge(ctx.conn, ctx.principal, a["id"], ctx.body.note)

    @api.route("POST", "/alerts/{alert_id}/resolve", summary="Resolve an alert", tags=["alerts"], body=schemas.AlertActionIn,
               roles=HEALTH_ROLES)
    @map_errors
    def alert_resolve(ctx: Ctx):
        a = db.one(ctx.conn, "SELECT * FROM alerts WHERE id=?", (ctx.path["alert_id"],))
        if not a or not _visible_alert_rows(ctx, [a]):
            raise not_found("alert", ctx.path["alert_id"])
        return alert_svc.resolve(ctx.conn, ctx.principal, a["id"], ctx.body.note)

    # ---------------------------------------------------------------- medical events
    def _event_visible(ctx: Ctx, e: dict) -> tuple[bool, bool]:
        p = ctx.principal
        if e["astronaut_id"] is None:
            return True, False
        if p.role == "astronaut" and p.astronaut_id != e["astronaut_id"]:
            return False, False
        if e["is_private"] and not can_view_private(p, e["astronaut_id"]):
            return p.role == "medical_officer", True
        return p.role in MED or p.astronaut_id == e["astronaut_id"], False

    @api.route("GET", "/medical-events", summary="Medical events", tags=["medical-events"], query=schemas.ListQuery, roles=HEALTH_ROLES)
    def event_list(ctx: Ctx):
        q = ctx.query
        sql, params = "SELECT * FROM medical_events WHERE 1=1", []
        if q.astronaut_id:
            scoped_astronaut(ctx, q.astronaut_id)
            sql += " AND astronaut_id=?"
            params.append(q.astronaut_id)
        if q.status:
            if q.status == "open":
                sql += " AND state!='RESOLVED'"
            else:
                sql += " AND state=?"
                params.append(q.status)
        rows = db.all_(ctx.conn, sql + " ORDER BY CASE WHEN state='RESOLVED' THEN 1 ELSE 0 END, "
                       "CASE severity WHEN 'URGENT' THEN 0 WHEN 'MEDICAL_REVIEW' THEN 1 ELSE 2 END, opened_at DESC LIMIT ? OFFSET ?",
                       params + [q.limit, q.offset])
        out = []
        for e in rows:
            vis, red = _event_visible(ctx, e)
            if not vis:
                continue
            e = dict(e, is_private=bool(e["is_private"]), is_synthetic=bool(e["is_synthetic"]), redacted=red)
            if red:
                e["title"] = "Private behavioral-health follow-up"
            out.append(e)
        return out

    @api.route("GET", "/medical-events/{event_id}", summary="Medical event detail (timeline, protocol, checklist)",
               tags=["medical-events"], roles=HEALTH_ROLES)
    def event_detail(ctx: Ctx):
        e = medical_events.get(ctx.conn, ctx.path["event_id"])
        if not e:
            raise not_found("medical event", ctx.path["event_id"])
        vis, red = _event_visible(ctx, e)
        if not vis or red:
            raise forbidden("private medical event")
        return e

    @api.route("POST", "/medical-events/{event_id}/transition", summary="Change medical event state (validated state machine)",
               tags=["medical-events"], body=schemas.EventTransitionIn, roles=HEALTH_ROLES)
    def event_transition(ctx: Ctx):
        e = _event_for_write(ctx)
        try:
            return medical_events.transition(ctx.conn, ctx.principal, e["id"], ctx.body.to_state, ctx.body.reason)
        except medical_events.TransitionError as ex:
            raise ApiError(409, "invalid_transition", str(ex))
        except PermissionError as ex:
            raise ApiError(403, "forbidden", str(ex))

    @api.route("POST", "/medical-events/{event_id}/actions", summary="Record an action (checklist item, note, step)",
               tags=["medical-events"], body=schemas.EventActionIn, roles=HEALTH_ROLES, status_code=201)
    def event_action(ctx: Ctx):
        e = _event_for_write(ctx)
        a = medical_events.add_action(ctx.conn, ctx.principal, e["id"], ctx.body.action_type, ctx.body.description, ctx.body.data)
        a["data"] = db.loads(a["data"], {})
        return a

    @api.route("POST", "/medical-events/{event_id}/escalate", summary="Escalate: notify medical personnel and queue report to ground",
               tags=["medical-events"], body=schemas.EscalateIn, roles=HEALTH_ROLES)
    def event_escalate(ctx: Ctx):
        e = _event_for_write(ctx)
        if e["state"] != "ESCALATED":
            if "ESCALATED" not in medical_events.TRANSITIONS[e["state"]]:
                raise ApiError(409, "invalid_transition", f"cannot escalate from {e['state']}")
            medical_events.transition(ctx.conn, ctx.principal, e["id"], "ESCALATED", ctx.body.note or "Escalated to medical personnel")
        now = db.now_iso()
        with db.transaction(ctx.conn):
            ctx.conn.execute("UPDATE alerts SET escalation_status='escalated', escalated_at=?, updated_at=? WHERE medical_event_id=?",
                             (now, now, e["id"]))
            medical_events.add_action(ctx.conn, ctx.principal, e["id"], "escalation", ctx.body.note or "Escalation requested",
                                      {"outstanding_questions": ctx.body.outstanding_questions})
            medical_events.add_action(ctx.conn, ctx.principal, e["id"], "notification",
                                      "Notified: Crew Medical Officer (onboard), Flight Surgeon (ground, via sync queue)")
        rpt = reports.create(ctx.conn, ctx.principal, e["id"], ctx.body.outstanding_questions, queue=True)
        BUS.publish("notification", {"id": e["id"], "severity": e["severity"], "title": f"Escalated: {e['title']}",
                                     "roles": ["medical_officer", "flight_surgeon"]},
                    astronaut_id=e["astronaut_id"], private=bool(e["is_private"]))
        out = medical_events.get(ctx.conn, e["id"])
        out["report"] = {"id": rpt["id"], "sync_status": rpt["sync_status"]}
        return out

    @api.route("POST", "/medical-events/{event_id}/reports", summary="Generate a structured medical report", tags=["medical-reports"],
               body=schemas.ReportCreateIn, roles=HEALTH_ROLES, status_code=201)
    def event_report(ctx: Ctx):
        e = _event_for_write(ctx)
        return reports.create(ctx.conn, ctx.principal, e["id"], ctx.body.outstanding_questions, ctx.body.queue_for_transmission)

    def _event_for_write(ctx: Ctx) -> dict:
        e = db.one(ctx.conn, "SELECT * FROM medical_events WHERE id=?", (ctx.path["event_id"],))
        if not e:
            raise not_found("medical event", ctx.path["event_id"])
        vis, red = _event_visible(ctx, e)
        if not vis or red:
            raise forbidden("not permitted for this medical event")
        return e

    @api.route("GET", "/medical-reports", summary="Medical reports", tags=["medical-reports"], query=schemas.ListQuery, roles=HEALTH_ROLES)
    def report_list(ctx: Ctx):
        rows = db.all_(ctx.conn, "SELECT id, event_id, astronaut_id, created_at, created_by, sync_status, is_private, is_synthetic "
                                 "FROM medical_reports ORDER BY created_at DESC LIMIT ? OFFSET ?", (ctx.query.limit, ctx.query.offset))
        out = []
        for r in rows:
            e = db.one(ctx.conn, "SELECT * FROM medical_events WHERE id=?", (r["event_id"],))
            vis, red = _event_visible(ctx, e) if e else (False, False)
            if vis and not red:
                out.append(r)
        return out

    @api.route("GET", "/medical-reports/{report_id}", summary="Medical report detail", tags=["medical-reports"], roles=HEALTH_ROLES)
    def report_detail(ctx: Ctx):
        r = reports.get(ctx.conn, ctx.path["report_id"])
        if not r:
            raise not_found("report", ctx.path["report_id"])
        e = db.one(ctx.conn, "SELECT * FROM medical_events WHERE id=?", (r["event_id"],))
        vis, red = _event_visible(ctx, e)
        if not vis or red:
            raise forbidden("not permitted")
        with db.transaction(ctx.conn):
            audit.record(ctx.conn, ctx.principal, "medical_report.read", "medical_report", r["id"], {})
        return r

    # ---------------------------------------------------------------- protocols
    @api.route("GET", "/medical-protocols", summary="Preloaded procedures (approval status shown)", tags=["medical-protocols"],
               roles=ALL_USERS)
    def protocols(ctx: Ctx):
        return [knowledge.decode_protocol(p) for p in db.all_(ctx.conn, "SELECT * FROM medical_protocols ORDER BY id, version")]

    @api.route("GET", "/medical-protocols/{protocol_id}", summary="Procedure detail", tags=["medical-protocols"], roles=ALL_USERS)
    def protocol(ctx: Ctx):
        p = knowledge.get_protocol(ctx.conn, ctx.path["protocol_id"])
        if not p:
            raise not_found("procedure", ctx.path["protocol_id"])
        return p

    # ---------------------------------------------------------------- page aggregates
    @api.route("GET", "/overview", summary="Mission overview for one astronaut", tags=["views"], query=schemas.AstronautQuery,
               roles=HEALTH_ROLES)
    def overview(ctx: Ctx):
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        conn = ctx.conn
        m = default_mission(conn)
        a = db.one(conn, "SELECT * FROM astronauts WHERE id=?", (ast,))
        latest_asm = db.one(conn, "SELECT * FROM health_assessments WHERE astronaut_id=? AND is_private=0 ORDER BY created_at DESC LIMIT 1", (ast,))
        alert_rows = _visible_alert_rows(ctx, db.all_(conn, "SELECT * FROM alerts WHERE resolution_status='open' AND "
                                                            "(astronaut_id=? OR astronaut_id IS NULL) ORDER BY updated_at DESC", (ast,)))
        open_alerts = [alert_svc.decode(conn, x, ctx.principal) for x in alert_rows]
        worst = max((alert_svc.SEVERITY_ORDER[x["severity"]] for x in open_alerts if x["astronaut_id"] == ast), default=0)
        vitals_codes = ["heart_rate", "bp_systolic", "bp_diastolic", "spo2", "respiratory_rate", "body_temperature", "blood_glucose",
                        "sleep_duration", "mood"]
        latest = {o["metric_code"]: o for o in _latest(ctx, ast, vitals_codes)}
        vitals = []
        for code in vitals_codes:
            ind = knowledge.indicators()[code]
            if code == "blood_glucose" and not a["glucose_monitoring_enabled"]:
                vitals.append({"metric_code": code, "name": ind["name"], "status": "not_configured",
                               "note": "Clinician-directed; not enabled for this astronaut"})
                continue
            o = latest.get(code)
            if not o:
                hidden = code == "mood" and not can_view_private(ctx.principal, ast)
                vitals.append({"metric_code": code, "name": ind["name"], "status": "private" if hidden else "missing"})
                continue
            stale = o["age_hours"] > 36
            b = baselines.approved(conn, ast, code, baselines.context_key_for(code, {}))
            vitals.append({"metric_code": code, "name": ind["name"], "value": o["value"], "unit": o["unit"],
                           "measured_at": o["measured_at"], "age_hours": o["age_hours"], "source_type": o["source_type"],
                           "device_id": o["device_id"], "quality": o["quality"], "observation_id": o["id"],
                           "is_synthetic": o["is_synthetic"], "status": "stale" if stale else "current",
                           "baseline": {"mean": b["mean"], "sd": b["sd"], "version": b["version"]} if b else None,
                           "z": round(trends.zscore(o["value"], b), 2) if b and isinstance(o["value"], (int, float)) else None})
        sleep = db.all_(conn, "SELECT * FROM sleep_records WHERE astronaut_id=? ORDER BY sleep_end DESC LIMIT 7", (ast,))
        ex = db.all_(conn, "SELECT completion_status FROM exercise_records WHERE astronaut_id=? AND start_at>=? AND category!='performance_test'",
                     (ast, db.hours_ago(24 * 7)))
        done = sum(1 if r["completion_status"] == "completed" else 0.5 if r["completion_status"] == "partial" else 0 for r in ex)
        events = db.all_(conn, "SELECT * FROM medical_events WHERE astronaut_id=? ORDER BY opened_at DESC LIMIT 8", (ast,))
        ev_out = []
        for e in events:
            vis, red = _event_visible(ctx, e)
            if vis:
                ev_out.append({"id": e["id"], "title": "Private behavioral-health follow-up" if red else e["title"],
                               "state": e["state"], "severity": e["severity"], "opened_at": e["opened_at"], "redacted": red,
                               "is_synthetic": bool(e["is_synthetic"])})
        status = assessment_engine.STATUS_FOR[worst]
        if worst == 0 and (not latest_asm or latest_asm["status"] == "INSUFFICIENT_DATA" or
                           sum(1 for v in vitals if v["status"] in ("missing", "stale")) >= 3):
            status = "INSUFFICIENT_DATA"
        from .routes_ops import routine_tasks
        return {
            "mission": {"id": m["id"], "name": m["name"], "mission_type": m["mission_type"], "mission_day": mission_day(m),
                        "start_utc": m["start_utc"], "earth_link_status": m["earth_link_status"],
                        "comm_delay_seconds": m["comm_delay_seconds"], "is_synthetic": bool(m["is_synthetic"]),
                        "phase": db.one(conn, "SELECT phase, location, gravity_g FROM mission_environments WHERE mission_id=? "
                                              "AND start_utc<=? ORDER BY start_utc DESC LIMIT 1", (m["id"], db.now_iso()))},
            "astronaut": {k: a[k] for k in ("id", "name", "call_sign", "crew_role")} | {"is_synthetic": bool(a["is_synthetic"]),
                                                                                       "glucose_monitoring_enabled": bool(a["glucose_monitoring_enabled"])},
            "current_status": status,
            "latest_assessment": assessment_engine.decode(latest_asm) if latest_asm else None,
            "vitals": vitals, "active_alerts": open_alerts[:20],
            "upcoming_tasks": [t for t in routine_tasks(conn, ast) if t["status"] != "done"][:8],
            "sleep_summary": {"records": sleep, "mean_duration_min": round(sum((s["reported_duration_min"] or s["computed_duration_min"]) for s in sleep) / len(sleep), 1) if sleep else None},
            "exercise_summary": {"sessions_7d": len(ex), "completed_equivalent": done, "ratio": round(done / len(ex), 2) if ex else None},
            "environment": {"readings": environment.latest_readings(conn, m["id"]), "open_events": environment.events(conn, m["id"], open_only=True)},
            "recent_events": ev_out,
            "sync": {k: v for k, v in sync.status(conn).items() if k != "items"},
        }

    @api.route("GET", "/body-systems/{system}", summary="Body-system view: risks, hazards, measurements, symptoms, assessments",
               tags=["views"], query=schemas.AstronautQuery, roles=HEALTH_ROLES)
    def body_system(ctx: Ctx):
        system = ctx.path["system"]
        if system not in BODY_SYSTEMS:
            raise not_found("body system", system)
        ast = scoped_astronaut(ctx, ctx.query.astronaut_id)
        conn = ctx.conn
        private_ok = can_view_private(ctx.principal, ast)
        risks = knowledge.list_risks(conn, body_system=system)
        metrics = list(dict.fromkeys(BODY_SYSTEMS[system]["metrics"] + [c for r in risks for c in r["indicators"]
                       if knowledge.indicators().get(c, {}).get("subject") != "environment"
                       and knowledge.indicators().get(c, {}).get("category") not in ("radiation", "symptom")]))
        if not private_ok:
            metrics = [c for c in metrics if knowledge.indicators()[c].get("privacy") != "private"]
        latest = _latest(ctx, ast, metrics)
        sym_codes = {s for r in risks for s in r["symptoms"]}
        start = db.hours_ago(24 * ctx.query.days)
        symptoms = [o for o in db.all_(conn, "SELECT * FROM observations WHERE astronaut_id=? AND metric_code='symptom' AND measured_at>=? "
                                             "ORDER BY measured_at DESC", (ast, start)) if o["value_text"] in sym_codes]
        risk_ids = {r["id"] for r in risks}
        asms = db.all_(conn, "SELECT * FROM health_assessments WHERE astronaut_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 300", (ast, start))
        asms, _ = filter_private(ctx, asms)
        findings = []
        for a in asms:
            d = assessment_engine.decode(a)
            if set(d["risk_ids"]) & risk_ids:
                findings.append({"assessment_id": d["id"], "created_at": d["created_at"], "status": d["status"],
                                 "findings": [f for f in d["findings"]]})
        alerts = _visible_alert_rows(ctx, db.all_(conn, "SELECT * FROM alerts WHERE astronaut_id=? AND resolution_status='open'", (ast,)))
        rel_alerts = []
        for x in alerts:
            r = db.one(conn, "SELECT risk_ids FROM assessment_rules WHERE id=? AND version=?", (x["rule_id"], x["rule_version"]))
            if r and set(db.loads(r["risk_ids"], [])) & risk_ids:
                rel_alerts.append(alert_svc.decode(conn, x, ctx.principal))
        limitations = list(dict.fromkeys(l for r in risks for l in r["limitations"]))
        next_steps = [x["next_step"] for x in rel_alerts] or ["No open findings for this system. Continue the scheduled routine."]
        specialized = [r["specialized_assessment_note"] for r in risks if r.get("specialized_assessment_note")]
        return {"system": system, "label": BODY_SYSTEMS[system]["label"], "risks": risks,
                "hazards": sorted({(h["hazard_id"], h["name"]) for r in risks for h in r["hazards"]}),
                "metrics": metrics, "latest": latest,
                "metric_names": {c: knowledge.indicators()[c]["name"] for c in metrics},
                "symptoms": [{"id": s["id"], "code": s["value_text"], "label": knowledge.symptom_codes().get(s["value_text"], {}).get("label"),
                              "measured_at": s["measured_at"], "severity": db.loads(s["context"], {}).get("severity")} for s in symptoms],
                "assessment_findings": findings[:15], "open_alerts": rel_alerts, "limitations": limitations,
                "next_steps": list(dict.fromkeys(next_steps)) + specialized,
                "sources": list({s["id"]: s for r in risks for s in r["sources"]}.values()),
                "private_hidden": not private_ok and system == "behavioral"}
