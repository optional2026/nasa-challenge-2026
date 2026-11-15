"""Password sign-in for every role, secure password storage, and the crew / Earth role separation
(astronaut, Crew Medical Officer, administrator, ground flight surgeon). All checks hit the real API."""
from datetime import timedelta

from conftest import CREW_PASSWORD, PASSWORD

from astra import db, security

API = "/api/v1"
NEW_PW = "Orbit-check-77"


def t(m):
    return db.iso(db.utcnow() - timedelta(minutes=m))


def login(client, username, password):
    return client.post(f"{API}/auth/login", json={"username": username, "password": password})


def bearer(r):
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def user_id(client, auth, username):
    return next(u["id"] for u in client.get(f"{API}/users", headers=auth("admin")).json() if u["username"] == username)


# ---------------------------------------------------------------- password sign-in
def test_login_for_all_roles(client):
    expected = {"vega": "astronaut", "okafor": "astronaut", "mori": "medical_officer",
                "ramirez": "flight_surgeon", "admin": "admin"}
    for username, role in expected.items():
        pw = CREW_PASSWORD if role in ("astronaut", "medical_officer") else PASSWORD
        r = login(client, username, pw)
        assert r.status_code == 200, (username, r.text)
        assert r.json()["user"]["role"] == role
        me = client.get(f"{API}/auth/me", headers=bearer(r)).json()
        assert me["username"] == username and me["role"] == role


def test_three_precreated_crew_accounts_use_shared_demo_password(client):
    for username in ("vega", "okafor", "mori"):
        assert login(client, username, "optionalwillwin").status_code == 200
        # the previous Earth demo password and wrong passwords no longer work for crew accounts
        for wrong in ("astra-demo", "", "OptionalWillWin", "optionalwillwin "):
            r = login(client, username, wrong)
            assert r.status_code in (401, 422), (username, wrong)
        assert login(client, username, "nope").json()["error"]["code"] == "invalid_credentials"
    # unknown user and wrong password are indistinguishable
    assert login(client, "nobody", "optionalwillwin").json() == login(client, "vega", "wrong-password").json()


def test_passwordless_profile_selection_removed(client):
    assert client.get(f"{API}/auth/profiles").status_code == 404
    assert client.post(f"{API}/auth/select-profile", json={"user_id": 1}).status_code == 404


def test_passwords_are_hashed_never_plaintext(client):
    with db.session() as conn:
        rows = {r["username"]: r["password_hash"] for r in db.all_(conn, "SELECT username, password_hash FROM users")}
        dupes = db.one(conn, "SELECT COUNT(*) c FROM users WHERE username IN ('vega','okafor','mori')")["c"]
    assert dupes == 3  # migration/seed updated rows in place, no duplicate accounts
    for username in ("vega", "okafor", "mori"):
        h = rows[username]
        assert h.startswith("scrypt$") and "optionalwillwin" not in h
        assert security.verify_password("optionalwillwin", h)
        assert not security.verify_password("astra-demo", h)
    # per-user random salt: the same password gives different hashes
    assert len({rows["vega"], rows["okafor"], rows["mori"]}) == 3


def test_password_and_hash_never_returned(client, auth):
    r = login(client, "vega", CREW_PASSWORD)
    for body in (r.text, client.get(f"{API}/auth/me", headers=bearer(r)).text,
                 client.get(f"{API}/users", headers=auth("admin")).text,
                 client.get("/api/v1/public-config").text, client.get("/api/openapi.json").text):
        assert "scrypt$" not in body and "password_hash" not in body
        assert "optionalwillwin" not in body and "astra-demo" not in body


def test_role_cannot_be_chosen_by_client(client, auth):
    assert client.post(f"{API}/auth/login", json={"username": "vega", "password": CREW_PASSWORD, "role": "admin"}).status_code == 422
    v = auth("vega")
    vid = user_id(client, auth, "vega")
    assert client.patch(f"{API}/users/{vid}", headers=v, json={"role": "medical_officer"}).status_code == 403
    assert client.post(f"{API}/users/{vid}/password", headers=v, json={"password": NEW_PW}).status_code == 403
    assert client.post(f"{API}/users", json={"username": "selfreg", "display_name": "x", "role": "astronaut", "name": "x",
                                             "password": NEW_PW}).status_code == 401


# ---------------------------------------------------------------- account creation and reset
def test_admin_creates_astronaut_with_validated_password(client, auth):
    a = auth("admin")
    base = {"username": "haddad", "display_name": "Omar Haddad", "role": "astronaut", "name": "Omar Haddad", "crew": "Backup Crew"}
    assert client.post(f"{API}/users", headers=a, json=base).status_code == 422  # password is required
    for weak in ("short", "aaaaaaaaaa", "password", "haddad", "  padded-pass  "):
        r = client.post(f"{API}/users", headers=a, json=base | {"password": weak})
        assert r.status_code == 422, weak
    r = client.post(f"{API}/users", headers=a, json=base | {"password": NEW_PW})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["sign_in"] == "password" and not ({"password", "password_hash"} & set(u))
    assert "scrypt$" not in r.text and NEW_PW not in r.text
    with db.session() as conn:
        h = db.one(conn, "SELECT password_hash FROM users WHERE username='haddad'")["password_hash"]
    assert h.startswith("scrypt$") and NEW_PW not in h
    h_new = bearer(login(client, "haddad", NEW_PW))
    assert client.get(f"{API}/overview", headers=h_new).json()["astronaut"]["id"] == u["astronaut"]["id"]
    assert login(client, "haddad", "wrong-password").status_code == 401

    # administrator reset: replaces the hash, old password stops working, nothing is disclosed
    r = client.post(f"{API}/users/{u['id']}/password", headers=a, json={"password": "Second-orbit-88"})
    assert r.status_code == 200 and "Second-orbit-88" not in r.text and "scrypt$" not in r.text
    assert login(client, "haddad", NEW_PW).status_code == 401
    assert login(client, "haddad", "Second-orbit-88").status_code == 200
    assert client.post(f"{API}/users/{u['id']}/password", headers=a, json={"password": "short"}).status_code == 422
    # Earth-side passwords are not managed here; non-admins cannot reset
    for earth in ("admin", "ramirez"):
        assert client.post(f"{API}/users/{user_id(client, auth, earth)}/password", headers=a,
                           json={"password": NEW_PW}).status_code == 403
    for other in ("ramirez", "mori"):
        assert client.post(f"{API}/users/{u['id']}/password", headers=auth(other), json={"password": NEW_PW}).status_code == 403
    rows = client.get(f"{API}/audit?limit=20", headers=a).json()
    assert any(x["action"] == "user.password_reset" for x in rows)
    assert all("Second-orbit-88" not in str(x["details"]) for x in rows)
    client.post(f"{API}/users/{u['id']}/deactivate", headers=a)


# ---------------------------------------------------------------- astronaut / CMO access
def test_astronaut_only_own_records(client, auth):
    v = auth("vega")
    assert client.get(f"{API}/overview", headers=v).json()["astronaut"]["id"] == "AST-001"
    for path in ("/overview", "/sleep", "/exercise", "/nutrition", "/mood", "/routine", "/measurements/latest", "/body-systems/cardiovascular"):
        assert client.get(f"{API}{path}?astronaut_id=AST-003", headers=v).status_code == 403, path
        assert client.get(f"{API}{path}?astronaut_id=AST-001", headers=v).status_code == 200, path
    assert client.get(f"{API}/crew/overview", headers=v).status_code == 403
    r = client.post(f"{API}/sleep", headers=v, json={"astronaut_id": "AST-003", "sleep_start": t(600), "sleep_end": t(130)})
    assert r.status_code == 403


def test_cmo_personal_and_crew_access(client, auth):
    m = auth("mori")
    # personal health recording on their own record
    r = client.post(f"{API}/sleep", headers=m, json={"sleep_start": t(620), "sleep_end": t(140)})
    assert r.status_code == 201, r.text
    assert client.get(f"{API}/mood?astronaut_id=AST-002", headers=m).status_code == 200
    # crew-wide oversight
    crew = {c["astronaut"]["id"] for c in client.get(f"{API}/crew/overview", headers=m).json()["crew"]}
    assert {"AST-001", "AST-002", "AST-003"} <= crew
    assert client.get(f"{API}/overview?astronaut_id=AST-003", headers=m).status_code == 200
    # ... but not other crew members' private check-ins
    assert client.get(f"{API}/mood?astronaut_id=AST-003", headers=m).status_code == 403


# ---------------------------------------------------------------- Earth-based roles
def test_admin_has_no_personal_health_recording(client, auth):
    a = auth("admin")
    me = client.get(f"{API}/auth/me", headers=a).json()
    assert me["astronaut_id"] is None
    # no implicit "own" record for astronaut-only endpoints
    assert client.get(f"{API}/overview", headers=a).status_code == 400
    for path, body in (("/measurements/manual", {"measured_at": t(1), "items": [{"metric_code": "heart_rate", "value": 60, "unit": "bpm"}]}),
                       ("/sleep", {"sleep_start": t(600), "sleep_end": t(120)}),
                       ("/mood", {"mood": 3}),
                       ("/exercise", {"exercise_type": "Run", "category": "aerobic", "start_at": t(60), "completion_status": "completed"}),
                       ("/nutrition", {"recorded_at": t(10), "record_type": "water", "water_ml": 200})):
        assert client.post(f"{API}{path}", headers=a, json=body).status_code in (403, 422), path
    r = client.post(f"{API}/telemetry", headers=a, json={"observations": [{
        "astronaut_id": "AST-001", "mission_id": "MSN-ARES-T1", "metric_code": "heart_rate", "value": 60, "unit": "bpm",
        "measured_at": t(1), "source_type": "manual", "quality": "valid"}]})
    assert r.json().get("accepted", []) == []


def test_ground_personnel_inspect_individual_astronaut_records(client, auth):
    for who in ("admin", "ramirez"):
        h = auth(who)
        for path in ("/overview?astronaut_id=AST-003", "/body-systems/cardiovascular?astronaut_id=AST-003",
                     "/measurements/history?astronaut_id=AST-003", "/measurements/latest?astronaut_id=AST-003",
                     "/trends?astronaut_id=AST-003&metric_code=heart_rate", "/assessments?astronaut_id=AST-003",
                     "/sleep?astronaut_id=AST-003", "/exercise?astronaut_id=AST-003", "/nutrition?astronaut_id=AST-003",
                     "/routine?astronaut_id=AST-003", "/alerts?astronaut_id=AST-003", "/medical-events?astronaut_id=AST-003",
                     "/astronauts/AST-003", "/crew/overview"):
            assert client.get(API + path, headers=h).status_code == 200, (who, path)
    # medical vs administrative: only the flight surgeon sees private behavioral-health content
    assert client.get(f"{API}/mood?astronaut_id=AST-003", headers=auth("ramirez")).status_code == 200
    assert client.get(f"{API}/mood?astronaut_id=AST-003", headers=auth("admin")).status_code == 403
    # only the administrator manages users
    assert client.get(f"{API}/users", headers=auth("ramirez")).status_code == 403


def test_flight_surgeon_limited_to_assigned_mission(client, auth):
    """A second mission is inserted directly: the flight surgeon (assigned to MSN-ARES-T1) cannot see its crew;
    the unassigned administrator can; reassigning the flight surgeon moves their access."""
    now = db.now_iso()
    with db.session() as conn, db.transaction(conn):
        db.insert(conn, "missions", {"id": "MSN-LUNA-X", "name": "Luna-X (test)", "mission_type": "lunar_surface",
                                     "start_utc": now, "comm_delay_seconds": 1.3, "earth_link_status": "online", "is_synthetic": 1})
        db.insert(conn, "astronauts", {"id": "AST-901", "mission_id": "MSN-LUNA-X", "name": "Test Lunar", "crew_role": "Pilot",
                                       "is_synthetic": 1, "created_at": now, "crew": "Luna Crew"})
    try:
        fs, a = auth("ramirez"), auth("admin")
        assert client.get(f"{API}/overview?astronaut_id=AST-901", headers=fs).status_code == 403
        assert client.get(f"{API}/measurements/history?astronaut_id=AST-901", headers=fs).status_code == 403
        assert client.get(f"{API}/mood?astronaut_id=AST-901", headers=fs).status_code == 403
        r = client.post(f"{API}/measurements/manual", headers=fs, json={"astronaut_id": "AST-901", "measured_at": t(1),
                        "source_type": "clinician", "items": [{"metric_code": "heart_rate", "value": 60, "unit": "bpm"}]})
        assert r.status_code == 422 and "assigned mission" in r.text
        assert "AST-901" not in {c["astronaut"]["id"] for c in client.get(f"{API}/crew/overview", headers=fs).json()["crew"]}
        assert client.get(f"{API}/overview?astronaut_id=AST-901", headers=a).status_code == 200
        # the CMO of the Prime Crew cannot access an unrelated mission's crew either
        assert client.get(f"{API}/overview?astronaut_id=AST-901", headers=auth("mori")).status_code == 403
        # reassignment (administrator only) moves the flight surgeon's access
        fs_id = user_id(client, auth, "ramirez")
        assert client.patch(f"{API}/users/{fs_id}", headers=fs, json={"mission_id": "MSN-LUNA-X"}).status_code == 403
        r = client.patch(f"{API}/users/{fs_id}", headers=a, json={"mission_id": "MSN-LUNA-X"})
        assert r.status_code == 200 and r.json()["assigned_mission_id"] == "MSN-LUNA-X"
        assert client.patch(f"{API}/users/{fs_id}", headers=a, json={"role": "astronaut"}).status_code == 403
        assert client.get(f"{API}/overview?astronaut_id=AST-901", headers=fs).status_code == 200
        assert client.get(f"{API}/overview?astronaut_id=AST-001", headers=fs).status_code == 403
    finally:
        client.patch(f"{API}/users/{user_id(client, auth, 'ramirez')}", headers=auth("admin"), json={"mission_id": "MSN-ARES-T1"})
        with db.session() as conn, db.transaction(conn):
            conn.execute("DELETE FROM astronauts WHERE id='AST-901'")
            conn.execute("DELETE FROM missions WHERE id='MSN-LUNA-X'")
    assert client.get(f"{API}/overview?astronaut_id=AST-001", headers=auth("ramirez")).status_code == 200


def test_unauthenticated_requests_rejected(client):
    for path in ("/overview?astronaut_id=AST-001", "/users", "/crew/overview", "/mood?astronaut_id=AST-001",
                 "/measurements/history?astronaut_id=AST-001", "/auth/me"):
        assert client.get(API + path).status_code == 401, path
    assert client.get(API + "/overview?astronaut_id=AST-001", headers={"Authorization": "Bearer forged.token.value"}).status_code == 401


def test_existing_database_migrated_once_without_duplicates(client, auth):
    """Simulates a database created before password sign-in: crew accounts on the old password, no flight-surgeon
    mission assignment, migration not yet recorded. The migration updates rows in place exactly once."""
    from astra import seed
    with db.session() as conn, db.transaction(conn):
        for u in ("vega", "okafor", "mori"):
            conn.execute("UPDATE users SET password_hash=? WHERE username=?", (security.hash_password("astra-demo"), u))
        conn.execute("UPDATE users SET mission_id=NULL WHERE username='ramirez'")
        conn.execute("DELETE FROM schema_meta WHERE key=?", (seed.CREW_PASSWORD_MIGRATION,))
        before = db.one(conn, "SELECT COUNT(*) c FROM users")["c"]
    with db.session() as conn:
        seed.apply_demo_password(conn)
        assert db.one(conn, "SELECT COUNT(*) c FROM users")["c"] == before
        assert db.one(conn, "SELECT mission_id FROM users WHERE username='ramirez'")["mission_id"] == "MSN-ARES-T1"
    for u in ("vega", "okafor", "mori"):
        assert login(client, u, "optionalwillwin").status_code == 200
        assert login(client, u, "astra-demo").status_code == 401
    # later startups never overwrite crew passwords again (administrator resets stay in effect)
    with db.session() as conn, db.transaction(conn):
        conn.execute("UPDATE users SET password_hash=? WHERE username='okafor'", (security.hash_password(NEW_PW),))
    with db.session() as conn:
        seed.apply_demo_password(conn)
    assert login(client, "okafor", NEW_PW).status_code == 200
    with db.session() as conn, db.transaction(conn):
        conn.execute("UPDATE users SET password_hash=? WHERE username='okafor'", (security.hash_password(CREW_PASSWORD),))
