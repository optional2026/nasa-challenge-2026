"""Structured medical reports for onboard medical personnel and ground flight surgeons."""
from __future__ import annotations

from datetime import timedelta

from .. import audit, db
from ..bus import BUS
from ..security import Principal
from . import ingestion, knowledge, medical_events, sync


def build(conn, event_id: str, outstanding_questions: list[str] | None = None) -> dict:
    e = medical_events.get(conn, event_id)
    if not e:
        raise LookupError(event_id)
    ast = db.one(conn, "SELECT id, name, call_sign, crew_role FROM astronauts WHERE id=?", (e["astronaut_id"],)) if e["astronaut_id"] else None
    mission = db.one(conn, "SELECT id, name, mission_type, start_utc FROM missions WHERE id=?", (e["mission_id"],))
    obs = []
    if e["observation_ids"]:
        q = ",".join("?" * len(e["observation_ids"]))
        obs = [ingestion.decode_observation(r) for r in db.all_(conn, f"SELECT * FROM observations WHERE id IN ({q}) ORDER BY measured_at", e["observation_ids"])]
    sym_rows = []
    window_ref = min([e["opened_at"]] + [o["measured_at"] for o in obs])
    if e["astronaut_id"]:
        sym_rows = db.all_(conn, "SELECT * FROM observations WHERE astronaut_id=? AND metric_code='symptom' AND measured_at>=? "
                                 "ORDER BY measured_at", (e["astronaut_id"], db.iso(db.parse_iso(window_ref) - timedelta(hours=24))))
    vocab = knowledge.symptom_codes()
    symptoms = [{"code": s["value_text"], "label": vocab.get(s["value_text"], {}).get("label", s["value_text"]),
                 "severity": db.loads(s["context"], {}).get("severity"), "reported_at": s["measured_at"],
                 "observation_id": s["id"]} for s in sym_rows]
    alerts = db.all_(conn, "SELECT * FROM alerts WHERE medical_event_id=? ORDER BY created_at", (event_id,))
    findings = [{"alert_id": a["id"], "severity": a["severity"], "rule": f"{a['rule_id']} v{a['rule_version']} ({a['rule_class']})",
                 "title": a["title"], "explanation": a["explanation"]} for a in alerts]
    baseline_comparisons = [db.loads(a["baseline_context"], {}) for a in alerts if a["baseline_context"] != "{}"]
    unchecked = [c["item"] for c in e["checklist_status"] if not c["checked"]]
    questions = list(outstanding_questions or []) + [f"Checklist item not yet confirmed: {u}" for u in unchecked]
    content = {
        "report_type": "ASTRA medical event report",
        "synthetic": bool(e["is_synthetic"]),
        "astronaut": ast, "mission": mission,
        "event": {"id": e["id"], "title": e["title"], "opened_at": e["opened_at"], "state": e["state"],
                  "severity": e["severity"], "risk_id": e["risk_id"], "protocol_id": e["protocol_id"]},
        "symptoms": symptoms,
        "measurements": [{"id": o["id"], "metric": o["metric_code"], "value": o["value"], "unit": o["unit"],
                          "original": f"{o['original_value']} {o['original_unit']}", "measured_at": o["measured_at"],
                          "source": o["source_type"], "device_id": o["device_id"], "quality": o["quality"],
                          "synthetic": o["is_synthetic"]} for o in obs],
        "baseline_comparisons": baseline_comparisons,
        "assessment_findings": findings,
        "actions_taken": [{"at": a["performed_at"], "by": a["performed_by"], "type": a["action_type"],
                           "description": a["description"]} for a in e["actions"]],
        "state_history": [{"at": t["at"], "from": t["from_state"], "to": t["to_state"], "by": t["actor"], "reason": t["reason"]}
                          for t in e["transitions"]],
        "outstanding_questions": questions,
        "current_status": e["state"],
        "supporting_records": {"alert_ids": [a["id"] for a in alerts], "observation_ids": e["observation_ids"],
                               "assessment_ids": sorted({a["assessment_id"] for a in alerts if a["assessment_id"]})},
        "disclaimer": "Decision-support output from the ASTRA prototype. Not a diagnosis. Rules marked DEMONSTRATION_ONLY are synthetic.",
    }
    return content


def render_text(c: dict) -> str:
    L = []
    if c["synthetic"]:
        L.append("*** SYNTHETIC DATA — DEMONSTRATION REPORT ***")
    a, m, ev = c["astronaut"] or {}, c["mission"] or {}, c["event"]
    L += [f"ASTRA MEDICAL EVENT REPORT — {ev['id']}", f"Mission: {m.get('name')} ({m.get('id')})",
          f"Astronaut: {a.get('name')} ({a.get('id')})", f"Event: {ev['title']}",
          f"Opened: {ev['opened_at']}   Severity: {ev['severity']}   Current status: {c['current_status']}", ""]
    L.append("SYMPTOMS")
    L += [f"  - {s['label']} (severity {s['severity'] or 'n/a'}) at {s['reported_at']}" for s in c["symptoms"]] or ["  none reported"]
    L.append("\nMEASUREMENTS")
    L += [f"  - {x['measured_at']} {x['metric']}: {x['value']} {x['unit']} [source {x['source']}, device {x['device_id'] or '-'}, quality {x['quality']}]"
          for x in c["measurements"]] or ["  none linked"]
    L.append("\nASSESSMENT FINDINGS")
    L += [f"  - [{f['severity']}] {f['title']} — {f['explanation']} ({f['rule']})" for f in c["assessment_findings"]]
    L.append("\nACTIONS TAKEN")
    L += [f"  - {x['at']} {x['by']}: {x['type']} — {x['description']}" for x in c["actions_taken"]] or ["  none recorded"]
    L.append("\nOUTSTANDING QUESTIONS")
    L += [f"  - {q}" for q in c["outstanding_questions"]] or ["  none"]
    L.append("\n" + c["disclaimer"])
    return "\n".join(L)


def create(conn, actor: Principal | str, event_id: str, outstanding_questions=None, queue: bool = True) -> dict:
    content = build(conn, event_id, outstanding_questions)
    text = render_text(content)
    rid = db.new_id("RPT")
    e = db.one(conn, "SELECT * FROM medical_events WHERE id=?", (event_id,))
    actor_name = actor.actor if isinstance(actor, Principal) else actor
    with db.transaction(conn):
        db.insert(conn, "medical_reports", {
            "id": rid, "event_id": event_id, "astronaut_id": e["astronaut_id"], "mission_id": e["mission_id"],
            "created_at": db.now_iso(), "created_by": actor_name, "content": db.dumps(content), "rendered_text": text,
            "content_hash": db.sha256(content), "sync_status": "local", "is_private": 1,
            "is_synthetic": e["is_synthetic"], "sim_run_id": e["sim_run_id"]})
        medical_events.add_action(conn, actor, event_id, "report", f"Medical report {rid} generated")
        audit.record(conn, actor, "medical_report.create", "medical_report", rid, {"event_id": event_id})
        if queue:
            sync.enqueue(conn, "medical_report", rid, {"report_id": rid, "content": content}, private=True,
                         priority=1 if e["severity"] == "URGENT" else 3)
            conn.execute("UPDATE medical_reports SET sync_status='queued' WHERE id=?", (rid,))
    BUS.publish("medical_report.created", {"id": rid, "event_id": event_id}, astronaut_id=e["astronaut_id"], private=True)
    return get(conn, rid)


def get(conn, report_id: str) -> dict | None:
    r = db.one(conn, "SELECT * FROM medical_reports WHERE id=?", (report_id,))
    if r:
        r["content"] = db.loads(r["content"])
        r["is_private"] = bool(r["is_private"])
        r["is_synthetic"] = bool(r["is_synthetic"])
        from .. import config
        if config.deployment() != "standalone":
            from . import replication
            r["transmission"] = replication.record_sync_info(conn, "medical_report", report_id)
        else:
            r["transmission"] = db.one(conn, "SELECT status, attempts, delivered_at, acknowledged_at, acknowledged_by, last_error "
                                             "FROM sync_queue WHERE item_type='medical_report' AND item_id=? "
                                             "ORDER BY created_at DESC LIMIT 1", (report_id,))
    return r
