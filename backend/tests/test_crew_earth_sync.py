"""Crew Side ↔ Earth Side synchronization — integration tests with TWO real server processes.

An onboard (Crew Side) server and an Earth Side server are started as separate processes with separate data
directories / SQLite databases and ports. Records travel between the two databases only through the signed
replication API. Nothing here touches the in-process standalone app used by the other test modules.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import requests

BACKEND = Path(__file__).resolve().parents[1]
CREW_PW, EARTH_PW = "optionalwillwin", "astra-demo"
SYNC_KEY = "test-sync-key-0123456789-abcdefghijklmnopqrstuvwxyz"
T = 20


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, side: str, root: Path, port: int, extra: dict | None = None, args: list[str] | None = None):
        self.side, self.port, self.data = side, port, root / side
        self.base = f"http://127.0.0.1:{port}/api/v1"
        self.extra, self.args = extra or {}, args or []
        self.proc = None
        self.log = root / f"{side}-{port}.log"

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ASTRA_")}
        env.update({"ASTRA_DATA_DIR": str(self.data), "ASTRA_SYNC_KEY": SYNC_KEY, "ASTRA_SYNC_INTERVAL": "0.5",
                    "ASTRA_FRONTEND_DIST": str(self.data / "no-dist"), "PYTHONUNBUFFERED": "1"})
        env.update(self.extra)
        return env

    def start(self):
        self.proc = subprocess.Popen([sys.executable, str(BACKEND / "run.py"), "--side", self.side, "--port", str(self.port),
                                      *self.args], cwd=str(BACKEND), env=self.env(),
                                     stdout=open(self.log, "ab"), stderr=subprocess.STDOUT)
        deadline = time.time() + 120
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.side} server exited: {self.log.read_text(errors='replace')[-2000:]}")
            try:
                if requests.get(self.base + "/health", timeout=2).ok:
                    return self
            except requests.RequestException:
                pass
            time.sleep(0.5)
        raise RuntimeError(f"{self.side} server did not start")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def login(self, user: str) -> dict | None:
        r = requests.post(self.base + "/auth/login", json={"username": user, "password": CREW_PW if user in ("vega", "okafor", "mori") else EARTH_PW}, timeout=T)
        return {"Authorization": "Bearer " + r.json()["token"]} if r.ok else None

    def get(self, path, h=None, **kw):
        return requests.get(self.base + path, headers=h, timeout=T, **kw)

    def post(self, path, h=None, json_body=None):
        return requests.post(self.base + path, headers=h, json=json_body if json_body is not None else {}, timeout=T)

    def db(self):
        c = sqlite3.connect(f"file:{self.data / 'astra.sqlite3'}?mode=ro", uri=True, timeout=30)
        c.row_factory = sqlite3.Row
        return c


@pytest.fixture(scope="module")
def sides():
    root = Path(tempfile.mkdtemp(prefix="astra-2side-"))
    ep, op = _free_port(), _free_port()
    earth = Server("earth", root, ep, {"ASTRA_SYNC_PEER_ID": "ONBOARD-TEST", "ASTRA_SYNC_PEER_MISSION": "MSN-ARES-T1",
                                       "ASTRA_NODE_ID": "EARTH-TEST"})
    onboard = Server("onboard", root, op, {"ASTRA_NODE_ID": "ONBOARD-TEST", "ASTRA_ALLOW_LINK_SIMULATION": "1",
                                           "ASTRA_EARTH_URL": f"http://127.0.0.1:{ep}"})
    earth.start()
    onboard.start()
    yield onboard, earth
    onboard.stop()
    earth.stop()


def wait_for(fn, timeout=40, step=0.5):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(step)
    return last


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def record_hr(onboard, h, value=62, astronaut_id=None):
    body = {"measured_at": now_iso(), "source_type": "manual", "quality": "unverified", "context": {"activity": "resting"},
            "items": [{"metric_code": "heart_rate", "value": value, "unit": "bpm"}], "client_submission_id": f"T-{time.time_ns()}"}
    if astronaut_id:
        body["astronaut_id"] = astronaut_id
    r = onboard.post("/measurements/manual", h, body)
    assert r.status_code == 201, r.text
    return r.json()["accepted"][0]["observation_id"], body["measured_at"]


def outbox_status(onboard, rtype, rid):
    with onboard.db() as c:
        r = c.execute("SELECT status FROM replication_outbox WHERE record_type=? AND record_id=?", (rtype, rid)).fetchone()
    return r["status"] if r else None


def set_outage(onboard, mori, on: bool):
    r = onboard.post("/link/simulation/" + ("outage" if on else "restore"), mori)
    assert r.status_code == 200, r.text
    assert r.json()["simulated_outage"] is on
    return r.json()


# ---------------------------------------------------------------------------------------------- tests
def test_each_side_accepts_only_its_own_accounts(sides):
    onboard, earth = sides
    assert onboard.login("vega") and onboard.login("mori")
    r = requests.post(onboard.base + "/auth/login", json={"username": "admin", "password": EARTH_PW}, timeout=T)
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_side"
    assert earth.login("admin") and earth.login("ramirez")
    r = requests.post(earth.base + "/auth/login", json={"username": "vega", "password": CREW_PW}, timeout=T)
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_side"
    cfg = onboard.get("/public-config").json()
    assert cfg["deployment"] == "onboard" and earth.get("/public-config").json()["deployment"] == "earth"


def test_outage_queue_restore_and_earth_visibility(sides):
    onboard, earth = sides
    vega, mori, admin, fs = onboard.login("vega"), onboard.login("mori"), earth.login("admin"), earth.login("ramirez")
    # CMO enables the simulated outage
    st = set_outage(onboard, mori, True)
    assert st["link_state"] == "unavailable_simulated"
    # astronaut records a measurement: saved onboard immediately ...
    oid, measured_at = record_hr(onboard, vega, 63)
    assert onboard.get(f"/measurements/{oid}", vega).status_code == 200
    # ... and the CMO sees it at once from another session
    r = onboard.get(f"/measurements/{oid}", mori)
    assert r.status_code == 200 and r.json()["replication"]["status"] == "PENDING"
    # Earth does not receive it during the outage; it stays PENDING onboard
    time.sleep(3)
    assert earth.get(f"/measurements/{oid}", admin).status_code == 404
    assert outbox_status(onboard, "observation", oid) == "PENDING"
    link = onboard.get("/link", mori).json()
    assert link["unsynced"] >= 1 and link["sync_state"] == "pending"
    unsynced = onboard.get("/replication/unsynced", mori).json()["items"]
    assert any(i["record_id"] == oid for i in unsynced)
    # restore: the queue drains automatically
    set_outage(onboard, mori, False)
    got = wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200)
    assert got, "record did not reach Earth after the connection was restored"
    assert wait_for(lambda: outbox_status(onboard, "observation", oid) == "SYNCED")
    o = earth.get(f"/measurements/{oid}", admin).json()
    # original measurement timestamp preserved; Earth arrival recorded separately
    assert o["measured_at"] == onboard.get(f"/measurements/{oid}", mori).json()["measured_at"]
    assert o["replication"]["origin_node"] == "ONBOARD-TEST" and o["replication"]["first_received_at"] >= o["measured_at"]
    # assigned ground flight surgeon sees it too
    assert earth.get(f"/measurements/{oid}", fs).status_code == 200
    link = wait_for(lambda: (lambda l: l if l["unsynced"] == 0 else None)(onboard.get("/link", mori).json()))
    assert link and link["sync_state"] == "complete" and link["last_success_at"]


def test_unassigned_flight_surgeon_cannot_see_synced_record(sides):
    onboard, earth = sides
    vega, admin = onboard.login("vega"), earth.login("admin")
    oid, _ = record_hr(onboard, vega, 60)
    assert wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200)
    # a second ground flight surgeon WITHOUT a mission assignment (provisioned directly; the admin API only creates crew accounts)
    with sqlite3.connect(earth.data / "astra.sqlite3", timeout=30) as c:
        c.execute("INSERT OR IGNORE INTO users(username, display_name, password_hash, role, astronaut_id, active, created_at, mission_id) "
                  "SELECT 'fs2', 'FS without mission', password_hash, 'flight_surgeon', NULL, 1, created_at, NULL FROM users WHERE username='ramirez'")
    r = requests.post(earth.base + "/auth/login", json={"username": "fs2", "password": EARTH_PW}, timeout=T)
    fs2 = {"Authorization": "Bearer " + r.json()["token"]}
    assert earth.get(f"/measurements/{oid}", fs2).status_code == 403


def test_simulation_control_requires_cmo(sides):
    onboard, earth = sides
    vega, okafor = onboard.login("vega"), onboard.login("okafor")
    for h in (vega, okafor):
        assert onboard.post("/link/simulation/outage", h).status_code == 403
        assert onboard.post("/link/simulation/restore", h).status_code == 403
    assert onboard.post("/link/simulation/outage", None).status_code == 401
    # not available on the Earth server for any role
    for u in ("admin", "ramirez"):
        assert earth.post("/link/simulation/outage", earth.login(u)).status_code in (403, 409)
    assert onboard.get("/link", onboard.login("mori")).json()["simulated_outage"] is False
    # simulation changes are audited
    with onboard.db() as c:
        acts = {r["action"] for r in c.execute("SELECT action FROM audit_log WHERE action LIKE 'link_simulation.%'")}
    assert {"link_simulation.enabled", "link_simulation.disabled"} <= acts


def test_onboard_fully_operational_without_earth(sides):
    onboard, earth = sides
    vega, okafor, mori = onboard.login("vega"), onboard.login("okafor"), onboard.login("mori")
    set_outage(onboard, mori, True)
    try:
        oid, _ = record_hr(onboard, okafor, 58)
        for path in ("/crew/overview", "/alerts?astronaut_id=AST-003", "/medical-events", "/assessments?astronaut_id=AST-003",
                     "/overview?astronaut_id=AST-003", "/routine?astronaut_id=AST-003", "/measurements/history?astronaut_id=AST-003"):
            assert onboard.get(path, mori).status_code == 200, path
        assert onboard.post("/assessments", mori, {"astronaut_id": "AST-003"}).status_code in (200, 201)
        assert onboard.post("/sleep", vega, {"sleep_start": "2026-11-14T22:00:00Z", "sleep_end": "2026-11-15T05:00:00Z",
                                             "quality": 4}).status_code == 201
        # a new session (e.g. after a page refresh) still sees the outage
        assert onboard.get("/link", onboard.login("mori")).json()["link_state"] == "unavailable_simulated"
        time.sleep(2)
        assert outbox_status(onboard, "observation", oid) == "PENDING"
    finally:
        set_outage(onboard, mori, False)
    assert wait_for(lambda: outbox_status(onboard, "observation", oid) == "SYNCED")


def test_outage_persists_across_onboard_restart(sides):
    onboard, earth = sides
    mori, vega, admin = onboard.login("mori"), onboard.login("vega"), earth.login("admin")
    set_outage(onboard, mori, True)
    oid, _ = record_hr(onboard, vega, 64)
    onboard.stop()
    onboard.start()
    mori = onboard.login("mori")
    assert onboard.get("/link", mori).json()["simulated_outage"] is True
    time.sleep(2)
    assert earth.get(f"/measurements/{oid}", admin).status_code == 404
    assert outbox_status(onboard, "observation", oid) == "PENDING"
    set_outage(onboard, mori, False)
    assert wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200)


def test_sync_runs_without_any_user_session(sides):
    onboard, earth = sides
    vega, admin = onboard.login("vega"), earth.login("admin")
    oid, _ = record_hr(onboard, vega, 59)
    # from here on nobody talks to the onboard server: the background service delivers on its own
    assert wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200)


def test_interrupted_transmission_does_not_lose_records(sides):
    onboard, earth = sides
    vega, mori = onboard.login("vega"), onboard.login("mori")
    earth.stop()  # real communication loss (Earth server down), no simulation
    try:
        oid, _ = record_hr(onboard, vega, 65)
        assert wait_for(lambda: outbox_status(onboard, "observation", oid) == "FAILED", timeout=20)
        link = onboard.get("/link", mori).json()
        assert link["link_state"] == "unreachable" and link["unsynced"] >= 1
        assert onboard.get(f"/measurements/{oid}", mori).status_code == 200  # still there onboard
    finally:
        earth.start()
    admin = earth.login("admin")
    assert wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200, timeout=90)
    assert wait_for(lambda: outbox_status(onboard, "observation", oid) == "SYNCED")
    with earth.db() as c:
        assert c.execute("SELECT COUNT(*) FROM observations WHERE id=?", (oid,)).fetchone()[0] == 1


# ---------------------------------------------------------------------------------------------- direct peer API
def _signed_post(earth, batch: dict, key=SYNC_KEY, node="ONBOARD-TEST"):
    body = json.dumps(batch, separators=(",", ":"), sort_keys=True).encode()
    path = "/api/v1/replication/batch"
    ts = str(int(time.time()))
    msg = b"\n".join([b"astra-replication/1", b"POST", path.encode(), ts.encode(), node.encode(),
                      hashlib.sha256(body).hexdigest().encode()])
    sig = hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()
    return requests.post(f"http://127.0.0.1:{earth.port}{path}", data=body, timeout=T, headers={
        "Content-Type": "application/json", "X-Astra-Protocol": "astra-replication/1", "X-Astra-Node": node,
        "X-Astra-Timestamp": ts, "X-Astra-Signature": sig})


def _envelope_from_earth(earth, oid):
    with earth.db() as c:
        row = dict(c.execute("SELECT * FROM observations WHERE id=?", (oid,)).fetchone())
        rev = c.execute("SELECT revision FROM replicated_records WHERE record_type='observation' AND record_id=?", (oid,)).fetchone()[0]
    h = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return {"record_type": "observation", "record_id": oid, "revision": rev, "payload_hash": h, "payload": row}


def _batch(records):
    return {"protocol": "astra-replication/1", "batch_id": f"TEST-{time.time_ns()}", "node_id": "ONBOARD-TEST",
            "mission_id": "MSN-ARES-T1", "sent_at": now_iso(), "records": records}


def test_repeated_transmission_is_idempotent_and_immutable(sides):
    onboard, earth = sides
    vega, admin = onboard.login("vega"), earth.login("admin")
    oid, _ = record_hr(onboard, vega, 61)
    assert wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200)
    env = _envelope_from_earth(earth, oid)
    for _ in range(3):
        r = _signed_post(earth, _batch([env]))
        assert r.status_code == 200, r.text
        assert r.json()["results"][0]["status"] == "duplicate"
    with earth.db() as c:
        assert c.execute("SELECT COUNT(*) FROM observations WHERE id=?", (oid,)).fetchone()[0] == 1
    # a different version of an immutable health observation is rejected, never overwritten
    tampered = json.loads(json.dumps(env))
    tampered["payload"]["value_num"] = 180.0
    tampered["revision"] += 1
    tampered["payload_hash"] = hashlib.sha256(json.dumps(tampered["payload"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    res = _signed_post(earth, _batch([tampered])).json()["results"][0]
    assert res["status"] == "rejected" and "immutable" in res["error"]
    assert earth.get(f"/measurements/{oid}", admin).json()["value"] == 61


def test_peer_authentication_and_scope(sides):
    onboard, earth = sides
    vega, admin = onboard.login("vega"), earth.login("admin")
    oid, _ = record_hr(onboard, vega, 57)
    assert wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200)
    env = _envelope_from_earth(earth, oid)
    assert _signed_post(earth, _batch([env]), key="wrong-key").status_code == 401
    assert _signed_post(earth, _batch([env]), node="SOMEONE-ELSE").status_code == 401
    # a user session token is not a peer credential
    r = requests.post(earth.base + "/replication/batch", headers=admin, json=_batch([env]), timeout=T)
    assert r.status_code == 401
    # records of an astronaut outside the spacecraft's mission / unknown astronaut are refused
    other = json.loads(json.dumps(env))
    other["record_id"] = other["payload"]["id"] = "OBS-FORGED-0001"
    other["payload"]["astronaut_id"] = "AST-999"
    other["payload_hash"] = hashlib.sha256(json.dumps(other["payload"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    res = _signed_post(earth, _batch([other])).json()["results"][0]
    assert res["status"] == "rejected"
    bad_mission = _batch([env])
    bad_mission["mission_id"] = "MSN-OTHER"
    assert _signed_post(earth, bad_mission).status_code == 400
    # integrity hash must match the payload
    broken = json.loads(json.dumps(env))
    broken["payload"]["notes"] = "changed in transit"
    assert _signed_post(earth, _batch([broken])).json()["results"][0]["status"] == "rejected"
    # the receiver does not exist on the onboard server
    assert _signed_post(onboard, _batch([env])).status_code == 404


def test_private_data_stays_private_on_both_sides(sides):
    onboard, earth = sides
    vega, okafor, admin, fs = onboard.login("vega"), onboard.login("okafor"), earth.login("admin"), earth.login("ramirez")
    oid, _ = record_hr(onboard, okafor, 56)
    assert onboard.get(f"/measurements/{oid}", vega).status_code == 403  # another astronaut's record
    r = onboard.post("/mood", okafor, {"assessed_at": now_iso(), "mood": 4, "stress": 2, "fatigue": 2,
                                       "private_note": "PRIVATE-TEST-NOTE"})
    assert r.status_code == 201, r.text
    mood_id = r.json()["record"]["id"]
    assert onboard.get("/mood?astronaut_id=AST-003", vega).status_code == 403
    assert wait_for(lambda: earth.get("/mood?astronaut_id=AST-003", fs).ok and
                    any(m["id"] == mood_id for m in earth.get("/mood?astronaut_id=AST-003", fs).json()))
    # the Earth administrator cannot read private check-ins even though they were synchronized
    r = earth.get("/mood?astronaut_id=AST-003", admin)
    assert r.status_code == 403 or "PRIVATE-TEST-NOTE" not in r.text


def test_earth_side_does_not_create_health_records(sides):
    onboard, earth = sides
    fs = earth.login("ramirez")
    r = earth.post("/measurements/manual", fs, {"astronaut_id": "AST-001", "measured_at": now_iso(), "source_type": "manual",
                                                "quality": "unverified", "items": [{"metric_code": "heart_rate", "value": 60, "unit": "bpm"}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "earth_side_read_only"
    assert earth.post("/simulator/start", fs, {"scenario": "nominal"}).status_code == 409


def test_ground_note_reaches_cmo(sides):
    onboard, earth = sides
    fs, mori = earth.login("ramirez"), onboard.login("mori")
    r = earth.post("/ground/annotations", fs, {"astronaut_id": "AST-001", "kind": "request", "text": "Please repeat BP tomorrow."})
    assert r.status_code == 201, r.text
    nid = r.json()["id"]
    assert earth.post("/ground/annotations", earth.login("admin"), {"astronaut_id": "AST-001", "text": "x"}).status_code == 403
    got = wait_for(lambda: any(n["id"] == nid for n in onboard.get("/ground/annotations", mori).json()["items"]))
    assert got
    # acknowledged by cursor on the following pass
    assert wait_for(lambda: next(n for n in earth.get("/ground/annotations", fs).json()["items"] if n["id"] == nid)["delivered_at"])


def test_workflow_state_updates_replicate(sides):
    """Alerts / medical events change state after creation; the newer onboard revision replaces the older one on
    Earth and parent/child ordering holds for a whole simulated scenario."""
    onboard, earth = sides
    vega, mori, admin = onboard.login("vega"), onboard.login("mori"), earth.login("admin")
    r = onboard.post("/simulator/start", vega, {"scenario": "emergency", "speed": 96, "days": 2})
    assert r.status_code == 200, r.text
    assert wait_for(lambda: onboard.get("/simulator", vega).json()["state"] not in ("running", "paused"), timeout=240, step=2)
    alerts = onboard.get("/alerts?astronaut_id=AST-001&status=open", mori).json()
    assert alerts, "scenario produced no alert"
    aid = alerts[0]["id"]
    assert onboard.post(f"/alerts/{aid}/acknowledge", mori, {"note": "seen by CMO"}).status_code == 200
    ok = wait_for(lambda: (lambda r: r.ok and r.json()["ack_status"] != "unacknowledged")(earth.get(f"/alerts/{aid}", admin)),
                  timeout=120, step=1)
    assert ok, "alert acknowledgement did not reach Earth"
    link = wait_for(lambda: (lambda l: l if l["unsynced"] == 0 else None)(onboard.get("/link", mori).json()), timeout=120, step=1)
    assert link and link["counts"]["REJECTED"] == 0
    assert len(earth.get("/alerts?astronaut_id=AST-001", admin).json()) == len(onboard.get("/alerts?astronaut_id=AST-001", mori).json())


def test_link_simulation_disabled_without_explicit_configuration():
    root = Path(tempfile.mkdtemp(prefix="astra-nosim-"))
    srv = Server("onboard", root, _free_port(), {"ASTRA_NODE_ID": "ONBOARD-NOSIM", "ASTRA_EARTH_URL": "http://127.0.0.1:9"}).start()
    try:
        mori = srv.login("mori")
        r = srv.post("/link/simulation/outage", mori)
        assert r.status_code == 403 and r.json()["error"]["code"] == "simulation_disabled"
        assert srv.get("/link", mori).json()["simulation_allowed"] is False
    finally:
        srv.stop()


def test_large_signed_batch_is_accepted(sides):
    """Replication batches can exceed the 512 KB limit that protects user endpoints."""
    onboard, earth = sides
    vega, admin = onboard.login("vega"), earth.login("admin")
    oid, _ = record_hr(onboard, vega, 62)
    assert wait_for(lambda: earth.get(f"/measurements/{oid}", admin).status_code == 200)
    env = _envelope_from_earth(earth, oid)
    batch = _batch([env] * 700)
    assert len(json.dumps(batch)) > 600 * 1024
    r = _signed_post(earth, batch)
    assert r.status_code == 200, r.text[:200]
    assert {x["status"] for x in r.json()["results"]} == {"duplicate"}
    # user endpoints keep the small limit
    big = requests.post(earth.base + "/auth/login", data=b"x" * (600 * 1024), timeout=T,
                        headers={"Content-Type": "application/json"})
    assert big.status_code == 413
