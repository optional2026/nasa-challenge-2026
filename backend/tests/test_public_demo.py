"""Public demonstration hardening and demo-data generation."""
import time

import pytest

from astra.protection import LIMITER, LIMITS


@pytest.fixture
def public(monkeypatch):
    monkeypatch.setenv("ASTRA_PUBLIC_DEMO", "1")
    LIMITER.reset()
    yield
    LIMITER.reset()


def test_security_headers_always_present(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert "server" not in {k.lower() for k in r.headers} or "uvicorn" not in r.headers.get("server", "")


def test_body_size_limit(client):
    r = client.post("/api/v1/auth/login", content=b"x" * (600 * 1024), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_public_config(client, monkeypatch):
    assert client.get("/api/v1/public-config").json()["public_demo"] is False
    monkeypatch.setenv("ASTRA_PUBLIC_DEMO", "1")
    j = client.get("/api/v1/public-config").json()
    assert j["public_demo"] is True and j["show_demo_password"] is False and j["data"] == "synthetic"


def test_rule_changes_blocked_in_public_mode(client, auth, public):
    r = client.post("/api/v1/rules/DEMO-RAPID-CHANGE/versions", headers=auth("ramirez"), json={"active": False})
    assert r.status_code == 403 and r.json()["error"]["code"] == "disabled_in_public_demo"


def test_login_rate_limit_per_visitor(client, public):
    n, _ = LIMITS["login"]
    hdr = {"CF-Connecting-IP": "203.0.113.7"}
    codes = [client.post("/api/v1/auth/login", json={"username": "x", "password": "y"}, headers=hdr).status_code for _ in range(n + 1)]
    assert codes[:n] == [401] * n and codes[n] == 429
    # successful sign-ins are never limited (a whole judging room may share one IP)
    for _ in range(n + 5):
        assert client.post("/api/v1/auth/login", json={"username": "vega", "password": "astra-demo"},
                           headers={"CF-Connecting-IP": "203.0.113.9"}).status_code == 200
    # another visitor is not affected
    assert client.post("/api/v1/auth/login", json={"username": "x", "password": "y"},
                       headers={"CF-Connecting-IP": "203.0.113.8"}).status_code == 401


def test_sensitive_files_not_served(client):
    for path in ("/backend/data/astra.sqlite3", "/data/.secret_key", "/data/device_keys.json", "/assets/../../backend/data/.secret_key"):
        r = client.get(path)
        assert b"SQLite format" not in r.content and b"astra_dev_" not in r.content


def test_scenario_for_selected_astronaut(client, auth):
    h = auth("ramirez")
    client.post("/api/v1/simulator/reset", headers=h)
    r = client.post("/api/v1/simulator/start", headers=h, json={"scenario": "illness", "speed": 96, "days": 10, "seed": 7,
                                                                 "astronaut_id": "AST-003"})
    assert r.status_code == 200 and r.json()["primary_astronaut_id"] == "AST-003"
    for _ in range(600):
        if client.get("/api/v1/simulator", headers=h).json()["state"] not in ("running", "paused"):
            break
        time.sleep(0.2)
    rules_003 = {a["rule_id"] for a in client.get("/api/v1/alerts?astronaut_id=AST-003&status=open", headers=h).json() if a["astronaut_id"] == "AST-003"}
    rules_001 = {a["rule_id"] for a in client.get("/api/v1/alerts?astronaut_id=AST-001&status=open", headers=h).json() if a["astronaut_id"] == "AST-001"}
    assert "DEMO-TEMP-SYMPTOMS" in rules_003 and "DEMO-TEMP-SYMPTOMS" not in rules_001
    assert client.post("/api/v1/simulator/start", headers=h, json={"scenario": "nominal", "astronaut_id": "AST-999"}).status_code in (404, 409, 422)
    client.post("/api/v1/simulator/reset", headers=h)
