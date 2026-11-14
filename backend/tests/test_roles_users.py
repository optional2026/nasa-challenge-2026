"""Profile-selection sign-in, administrator user management and the three-role permission model
(astronaut, Crew Medical Officer, Earth-based administrator). All enforcement is server-side."""
from datetime import timedelta

from astra import db

API = "/api/v1"


def t(m):
    return db.iso(db.utcnow() - timedelta(minutes=m))


def _select(client, user_id):
    return client.post(f"{API}/auth/select-profile", json={"user_id": user_id})


def _profile_id(client, username):
    crew = client.get(f"{API}/auth/profiles").json()["crew"]
    return next(p["user_id"] for p in crew if p["username"] == username)


def _bearer(r):
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------------------------------------------------------------- sign-in
def test_profiles_list_crew_and_earth_accounts(client):
    r = client.get(f"{API}/auth/profiles")
    assert r.status_code == 200
    body = r.json()
    crew = {p["username"]: p for p in body["crew"]}
    assert {"vega", "okafor", "mori"} <= set(crew)
    assert crew["mori"]["role"] == "medical_officer" and crew["vega"]["role"] == "astronaut"
    assert crew["vega"]["mission_name"] and crew["vega"]["crew"]
    assert {e["username"] for e in body["earth"]} >= {"admin"}
    assert "not suitable" in body["notice"]
    assert "password_hash" not in str(body)


def test_select_profile_without_password(client):
    h = _bearer(_select(client, _profile_id(client, "vega")))
    me = client.get(f"{API}/auth/me", headers=h).json()
    assert me["username"] == "vega" and me["role"] == "astronaut"


def test_earth_accounts_cannot_be_selected_without_password(client, auth):
    users = client.get(f"{API}/users", headers=auth("admin")).json()
    for u in users:
        if u["role"] in ("admin", "flight_surgeon"):
            assert _select(client, u["id"]).status_code == 403
    assert _select(client, 999999).status_code == 403
    # role comes from the server, never from the client
    assert client.post(f"{API}/auth/select-profile", json={"user_id": 1, "role": "admin"}).status_code == 422


# ---------------------------------------------------------------- user management
def test_only_admin_manages_users(client, auth):
    body = {"username": "intruder", "display_name": "X", "role": "astronaut", "name": "X"}
    for u in ("vega", "mori", "ramirez"):
        assert client.post(f"{API}/users", headers=auth(u), json=body).status_code == 403
        assert client.get(f"{API}/users", headers=auth(u)).status_code == 403
    vega_id = _profile_id(client, "vega")
    assert client.patch(f"{API}/users/{vega_id}", headers=auth("vega"), json={"role": "medical_officer"}).status_code == 403
    assert client.post(f"{API}/users", json=body).status_code == 401  # no self-registration
    # administrators cannot be created or assigned through user management
    assert client.post(f"{API}/users", headers=auth("admin"), json=body | {"role": "admin"}).status_code == 422
    assert client.patch(f"{API}/users/{vega_id}", headers=auth("admin"), json={"role": "admin"}).status_code == 422


def test_admin_registers_edits_and_deactivates(client, auth):
    a = auth("admin")
    r = client.post(f"{API}/users", headers=a, json={
        "username": "lindqvist", "display_name": "Sofia Lindqvist", "role": "astronaut", "name": "Sofia Lindqvist",
        "call_sign": "LIND", "crew_role": "Mission Specialist", "crew": "Relief Crew"})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["active"] and u["sign_in"] == "profile" and u["astronaut"]["crew"] == "Relief Crew"
    ast = u["astronaut"]["id"]
    assert client.post(f"{API}/users", headers=a, json={"username": "lindqvist", "display_name": "dup", "role": "astronaut",
                                                         "name": "dup"}).status_code == 409
    # new astronaut signs in by profile selection and sees only their own data
    h = _bearer(_select(client, u["id"]))
    assert client.get(f"{API}/overview", headers=h).status_code == 200
    assert client.get(f"{API}/routine", headers=h).json()["tasks"]  # standard schedule created
    assert client.get(f"{API}/overview?astronaut_id=AST-001", headers=h).status_code == 403
    # CMO of the Prime Crew cannot see an astronaut assigned to another crew ...
    m = auth("mori")
    assert client.get(f"{API}/overview?astronaut_id={ast}", headers=m).status_code == 403
    crew_ids = {c["astronaut"]["id"] for c in client.get(f"{API}/crew/overview", headers=m).json()["crew"]}
    assert {"AST-001", "AST-002", "AST-003"} <= crew_ids and ast not in crew_ids
    # ... nor record measurements for them
    r = client.post(f"{API}/measurements/manual", headers=m, json={
        "astronaut_id": ast, "measured_at": t(2), "source_type": "manual", "quality": "valid",
        "items": [{"metric_code": "heart_rate", "value": 60, "unit": "bpm"}]})
    assert r.status_code == 422 and "crew" in r.text
    # ... until the administrator assigns them to the Prime Crew
    r = client.patch(f"{API}/users/{u['id']}", headers=a, json={"crew": "Prime Crew", "display_name": "Dr. Sofia Lindqvist"})
    assert r.status_code == 200 and r.json()["display_name"] == "Dr. Sofia Lindqvist"
    assert client.get(f"{API}/overview?astronaut_id={ast}", headers=m).status_code == 200
    # role change invalidates existing sessions (claims must match the server record)
    assert client.patch(f"{API}/users/{u['id']}", headers=a, json={"role": "medical_officer"}).status_code == 200
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401
    assert client.patch(f"{API}/users/{u['id']}", headers=a, json={"role": "astronaut"}).status_code == 200
    h = _bearer(_select(client, u["id"]))
    # deactivation signs the account out everywhere and removes it from the sign-in screen
    assert client.post(f"{API}/users/{u['id']}/deactivate", headers=a).json()["active"] is False
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401
    assert _select(client, u["id"]).status_code == 403
    assert "lindqvist" not in {p["username"] for p in client.get(f"{API}/auth/profiles").json()["crew"]}
    listed = {x["username"]: x for x in client.get(f"{API}/users", headers=a).json()}
    assert listed["lindqvist"]["active"] is False
    me_id = client.get(f"{API}/auth/me", headers=a).json()["id"]
    assert client.post(f"{API}/users/{me_id}/deactivate", headers=a).status_code == 409
    assert client.post(f"{API}/users/{u['id']}/activate", headers=a).json()["active"] is True
    # restore: move back out of the Prime Crew and deactivate so later tests see the original crew
    client.patch(f"{API}/users/{u['id']}", headers=a, json={"crew": "Relief Crew"})
    client.post(f"{API}/users/{u['id']}/deactivate", headers=a)


# ---------------------------------------------------------------- roles
def test_crew_overview_roles(client, auth):
    assert client.get(f"{API}/crew/overview", headers=auth("vega")).status_code == 403
    r = client.get(f"{API}/crew/overview", headers=auth("mori"))
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "crew" and body["crew_name"] == "Prime Crew"
    row = body["crew"][0]
    assert {"current_status", "category", "open_alerts", "vitals", "routine", "last_update_at"} <= set(row)
    assert "mood" not in {v["metric_code"] for c in body["crew"] for v in c["vitals"]}
    s = body["summary"]
    assert s["total"] == len(body["crew"]) == s["no_concern"] + s["attention"] + s["medical_review"] + s["no_data"]
    for c in body["crew"]:  # missing data is never shown as healthy
        if not c["has_data"]:
            assert c["category"] == "no_data" and c["current_status"] == "INSUFFICIENT_DATA"
    # administrator: whole mission, read-only, privacy-filtered
    a = client.get(f"{API}/crew/overview", headers=auth("admin")).json()
    assert a["scope"] == "mission" and {"AST-001", "AST-002", "AST-003"} <= {c["astronaut"]["id"] for c in a["crew"]}
    assert all(c["open_alerts"]["private_redacted"] == 0 for c in a["crew"])


def test_cmo_has_astronaut_capabilities_for_self(client, auth):
    m = auth("mori")
    assert client.get(f"{API}/overview", headers=m).json()["astronaut"]["id"] == "AST-002"
    r = client.post(f"{API}/measurements/manual", headers=m, json={
        "measured_at": t(1), "source_type": "manual", "quality": "valid",
        "items": [{"metric_code": "heart_rate", "value": 61, "unit": "bpm"}]})
    assert r.status_code == 201, r.text
    assert client.get(f"{API}/routine", headers=m).status_code == 200


def test_demo_generator_limited_to_own_profile(client, auth):
    v, o = auth("vega"), auth("okafor")
    assert client.post(f"{API}/simulator/start", headers=v, json={"scenario": "nominal", "astronaut_id": "AST-003"}).status_code == 403
    assert client.post(f"{API}/simulator/start", headers=v, json={"scenario": "nominal", "whole_crew": True}).status_code == 403
    # the CMO, too, generates demo data only for their own profile
    assert client.post(f"{API}/simulator/start", headers=auth("mori"), json={"scenario": "nominal", "astronaut_id": "AST-001"}).status_code == 403
    r = client.post(f"{API}/simulator/start", headers=v, json={"scenario": "nominal", "days": 2, "speed": 1})
    assert r.status_code == 200, r.text
    assert r.json()["primary_astronaut_id"] == "AST-001" and r.json()["crew_scope"] == ["AST-001"]
    # another astronaut cannot stop, reset or speed up someone else's run
    assert client.post(f"{API}/simulator/stop", headers=o).status_code == 403
    assert client.post(f"{API}/simulator/reset", headers=o).status_code == 403
    assert client.post(f"{API}/simulator/stop", headers=v).status_code == 200
    # astronaut reset removes only their own generated health records
    okafor_before = client.get(f"{API}/measurements/history?astronaut_id=AST-003&limit=1", headers=o).json()["total"]
    r = client.post(f"{API}/simulator/reset", headers=v)
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/measurements/history?astronaut_id=AST-003&limit=1", headers=o).json()["total"] == okafor_before
    rows = client.get(f"{API}/audit?limit=50", headers=auth("admin")).json()
    reset = next(x for x in rows if x["action"] == "simulator.reset")
    assert reset["details"]["scope"] == ["AST-001"]
