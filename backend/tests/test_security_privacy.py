"""Stage 9 — authentication, authorization, privacy, audit."""
from datetime import timedelta

from astra import db


def t(m):
    return db.iso(db.utcnow() - timedelta(minutes=m))


def test_login_failures_and_token(client):
    assert client.post("/api/v1/auth/login", json={"username": "vega", "password": "wrong"}).status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401


def test_astronaut_cannot_view_other_crew_health(client, auth):
    h = auth("okafor")
    assert client.get("/api/v1/overview?astronaut_id=AST-001", headers=h).status_code == 403
    assert client.get("/api/v1/measurements/history?astronaut_id=AST-001", headers=h).status_code == 403
    assert client.get("/api/v1/overview", headers=h).status_code == 200


def test_admin_has_no_medical_access(client, auth):
    h = auth("admin")
    assert client.get("/api/v1/overview?astronaut_id=AST-001", headers=h).status_code == 403
    assert client.get("/api/v1/users", headers=h).status_code == 200
    assert client.get("/api/v1/users", headers=auth("vega")).status_code == 403


def test_private_checkin_visibility(client, auth):
    r = client.post("/api/v1/mood", headers=auth("okafor"), json={
        "assessed_at": t(5), "mood": 2, "stress": 4, "fatigue": None, "note_for_medical": "SYNTHETIC private note",
        "client_submission_id": "MOOD-PRIV-1"})
    assert r.status_code == 201, r.text
    assert "fatigue" in r.json()["record"]["skipped"]  # skipped answers recorded as missing
    # astronaut and flight surgeon can read; CMO and other crew cannot
    assert client.get("/api/v1/mood?astronaut_id=AST-003", headers=auth("okafor")).status_code == 200
    assert client.get("/api/v1/mood?astronaut_id=AST-003", headers=auth("ramirez")).status_code == 200
    assert client.get("/api/v1/mood?astronaut_id=AST-003", headers=auth("mori")).status_code == 403
    assert client.get("/api/v1/mood?astronaut_id=AST-003", headers=auth("vega")).status_code == 403
    # private observations hidden from CMO in history; private alert redacted
    hist = client.get("/api/v1/measurements/history?astronaut_id=AST-003&metric_code=mood", headers=auth("mori")).json()
    assert hist["items"] == [] and hist["hidden_private"] >= 1
    alerts = client.get("/api/v1/alerts?astronaut_id=AST-003", headers=auth("mori")).json()
    note = [a for a in alerts if a["rule_id"] == "DEMO-NOTE-TO-MEDICAL"]
    assert note and note[0]["redacted"] and "PRIVATE" in note[0]["explanation"]
    fs = [a for a in client.get("/api/v1/alerts?astronaut_id=AST-003", headers=auth("ramirez")).json() if a["rule_id"] == "DEMO-NOTE-TO-MEDICAL"]
    assert fs and not fs[0]["redacted"]
    # other astronaut sees nothing of it
    assert not [a for a in client.get("/api/v1/alerts", headers=auth("vega")).json() if a["astronaut_id"] == "AST-003"]


def test_cmo_only_checkin_for_self(client, auth):
    r = client.post("/api/v1/mood", headers=auth("mori"), json={"astronaut_id": "AST-003", "assessed_at": t(5), "mood": 3})
    assert r.status_code == 403


def test_audit_log_records_actions(client, auth):
    rows = client.get("/api/v1/audit?limit=500", headers=auth("admin")).json()
    actions = {r["action"] for r in rows}
    assert {"auth.login", "observations.ingest", "baseline.approve"} & actions
    assert client.get("/api/v1/audit", headers=auth("vega")).status_code == 403


def test_no_secrets_in_responses(client, auth):
    devs = client.get("/api/v1/devices", headers=auth("admin")).json()
    assert devs and all("api_key_hash" not in d for d in devs)
    me = client.get("/api/v1/auth/me", headers=auth("vega")).json()
    assert "password_hash" not in me


def test_openapi_and_docs(client):
    doc = client.get("/api/openapi.json").json()
    assert doc["openapi"].startswith("3.1")
    for p in ("/api/v1/telemetry", "/api/v1/measurements/manual", "/api/v1/measurements/history", "/api/v1/measurements/latest",
              "/api/v1/assessments", "/api/v1/astronauts", "/api/v1/missions", "/api/v1/devices", "/api/v1/baselines",
              "/api/v1/risks", "/api/v1/hazards", "/api/v1/countermeasures", "/api/v1/alerts", "/api/v1/medical-events",
              "/api/v1/medical-protocols", "/api/v1/medical-reports", "/api/v1/environment", "/api/v1/sleep", "/api/v1/mood",
              "/api/v1/exercise", "/api/v1/nutrition", "/api/v1/simulator", "/api/v1/sync", "/api/v1/measurements"):
        assert p in doc["paths"], p
    assert "TelemetryBatchIn" in doc["components"]["schemas"]
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/v1/does-not-exist").status_code == 404


def test_websocket_auth_and_privacy_filtering(client, auth):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=bad") as ws:
            ws.receive_json()
    tok_vega = auth("vega")["Authorization"].split()[1]
    tok_fs = auth("ramirez")["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={tok_vega}") as ws_v, client.websocket_connect(f"/ws?token={tok_fs}") as ws_f:
        assert ws_v.receive_json()["type"] == "hello"
        assert ws_f.receive_json()["type"] == "hello"
        r = client.post("/api/v1/mood", headers=auth("okafor"), json={"assessed_at": t(3), "mood": 3, "stress": 2,
                                                                          "client_submission_id": "MOOD-WS-1"})
        assert r.status_code == 201
        # flight surgeon receives the private observation event
        got = []
        for _ in range(10):
            m = ws_f.receive_json()
            got.append(m)
            if m["type"] == "observations.created":
                break
        assert any(m["type"] == "observations.created" and m["private"] for m in got)
        # vega (other astronaut) gets nothing about AST-003: send a ping and expect only pong
        ws_v.send_text("ping")
        assert ws_v.receive_json()["type"] == "pong"
