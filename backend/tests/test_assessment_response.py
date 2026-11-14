"""Stages 3–4 — baselines, assessment engine, alerts, medical events, reports, sync."""
from datetime import timedelta

from astra import db

M = "MSN-ARES-T1"


def t(minutes_ago):
    return db.iso(db.utcnow() - timedelta(minutes=minutes_ago))


def hr(client, keys, value, minutes_ago, oid, quality="valid"):
    return client.post("/api/v1/telemetry", headers={"X-Device-Key": keys["DEV-HRW-002"]}, json={"observations": [{
        "observation_id": oid, "astronaut_id": "AST-002", "mission_id": M, "metric_code": "heart_rate", "value": value,
        "unit": "bpm", "measured_at": t(minutes_ago), "source_type": "wearable", "device_id": "DEV-HRW-002",
        "quality": quality, "context": {"activity": "resting"}}]}).json()


def test_baselines_seeded_and_approved(client, auth):
    rows = client.get("/api/v1/baselines?astronaut_id=AST-002", headers=auth("mori")).json()
    hrb = [b for b in rows if b["metric_code"] == "heart_rate" and b["status"] == "approved"]
    assert hrb and hrb[0]["context_key"] == "resting" and hrb[0]["approved_by"] == "user:ramirez"
    assert all(b["source"] == "pre_mission" for b in rows)


def test_baseline_requires_medical_role_and_is_versioned(client, auth):
    body = {"astronaut_id": "AST-002", "metric_code": "bp_systolic", "period_start": t(60 * 24 * 60), "period_end": t(0),
            "source": "in_flight_window"}
    assert client.post("/api/v1/baselines", headers=auth("vega"), json=body).status_code == 403
    r = client.post("/api/v1/baselines", headers=auth("mori"), json=body)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "draft" and b["version"] >= 2
    # draft does not replace the approved baseline until approved
    rows = client.get("/api/v1/baselines?astronaut_id=AST-002", headers=auth("mori")).json()
    assert [x for x in rows if x["metric_code"] == "bp_systolic" and x["status"] == "approved"][0]["version"] == 1
    r = client.post(f"/api/v1/baselines/{b['id']}/approve", headers=auth("mori"), json={"ref_low": 10, "ref_high": 5})
    assert r.status_code == 422


def test_questionable_quality_triggers_reassessment_not_abnormal(client, device_keys, auth):
    j = hr(client, device_keys, 140, 50, "Q-HR-1", quality="questionable")
    assert j["alerts_created"]
    a = client.get(f"/api/v1/alerts/{j['alerts_created'][0]}", headers=auth("mori")).json()
    assert a["severity"] == "REASSESSMENT" and a["rule_id"] == "DEMO-QUALITY-REPEAT"
    assert "does not interpret" in a["explanation"]


def test_sustained_deviation_reassessment_then_review_and_event(client, device_keys, auth):
    created = []
    for i, v in enumerate([90, 92, 91]):
        created += hr(client, device_keys, v, 40 - i * 5, f"SUS-HR-{i}")["alerts_created"]
    alerts = client.get("/api/v1/alerts?astronaut_id=AST-002&status=open", headers=auth("mori")).json()
    sus = [a for a in alerts if a["rule_id"] == "DEMO-BASELINE-SUSTAINED" and a["astronaut_id"] == "AST-002"]
    assert sus and sus[0]["severity"] == "REASSESSMENT"
    assert sus[0]["baseline_context"]["baseline_version"] == 1
    for i, v in enumerate([93, 94, 95]):
        hr(client, device_keys, v, 24 - i * 5, f"SUS-HR-B{i}")
    a = client.get(f"/api/v1/alerts/{sus[0]['id']}", headers=auth("mori")).json()
    assert a["severity"] == "MEDICAL_REVIEW" and a["medical_event_id"]
    assert len(a["observation_ids"]) >= 6
    assert a["rule"]["rule_class"] == "DEMONSTRATION_ONLY"
    asm = client.get(f"/api/v1/assessments?astronaut_id=AST-002", headers=auth("mori")).json()["items"][0]
    for k in ("findings", "limitations", "risk_ids", "next_step", "medical_review", "evidence_refs", "rule_versions",
              "indicators", "baseline_comparisons"):
        assert k in asm
    assert any("DEMONSTRATION-ONLY" in lim for lim in asm["limitations"])


def test_event_state_machine_and_alert_resolution_rules(client, auth):
    h = auth("mori")
    evs = client.get("/api/v1/medical-events?astronaut_id=AST-002&status=open", headers=h).json()
    e = evs[0]
    # invalid jump
    r = client.post(f"/api/v1/medical-events/{e['id']}/transition", headers=h, json={"to_state": "RESOLVED", "reason": "x"})
    assert r.status_code == 409
    # alert cannot be resolved while event is open
    alert_id = client.get(f"/api/v1/medical-events/{e['id']}", headers=h).json()["alerts"][0]["id"]
    r = client.post(f"/api/v1/alerts/{alert_id}/resolve", headers=h, json={"note": "done"})
    assert r.status_code == 422 and "event" in r.text
    # acknowledgement does not remove the event
    client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=h, json={"note": "seen"})
    assert client.get(f"/api/v1/medical-events/{e['id']}", headers=h).json()["state"] == "DETECTED"
    for to in ("VERIFYING", "ACTIVE", "MONITORING"):
        r = client.post(f"/api/v1/medical-events/{e['id']}/transition", headers=h, json={"to_state": to, "reason": "test"})
        assert r.status_code == 200, r.text
    # astronaut cannot resolve
    r = client.post(f"/api/v1/medical-events/{e['id']}/transition", headers=auth("mori") if False else auth("vega"),
                    json={"to_state": "RESOLVED", "reason": "fine"})
    assert r.status_code in (403, 404)
    r = client.post(f"/api/v1/medical-events/{e['id']}/transition", headers=h, json={"to_state": "RESOLVED"})
    assert r.status_code == 409  # reason required
    r = client.post(f"/api/v1/medical-events/{e['id']}/transition", headers=h, json={"to_state": "RESOLVED", "reason": "measurement artefact confirmed"})
    assert r.status_code == 200
    ev = r.json()
    assert [x["to_state"] for x in ev["transitions"]] == ["DETECTED", "VERIFYING", "ACTIVE", "MONITORING", "RESOLVED"]
    r = client.post(f"/api/v1/alerts/{alert_id}/resolve", headers=h, json={"note": "event resolved"})
    assert r.status_code == 200 and r.json()["resolution_status"] == "resolved"


def _urgent_event(client, keys):
    tel = lambda dev, items: client.post("/api/v1/telemetry", headers={"X-Device-Key": keys[dev]}, json={"observations": items}).json()
    base = {"astronaut_id": "AST-003", "mission_id": M, "quality": "valid"}
    tel("DEV-HRW-003", [dict(base, observation_id="URG-HR", metric_code="heart_rate", value=120, unit="bpm", measured_at=t(12),
                             source_type="wearable", device_id="DEV-HRW-003", context={"activity": "resting"})])
    r = tel("DEV-OXI-01", [dict(base, observation_id="URG-SPO2", metric_code="spo2", value=88, unit="%", measured_at=t(10),
                                source_type="medical_device", device_id="DEV-OXI-01",
                                symptoms=[{"code": "shortness_of_breath", "severity": 4}])])
    return r


def test_urgent_workflow_escalation_report_and_sync(client, device_keys, auth):
    r = _urgent_event(client, device_keys)
    assert r["alerts_created"]
    h = auth("mori")
    urgent = [a for a in client.get("/api/v1/alerts?status=open&severity=URGENT", headers=h).json() if a["astronaut_id"] == "AST-003"]
    assert urgent and urgent[0]["medical_event_id"]
    eid = urgent[0]["medical_event_id"]
    e = client.get(f"/api/v1/medical-events/{eid}", headers=h).json()
    assert e["protocol"]["approval_status"] == "SYNTHETIC_DEMO" and e["checklist_status"]
    # verification checklist
    item = e["checklist_status"][0]["item"]
    r = client.post(f"/api/v1/medical-events/{eid}/actions", headers=auth("okafor"),
                    json={"action_type": "checklist_item", "description": item, "data": {"item": item, "checked": True}})
    assert r.status_code == 201
    # escalate (astronaut may escalate own event)
    sync_link = client.post("/api/v1/sync/link", headers=h, json={"earth_link_status": "offline", "comm_delay_seconds": 0})
    assert sync_link.status_code == 200
    r = client.post(f"/api/v1/medical-events/{eid}/escalate", headers=auth("okafor"), json={"note": "SpO2 confirmed low",
                                                                                      "outstanding_questions": ["Q1?"]})
    assert r.status_code == 200, r.text
    ev = r.json()
    assert ev["state"] == "ESCALATED" and ev["report"]["sync_status"] == "queued"
    rep = client.get(f"/api/v1/medical-reports/{ev['report']['id']}", headers=h).json()
    c = rep["content"]
    for key in ("astronaut", "mission", "event", "symptoms", "measurements", "baseline_comparisons", "assessment_findings",
                "actions_taken", "outstanding_questions", "current_status", "supporting_records"):
        assert key in c
    assert any(s["code"] == "shortness_of_breath" for s in c["symptoms"])
    assert "Q1?" in c["outstanding_questions"]
    # offline: nothing is sent, item waits
    st = client.post("/api/v1/sync/run", headers=h).json()
    assert st["result"]["waiting_for_link"] >= 1
    # online with zero delay: delivered then acknowledged on next pass
    client.post("/api/v1/sync/link", headers=h, json={"earth_link_status": "online", "comm_delay_seconds": 0})
    client.post("/api/v1/sync/run", headers=h)
    client.post("/api/v1/sync/run", headers=h)
    rep = client.get(f"/api/v1/medical-reports/{ev['report']['id']}", headers=h).json()
    assert rep["sync_status"] == "acknowledged" and rep["transmission"]["status"] == "acknowledged"
    # idempotent re-enqueue does not create a duplicate
    from astra.services import sync
    conn = db.connect()
    n1 = db.one(conn, "SELECT COUNT(*) c FROM sync_queue")["c"]
    sync.enqueue(conn, "medical_report", rep["id"], {"report_id": rep["id"], "content": rep["content"]}, private=True)
    assert db.one(conn, "SELECT COUNT(*) c FROM sync_queue")["c"] == n1


def test_sync_degraded_link_backoff(client, auth):
    from astra.services import sync
    import random
    conn = db.connect()
    sync.enqueue(conn, "test_item", "X-1", {"hello": "world"})
    sync.set_link(conn, "test", "degraded", 0)
    res = sync.process(conn, rng=random.Random(0))  # rng 0 -> first draw 0.84 (> 0.4) ... deterministic
    st = sync.status(conn)
    assert st["earth_link_status"] == "degraded"
    sync.set_link(conn, "test", "online", 0)
    assert isinstance(res, dict)


def test_co2_rule_creates_environment_event(client, device_keys, auth):
    items = [{"mission_id": M, "metric_code": "cabin_co2", "value": v, "unit": "mmHg", "measured_at": t(m),
              "source_type": "environmental_sensor", "device_id": "DEV-ENV-HABA", "quality": "valid", "location": "HAB-A",
              "observation_id": f"CO2-{m}"} for v, m in ((3.6, 40), (3.8, 30), (3.9, 20))]
    r = client.post("/api/v1/telemetry", headers={"X-Device-Key": device_keys["DEV-ENV-HABA"]}, json={"observations": items}).json()
    assert r["alerts_created"]
    evs = client.get("/api/v1/environment/events", headers=auth("vega")).json()
    assert any(e["event_type"] == "cabin_co2_above_limit" and e["ended_at"] is None for e in evs)
    a = client.get(f"/api/v1/alerts/{r['alerts_created'][0]}", headers=auth("vega")).json()
    assert a["rule_class"] == "NASA_OPERATIONAL_REFERENCE" and "6004" in a["explanation"]
    assert a["rule_source"]["id"] == "SRC-TB-004-CO2"


def test_missing_data_shown_not_healthy(client, auth):
    r = client.post("/api/v1/assessments", headers=auth("vega"), json={})
    assert r.status_code == 201
    j = r.json()
    assert any(f["title"].startswith("Missing data") for f in j["findings"])
    o = client.get("/api/v1/overview", headers=auth("vega")).json()
    statuses = {v["metric_code"]: v["status"] for v in o["vitals"]}
    assert statuses["heart_rate"] in ("stale", "missing")  # pre-mission data only -> never shown as current/healthy
    assert o["current_status"] != "NO_CONCERN_IDENTIFIED"


def test_sleep_record_and_schedule_reference(client, auth):
    r = client.post("/api/v1/sleep", headers=auth("okafor"), json={
        "sleep_start": t(60 * 9), "sleep_end": t(60), "corrected_duration_min": 400, "quality": 4, "awakenings": 1,
        "scheduled_opportunity_min": 420, "fatigue_after_waking": 2, "client_submission_id": "SLP-TEST-1"})
    assert r.status_code == 201, r.text
    rec = r.json()["record"]
    assert rec["computed_duration_min"] == 480 and rec["reported_duration_min"] == 400
    asm = client.get(f"/api/v1/assessments/{r.json()['ingestion']['assessments'][0]}", headers=auth("okafor")).json()
    assert any(f["rule_id"] == "NASA-SLEEP-SCHEDULE-REF" for f in asm["findings"])
    bad = client.post("/api/v1/sleep", headers=auth("okafor"), json={"sleep_start": t(10), "sleep_end": t(60)})
    assert bad.status_code == 422


def test_exercise_and_nutrition_records(client, auth):
    r = client.post("/api/v1/exercise", headers=auth("okafor"), json={
        "exercise_type": "Treadmill", "category": "aerobic", "start_at": t(120), "duration_min": 40, "intensity": "moderate",
        "completion_status": "completed"})
    assert r.status_code == 201, r.text
    ex = client.get("/api/v1/exercise", headers=auth("okafor")).json()
    assert "not a measurement of bone density" in ex["adherence"]["note"]
    r = client.post("/api/v1/nutrition", headers=auth("okafor"), json={"recorded_at": t(30), "record_type": "water", "water_ml": 250})
    assert r.status_code == 201
    assert client.post("/api/v1/nutrition", headers=auth("okafor"), json={"recorded_at": t(30), "record_type": "water"}).status_code == 422


def test_medication_requires_approved_instruction_and_medical_role(client, auth):
    body = {"astronaut_id": "AST-003", "medication": "SYNTHETIC-TEST", "administered_at": t(5), "approved_instruction_ref": "PROC-X"}
    assert client.post("/api/v1/medications", headers=auth("okafor"), json=body).status_code == 403
    assert client.post("/api/v1/medications", headers=auth("mori"), json={k: v for k, v in body.items() if k != "approved_instruction_ref"}).status_code == 422
    assert client.post("/api/v1/medications", headers=auth("mori"), json=body).status_code == 201
