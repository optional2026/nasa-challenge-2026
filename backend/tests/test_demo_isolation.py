"""Demo-data generator isolation (bug fix): generating demo data as one astronaut must not create, change or
remove any record of another crew member. Uses three crew profiles (A = Vega, B = Okafor, C = Mori/CMO)."""
import time

from astra import db

API = "/api/v1"
A, B, C = "AST-001", "AST-003", "AST-002"
TABLES = ("observations", "health_assessments", "alerts", "medical_events", "sleep_records", "mood_assessments",
          "exercise_records", "nutrition_records", "medical_reports", "medical_history", "health_baselines")


def snapshot(ast):
    """Fingerprint of every per-astronaut record (ids + updated timestamps where present)."""
    out = {}
    with db.session() as conn:
        for t in TABLES:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()}
            extra = ", updated_at" if "updated_at" in cols else ""
            out[t] = sorted(tuple(r.values()) for r in db.all_(conn, f"SELECT id{extra} FROM {t} WHERE astronaut_id=?", (ast,)))
    return out


def sim_count(ast):
    with db.session() as conn:
        return db.one(conn, "SELECT COUNT(*) c FROM observations WHERE astronaut_id=? AND sim_run_id IS NOT NULL", (ast,))["c"]


def select(client, username):
    crew = client.get(f"{API}/auth/profiles").json()["crew"]
    uid = next(p["user_id"] for p in crew if p["username"] == username)
    r = client.post(f"{API}/auth/select-profile", json={"user_id": uid})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def generate(client, h, scenario, days=3, replace=True):
    if replace:
        assert client.post(f"{API}/simulator/reset", headers=h).status_code == 200
    r = client.post(f"{API}/simulator/start", headers=h, json={"scenario": scenario, "days": days, "speed": 96, "seed": 11})
    assert r.status_code == 200, r.text
    for _ in range(600):
        s = client.get(f"{API}/simulator", headers=h).json()
        if s["state"] not in ("running", "paused"):
            assert s["state"] == "completed", s
            return s
        time.sleep(0.2)
    raise AssertionError("simulation did not finish")


def test_demo_data_only_affects_signed_in_astronaut(client, auth):
    ha, hb, hc = select(client, "vega"), select(client, "okafor"), select(client, "mori")
    client.post(f"{API}/simulator/reset", headers=auth("admin"))  # start from no generated data at all
    before_b, before_c = snapshot(B), snapshot(C)

    def overview_rows():
        rows = client.get(f"{API}/crew/overview", headers=hc).json()["crew"]
        return {c["astronaut"]["id"]: (c["last_measured_at"], c["current_status"], c["open_alerts"]["total"]) for c in rows}
    crew_before = overview_rows()

    # Astronaut A generates a scenario: only A receives new observations / assessments / alerts
    s = generate(client, ha, "illness")
    assert s["primary_astronaut_id"] == A and s["crew_scope"] == [A] and s["counts"]["rejected"] == 0
    assert sim_count(A) > 0
    assert snapshot(B) == before_b and snapshot(C) == before_c
    with db.session() as conn:
        rows = db.all_(conn, "SELECT DISTINCT astronaut_id, mission_id FROM observations WHERE sim_run_id=?", (s["run_id"],))
        assert {(r["astronaut_id"], r["mission_id"]) for r in rows} <= {(A, "MSN-ARES-T1"), (None, "MSN-ARES-T1")}
        for t in ("health_assessments", "alerts", "medical_events", "sleep_records", "mood_assessments", "exercise_records", "nutrition_records"):
            owners = {r["astronaut_id"] for r in db.all_(conn, f"SELECT DISTINCT astronaut_id FROM {t} WHERE sim_run_id=?", (s["run_id"],))}
            assert owners <= {A, None}, (t, owners)

    # Astronaut B: own records unchanged and A's demo records are not visible
    hist_b = client.get(f"{API}/measurements/history?limit=500", headers=hb).json()
    assert hist_b["items"] and all(o["astronaut_id"] == B and not o.get("sim_run_id") for o in hist_b["items"])
    assert client.get(f"{API}/measurements/history?astronaut_id={A}", headers=hb).status_code == 403

    # CMO: crew overview shows each member's own records
    crew_after = overview_rows()
    assert {A, B, C} <= set(crew_after)
    assert crew_after[B] == crew_before[B] and crew_after[C] == crew_before[C]  # B and C rows unchanged
    with db.session() as conn:
        last_a = db.one(conn, "SELECT MAX(measured_at) m FROM observations WHERE astronaut_id=? AND is_private=0", (A,))["m"]
    assert crew_after[A][0] == last_a  # A's row reflects A's own (new) records

    # Administrator: inspects A and B separately without mixing
    ad = auth("admin")
    ia = client.get(f"{API}/measurements/history?astronaut_id={A}&limit=500&order=desc", headers=ad).json()["items"]
    ib = client.get(f"{API}/measurements/history?astronaut_id={B}&limit=500&order=desc", headers=ad).json()["items"]
    assert ia and all(o["astronaut_id"] == A for o in ia) and any(o["is_synthetic"] and o.get("sim_run_id") for o in ia)
    assert ib and all(o["astronaut_id"] == B and not o.get("sim_run_id") for o in ib)

    # Repeating generation (replace) does not duplicate A's data nor touch B / C
    n1 = sim_count(A)
    generate(client, ha, "illness")
    assert sim_count(A) == n1
    # B generates their own data: A's generated records are kept, C untouched
    generate(client, hb, "nominal")
    assert sim_count(A) == n1 and sim_count(B) > 0 and snapshot(C) == before_c
    # B removing their demo data leaves A's
    client.post(f"{API}/simulator/reset", headers=hb)
    assert sim_count(B) == 0 and sim_count(A) == n1
    client.post(f"{API}/simulator/reset", headers=ha)
    assert sim_count(A) == 0 and snapshot(B) == before_b and snapshot(C) == before_c


def test_admin_whole_crew_is_explicit(client, auth):
    ad = auth("admin")
    client.post(f"{API}/simulator/reset", headers=ad)
    r = client.post(f"{API}/simulator/start", headers=ad, json={"scenario": "nominal", "days": 2, "speed": 96, "astronaut_id": B})
    assert r.status_code == 200 and r.json()["crew_scope"] == [B]
    client.post(f"{API}/simulator/stop", headers=ad)
    client.post(f"{API}/simulator/reset", headers=ad, params={"astronaut_id": B})
    assert sim_count(B) == 0
    r = client.post(f"{API}/simulator/start", headers=ad, json={"scenario": "nominal", "days": 2, "speed": 96, "whole_crew": True})
    assert r.status_code == 200 and r.json()["crew_scope"] == "all"
    client.post(f"{API}/simulator/stop", headers=ad)
    client.post(f"{API}/simulator/reset", headers=ad)
