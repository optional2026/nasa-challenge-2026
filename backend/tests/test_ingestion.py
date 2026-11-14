"""Stage 2 — data models, validation, units, provenance, idempotency."""
from datetime import timedelta

from astra import db, units

M = "MSN-ARES-T1"


def now(minutes_ago=5):
    return db.iso(db.utcnow() - timedelta(minutes=minutes_ago))


def obs(**kw):
    base = {"astronaut_id": "AST-003", "mission_id": M, "metric_code": "heart_rate", "value": 60, "unit": "bpm",
            "measured_at": now(), "source_type": "wearable", "device_id": "DEV-HRW-003", "quality": "valid",
            "context": {"activity": "resting"}}
    base.update(kw)
    return base


def post(client, keys, dev, items, **headers):
    return client.post("/api/v1/telemetry", json={"observations": items}, headers={"X-Device-Key": keys[dev], **headers})


def test_unit_conversions():
    assert abs(units.convert(98.6, "degF", "degC") - 37.0) < 1e-6
    assert abs(units.convert(5.0, "mmol/L", "mg/dL") - 90.08) < 1e-6
    assert abs(units.convert(1.0, "kPa", "mmHg") - 7.500617) < 1e-6
    assert abs(units.convert(24.0, "mGy/d", "uGy/h") - 1000.0) < 1e-6


def test_telemetry_accepts_and_preserves_provenance(client, device_keys, auth):
    r = post(client, device_keys, "DEV-HRW-003", [obs(observation_id="T-PROV-1", value=61)])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["processing_status"] == "complete" and j["accepted"][0]["status"] == "accepted"
    o = client.get("/api/v1/measurements/T-PROV-1", headers=auth("okafor")).json()
    assert o["device_id"] == "DEV-HRW-003" and o["source_type"] == "wearable"
    assert o["original_value"] == 61 and o["original_unit"] == "bpm"
    assert o["received_at"] >= o["measured_at"]
    assert o["is_synthetic"] is True  # simulated device => SYNTHETIC label
    assert o["measured_at"].endswith("Z")


def test_fahrenheit_converted_original_kept(client, auth):
    r = client.post("/api/v1/measurements/manual", headers=auth("okafor"), json={
        "measured_at": now(), "items": [{"metric_code": "body_temperature", "value": 98.6, "unit": "degF"}],
        "method": "oral", "quality": "valid", "client_submission_id": "TEMP-F-1"})
    assert r.status_code == 201, r.text
    oid = r.json()["accepted"][0]["observation_id"]
    o = client.get(f"/api/v1/measurements/{oid}", headers=auth("okafor")).json()
    assert abs(o["value"] - 37.0) < 0.01 and o["unit"] == "degC"
    assert o["original_value"] == 98.6 and o["original_unit"] == "degF"


def test_rejections(client, device_keys):
    items = [
        obs(observation_id="R1", unit="beats"),                       # unsupported unit
        obs(observation_id="R2", value=900),                           # implausible input
        obs(observation_id="R3", measured_at=db.iso(db.utcnow() + timedelta(hours=2))),  # future
        obs(observation_id="R4", metric_code="nonsense"),              # unknown metric
        obs(observation_id="R5", astronaut_id="AST-999"),              # unknown astronaut
        obs(observation_id="R6", measured_at="2026-11-14T10:00:00"),   # missing timezone
        obs(observation_id="R7", value="fast"),                        # wrong type
        obs(observation_id="R8", astronaut_id="AST-001"),              # device assigned to another astronaut
    ]
    r = post(client, device_keys, "DEV-HRW-003", items)
    j = r.json()
    assert j["processing_status"] == "rejected"
    assert len(j["rejected"]) == len(items) and not j["accepted"]
    assert all(x["errors"] for x in j["rejected"])


def test_idempotency_and_conflict(client, device_keys):
    item = obs(observation_id="IDEM-1", value=62)
    a = post(client, device_keys, "DEV-HRW-003", [item]).json()
    b = post(client, device_keys, "DEV-HRW-003", [item]).json()
    assert a["accepted"][0]["status"] == "accepted" and b["accepted"][0]["status"] == "duplicate"
    c = post(client, device_keys, "DEV-HRW-003", [dict(item, value=99)]).json()
    assert c["rejected"] and "conflict" in c["rejected"][0]["errors"][0]


def test_batch_idempotency_key(client, device_keys):
    item = obs(observation_id="IDEM-BATCH-1")
    a = post(client, device_keys, "DEV-HRW-003", [item], **{"Idempotency-Key": "batch-xyz"}).json()
    b = post(client, device_keys, "DEV-HRW-003", [item], **{"Idempotency-Key": "batch-xyz"}).json()
    assert b.get("idempotent_replay") is True and b["accepted"] == a["accepted"]


def test_environment_vs_astronaut_subject(client, device_keys):
    env = {"mission_id": M, "metric_code": "cabin_co2", "value": 2.0, "unit": "mmHg", "measured_at": now(),
           "source_type": "environmental_sensor", "device_id": "DEV-ENV-LAB", "quality": "valid", "location": "LAB"}
    ok = post(client, device_keys, "DEV-ENV-LAB", [env]).json()
    assert ok["processing_status"] == "complete"
    bad = post(client, device_keys, "DEV-ENV-LAB", [dict(env, astronaut_id="AST-003")]).json()
    assert bad["rejected"] and "environmental" in bad["rejected"][0]["errors"][0]
    wrong_metric = post(client, device_keys, "DEV-ENV-LAB", [dict(env, metric_code="heart_rate", unit="bpm", value=60,
                                                                 astronaut_id="AST-003")]).json()
    assert wrong_metric["rejected"]


def test_device_key_required_and_checked(client):
    r = client.post("/api/v1/telemetry", json={"observations": [obs()]})
    assert r.status_code == 401
    r = client.post("/api/v1/telemetry", json={"observations": [obs()]}, headers={"X-Device-Key": "astra_dev_wrong"})
    assert r.status_code == 401


def test_manual_blood_pressure_panel_and_symptoms(client, auth):
    r = client.post("/api/v1/measurements/manual", headers=auth("okafor"), json={
        "measured_at": now(), "source_type": "medical_device", "device_id": "DEV-BPM-01", "quality": "valid",
        "context": {"activity": "resting"}, "client_submission_id": "BP-PANEL-1",
        "items": [{"metric_code": "bp_systolic", "value": 110, "unit": "mmHg"},
                  {"metric_code": "bp_diastolic", "value": 70, "unit": "mmHg"}],
        "symptoms": [{"code": "headache", "severity": 2}]})
    assert r.status_code == 201, r.text
    acc = r.json()["accepted"]
    assert {a["metric_code"] for a in acc} == {"bp_systolic", "bp_diastolic", "symptom"}
    # retry with the same client_submission_id is not duplicated
    r2 = client.post("/api/v1/measurements/manual", headers=auth("okafor"), json={
        "measured_at": r.request and db.iso(db.utcnow() - timedelta(minutes=5)), "source_type": "medical_device",
        "device_id": "DEV-BPM-01", "quality": "valid", "context": {"activity": "resting"}, "client_submission_id": "BP-PANEL-1",
        "items": [{"metric_code": "bp_systolic", "value": 110, "unit": "mmHg"}]})
    assert r2.status_code in (201, 422)


def test_astronaut_cannot_submit_for_other_astronaut(client, auth):
    r = client.post("/api/v1/measurements/manual", headers=auth("okafor"), json={
        "astronaut_id": "AST-001", "measured_at": now(), "items": [{"metric_code": "heart_rate", "value": 60, "unit": "bpm"}]})
    assert r.status_code == 422
    assert "own" in str(r.json())


def test_clinician_only_indicator(client, auth):
    r = client.post("/api/v1/measurements/manual", headers=auth("okafor"), json={
        "measured_at": now(), "items": [{"metric_code": "lab_result", "value": {"test": "CBC", "summary": "x"}, "unit": "structured"}]})
    assert r.status_code == 422
    r = client.post("/api/v1/measurements/manual", headers=auth("mori"), json={
        "astronaut_id": "AST-003", "source_type": "clinician", "measured_at": now(), "quality": "valid",
        "items": [{"metric_code": "lab_result", "value": {"test": "CBC", "summary": "SYNTHETIC test entry"}, "unit": "structured"}]})
    assert r.status_code == 201, r.text


def test_history_pagination_and_aggregation(client, auth):
    h = auth("okafor")
    r = client.get("/api/v1/measurements/history?metric_code=heart_rate&limit=5&offset=0", headers=h).json()
    assert r["limit"] == 5 and len(r["items"]) <= 5 and r["total"] >= len(r["items"])
    r = client.get("/api/v1/measurements/history?metric_code=heart_rate&bucket=day&limit=1000", headers=h).json()
    assert r["buckets"] and {"bucket_start", "mean", "min", "max", "count"} <= set(r["buckets"][0])
    latest = client.get("/api/v1/measurements/latest", headers=h).json()
    assert any(x["metric_code"] == "heart_rate" for x in latest)


def test_device_adapter_endpoint(client, device_keys):
    r = client.post("/api/v1/devices/DEV-OXI-01/readings", headers={"X-Device-Key": device_keys["DEV-OXI-01"]},
                    json={"reading": {"spo2_pct": 97, "pulse_bpm": 60, "signal_quality": 0.4}, "measured_at": now(),
                          "reading_id": "RD-OXI-ADAPTER-1"})
    assert r.status_code == 200, r.text
    # shared device has no astronaut assigned -> reading cannot be attributed without astronaut_id
    assert r.json()["rejected"]
    r = client.post("/api/v1/devices/DEV-OXI-01/readings", headers={"X-Device-Key": device_keys["DEV-OXI-01"]},
                    json={"reading": {"spo2_pct": 97, "pulse_bpm": 60, "signal_quality": 0.4}, "measured_at": now(),
                          "reading_id": "RD-OXI-ADAPTER-2", "astronaut_id": "AST-003"})
    j = r.json()
    assert j["processing_status"] == "complete", j
    # low signal quality is preserved as 'questionable', never silently upgraded
    assert {a["metric_code"] for a in j["accepted"]} == {"spo2", "heart_rate"}
    r = client.post("/api/v1/devices/DEV-THM-01/readings", headers={"X-Device-Key": device_keys["DEV-OXI-01"]},
                    json={"reading": {"temp": 36.6}, "measured_at": now()})
    assert r.status_code == 403


def test_personal_dosimeter_adapter(client, device_keys):
    r = client.post("/api/v1/devices/DEV-DOS-003/readings", headers={"X-Device-Key": device_keys["DEV-DOS-003"]},
                    json={"reading": {"dose_rate_uGy_h": 9.5, "cumulative_mGy": 2.1}, "measured_at": now(), "reading_id": "RD-DOS-1"})
    j = r.json()
    assert j["processing_status"] == "complete", j
    assert {a["metric_code"] for a in j["accepted"]} == {"radiation_dose_rate", "radiation_dose_cumulative"}
