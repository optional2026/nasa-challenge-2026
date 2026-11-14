"""Stage 5 — simulator: deterministic scenarios through the real API pipeline."""
import time

import pytest

from simulator.scenarios import SCENARIOS


def run(client, h, scenario, days=4, speed=96):
    r = client.post("/api/v1/simulator/start", headers=h, json={"scenario": scenario, "speed": speed, "days": days})
    assert r.status_code == 200, r.text
    for _ in range(600):
        s = client.get("/api/v1/simulator", headers=h).json()
        if s["state"] not in ("running", "paused"):
            return s
        time.sleep(0.2)
    raise AssertionError("simulation did not finish")


def test_eight_scenarios_defined():
    assert set(SCENARIOS) == {"nominal", "cardiovascular", "sleep_fatigue", "illness", "radiation_event", "musculoskeletal",
                              "behavioral", "emergency"}


def test_controls_and_reset(client, auth):
    h = auth("ramirez")
    r = client.post("/api/v1/simulator/start", headers=h, json={"scenario": "nominal", "speed": 1, "days": 3})
    assert r.json()["state"] == "running" and r.json()["label"] == "SYNTHETIC"
    assert client.post("/api/v1/simulator/start", headers=h, json={"scenario": "nominal"}).status_code == 409
    assert client.post("/api/v1/simulator/pause", headers=h).json()["state"] == "paused"
    clock = client.get("/api/v1/simulator", headers=h).json()["sim_clock"]
    time.sleep(0.6)
    assert client.get("/api/v1/simulator", headers=h).json()["sim_clock"] == clock  # paused clock does not advance
    assert client.post("/api/v1/simulator/resume", headers=h).json()["state"] == "running"
    assert client.post("/api/v1/simulator/speed", headers=h, json={"speed": 48}).json()["speed_sim_hours_per_second"] == 48
    s = client.post("/api/v1/simulator/stop", headers=h).json()
    assert s["state"] == "stopped" and s["mission_elapsed"]["mission_day"] >= 1
    r = client.post("/api/v1/simulator/reset", headers=h).json()
    assert r["status"]["state"] == "idle" and r["deleted"]["observations"] >= 1


def test_emergency_scenario_end_to_end(client, auth):
    h = auth("ramirez")
    client.post("/api/v1/simulator/reset", headers=h)
    s = run(client, h, "emergency", days=4)
    assert s["state"] == "completed" and s["counts"]["rejected"] == 0
    alerts = client.get("/api/v1/alerts?status=open&astronaut_id=AST-001", headers=h).json()
    urgent = [a for a in alerts if a["severity"] == "URGENT" and a["rule_id"] == "DEMO-CARDIORESP-COMBO"]
    assert urgent and urgent[0]["is_synthetic"] and urgent[0]["medical_event_id"]
    obs = client.get("/api/v1/measurements/history?astronaut_id=AST-001&metric_code=spo2&order=desc&limit=3", headers=h).json()
    assert all(o["is_synthetic"] for o in obs["items"])
    env = client.get("/api/v1/environment", headers=h).json()
    assert env["readings"] and all(r["is_synthetic"] for r in env["readings"])


@pytest.mark.parametrize("scenario,rule", [("radiation_event", "DEMO-RADIATION-SPIKE"), ("behavioral", "DEMO-BEHAVIORAL-TREND")])
def test_scenarios_produce_expected_findings(client, auth, scenario, rule):
    h = auth("ramirez")
    client.post("/api/v1/simulator/reset", headers=h)
    s = run(client, h, scenario, days=10)
    assert s["counts"]["rejected"] == 0
    rules = {a["rule_id"] for a in client.get("/api/v1/alerts?status=open", headers=h).json()}
    assert rule in rules, rules
    client.post("/api/v1/simulator/reset", headers=h)
