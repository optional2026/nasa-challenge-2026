"""ASTRA mission simulator (synthetic data source).

The simulator generates coherent scenario time series (see scenarios.py) and
delivers them through ASTRA's public entry points:

* device data  → POST /api/v1/telemetry with each simulated device's X-Device-Key
* crew records → POST /api/v1/sleep | /mood | /exercise | /nutrition as the astronaut

Two transports implement the same interface:

* HttpTransport      — real HTTP calls to a running server (CLI mode, below)
* InProcessTransport — used when the simulator is controlled from the ASTRA UI;
  it calls the *same handler functions* the HTTP routes call
  (`ingestion.handle_telemetry` after device-key authentication,
  `records.create_*` with the astronaut principal), so validation, storage,
  assessment and alerting are identical.

Every record is labelled SYNTHETIC.

CLI:  python -m simulator.source --url http://127.0.0.1:8000 --scenario emergency --speed 24
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import timedelta
from typing import Any

from astra import db
from astra.bus import BUS
from astra.seed import ASTRONAUTS, DEMO_PASSWORD, USERS, device_keys_path

from .scenarios import SCENARIOS, Emission, ScenarioBuilder

RECORD_PATHS = {"sleep": "/api/v1/sleep", "mood": "/api/v1/mood", "exercise": "/api/v1/exercise", "nutrition": "/api/v1/nutrition"}


class InProcessTransport:
    name = "in-process (same handler functions as the HTTP API)"

    def __init__(self):
        self.keys = json.loads(device_keys_path().read_text())

    def telemetry(self, device_id: str, observations: list[dict], run_id: str) -> dict:
        from astra.services import ingestion
        with db.session() as conn:
            principal = ingestion.device_principal(conn, self.keys[device_id])
            return ingestion.handle_telemetry(conn, principal, {"observations": observations}, sim_run_id=run_id)

    def record(self, kind: str, astronaut_id: str, body: dict, run_id: str) -> dict:
        from astra import schemas
        from astra.security import Principal
        from astra.services import records
        model = {"sleep": schemas.SleepIn, "mood": schemas.MoodIn, "exercise": schemas.ExerciseIn,
                 "nutrition": schemas.NutritionIn}[kind].model_validate(body)
        fn = {"sleep": records.create_sleep, "mood": records.create_mood, "exercise": records.create_exercise,
              "nutrition": records.create_nutrition}[kind]
        p = Principal(kind="user", name=f"simulated-crew:{astronaut_id}", role="astronaut", astronaut_id=astronaut_id)
        with db.session() as conn:
            return fn(conn, p, model, sim_run_id=run_id)

    def daily_assessment(self, astronaut_id: str, anchor: str, run_id: str) -> dict:
        from astra.services import assessment_engine
        with db.session() as conn:
            return assessment_engine.full_assessment(conn, astronaut_id, trigger="simulator_daily", sim_run_id=run_id, anchor=anchor)


class HttpTransport:
    name = "HTTP"

    def __init__(self, base_url: str, keys_file: str | None = None):
        import requests  # optional dependency for CLI use
        self.requests = requests
        self.base = base_url.rstrip("/")
        self.keys = json.loads(open(keys_file).read() if keys_file else device_keys_path().read_text())
        self.tokens: dict[str, str] = {}
        for username, _, role, ast in USERS:
            if role == "astronaut" or (ast and role == "medical_officer"):
                r = requests.post(self.base + "/api/v1/auth/login", json={"username": username, "password": DEMO_PASSWORD}, timeout=30)
                r.raise_for_status()
                self.tokens[ast] = r.json()["token"]

    def telemetry(self, device_id, observations, run_id):
        r = self.requests.post(self.base + "/api/v1/telemetry", json={"observations": observations},
                               headers={"X-Device-Key": self.keys[device_id], "X-Simulator-Run": run_id}, timeout=60)
        return r.json()

    def record(self, kind, astronaut_id, body, run_id):
        r = self.requests.post(self.base + RECORD_PATHS[kind], json=body,
                               headers={"Authorization": f"Bearer {self.tokens[astronaut_id]}"}, timeout=60)
        return r.json()

    def daily_assessment(self, astronaut_id, anchor, run_id):
        r = self.requests.post(self.base + "/api/v1/assessments", json={"astronaut_id": astronaut_id},
                               headers={"Authorization": f"Bearer {self.tokens[astronaut_id]}"}, timeout=60)
        return r.json()


class SimulatorRunner:
    TICK_S = 0.25

    def __init__(self, transport=None):
        self.transport = transport
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        self.state = "idle"
        self.scenario = None
        self.speed = 6.0
        self.days = 10
        self.run_id = None
        self.emissions: list[Emission] = []
        self.idx = 0
        self.sim_start = self.sim_end = self.sim_clock = None
        self.launch = None
        self.counts = {"telemetry_batches": 0, "observations": 0, "records": 0, "rejected": 0, "alerts": 0}
        self.last_error = None
        self.started_at = None
        self._stop = threading.Event()
        self._pause = threading.Event()

    # ------------------------------------------------------------ control
    def start(self, scenario: str, speed: float = 6.0, days: int = 10, seed: int = 42) -> dict:
        with self.lock:
            if self.state in ("running", "paused"):
                raise RuntimeError("simulation already running; stop it first")
            if scenario not in SCENARIOS:
                raise ValueError(f"unknown scenario '{scenario}'")
            self.transport = self.transport or InProcessTransport()
            with db.session() as conn:
                m = db.one(conn, "SELECT start_utc FROM missions ORDER BY start_utc DESC LIMIT 1")
            self.launch = db.parse_iso(m["start_utc"])
            self.sim_end = db.utcnow().replace(second=0, microsecond=0)
            self.sim_end -= timedelta(minutes=self.sim_end.minute % 15)
            self.sim_start = self.sim_end - timedelta(days=days)
            self.sim_clock = self.sim_start
            self.run_id = db.new_id("SIMRUN")
            self.scenario, self.speed, self.days = scenario, float(speed), days
            self.emissions = ScenarioBuilder(scenario, self.sim_start, days, seed, self.launch, self.run_id).build()
            self.idx = 0
            self.counts = {k: 0 for k in self.counts}
            self.last_error = None
            self.started_at = db.now_iso()
            self._stop.clear()
            self._pause.clear()
            self.state = "running"
            self.thread = threading.Thread(target=self._loop, daemon=True, name="astra-simulator")
            self.thread.start()
        self._publish()
        return self.status()

    def pause(self):
        with self.lock:
            if self.state != "running":
                raise RuntimeError("simulation is not running")
            self._pause.set()
            self.state = "paused"
        self._publish()
        return self.status()

    def resume(self):
        with self.lock:
            if self.state != "paused":
                raise RuntimeError("simulation is not paused")
            self._pause.clear()
            self.state = "running"
        self._publish()
        return self.status()

    def stop(self):
        with self.lock:
            if self.state not in ("running", "paused"):
                return self.status()
            self._stop.set()
            self._pause.clear()
        if self.thread:
            self.thread.join(timeout=30)
        with self.lock:
            self.state = "stopped"
        self._devices_disconnected()
        self._publish()
        return self.status()

    def set_speed(self, speed: float):
        with self.lock:
            self.speed = float(speed)
        self._publish()
        return self.status()

    def reset(self, actor) -> dict:
        self.stop()
        from astra import audit
        with db.session() as conn:
            with db.transaction(conn):
                runs = [r["sim_run_id"] for r in db.all_(conn, "SELECT DISTINCT sim_run_id FROM observations WHERE sim_run_id IS NOT NULL")]
                deleted = {}
                rep_ids = [r["id"] for r in db.all_(conn, "SELECT id FROM medical_reports WHERE sim_run_id IS NOT NULL")]
                if rep_ids:
                    q = ",".join("?" * len(rep_ids))
                    conn.execute(f"DELETE FROM sync_queue WHERE item_id IN ({q})", rep_ids)
                    conn.execute(f"DELETE FROM ground_inbox WHERE item_id IN ({q})", rep_ids)
                # detach non-simulated rows that were later updated with simulated evidence
                conn.execute("UPDATE alerts SET assessment_id=NULL WHERE sim_run_id IS NULL AND assessment_id IN "
                             "(SELECT id FROM health_assessments WHERE sim_run_id IS NOT NULL)")
                conn.execute("UPDATE alerts SET medical_event_id=NULL WHERE sim_run_id IS NULL AND medical_event_id IN "
                             "(SELECT id FROM medical_events WHERE sim_run_id IS NOT NULL)")
                conn.execute("UPDATE environment_events SET alert_id=NULL WHERE alert_id IN (SELECT id FROM alerts WHERE sim_run_id IS NOT NULL)")
                for table in ("medical_reports", "environment_events", "alerts", "medical_events", "health_assessments",
                              "sleep_records", "mood_assessments", "exercise_records", "nutrition_records"):
                    if table == "alerts":
                        conn.execute("DELETE FROM alert_observations WHERE alert_id IN (SELECT id FROM alerts WHERE sim_run_id IS NOT NULL)")
                    cur = conn.execute(f"DELETE FROM {table} WHERE sim_run_id IS NOT NULL")
                    deleted[table] = cur.rowcount
                # observations referenced by environment events / assessments were removed with cascades above
                cur = conn.execute("DELETE FROM observations WHERE sim_run_id IS NOT NULL")
                deleted["observations"] = cur.rowcount
                conn.execute("DELETE FROM telemetry_batches")
                audit.record(conn, actor, "simulator.reset", "simulator", None, {"runs": runs, "deleted": deleted})
        with self.lock:
            self.state = "idle"
            self.scenario = None
            self.run_id = None
            self.emissions = []
            self.idx = 0
            self.sim_clock = None
        BUS.publish("simulator.reset", {"deleted": deleted})
        self._publish()
        return {"status": self.status(), "deleted": deleted}

    # ------------------------------------------------------------ loop
    def _loop(self):
        try:
            while not self._stop.is_set():
                if self._pause.is_set():
                    time.sleep(0.1)
                    continue
                t0 = time.monotonic()
                with self.lock:
                    self.sim_clock = min(self.sim_end, self.sim_clock + timedelta(hours=self.speed * self.TICK_S))
                    clock = self.sim_clock
                batch = []
                while self.idx < len(self.emissions) and self.emissions[self.idx].t <= clock:
                    batch.append(self.emissions[self.idx])
                    self.idx += 1
                self._deliver(batch)
                if self.idx >= len(self.emissions) and clock >= self.sim_end:
                    with self.lock:
                        self.state = "completed"
                    self._publish()
                    return
                self._publish(throttle=True)
                time.sleep(max(0.0, self.TICK_S - (time.monotonic() - t0)))
        except Exception as exc:  # surface errors in status
            with self.lock:
                self.state = "error"
                self.last_error = repr(exc)
            self._publish()
            raise

    def _deliver(self, batch: list[Emission]):
        """Deliver in chronological order. Telemetry is grouped per device within 30-minute
        simulated slots (one API call per device per slot) so cause precedes effect."""
        buffer: dict[str, list[dict]] = {}
        slot = None

        def flush():
            for dev, obs in buffer.items():
                res = self.transport.telemetry(dev, obs, self.run_id)
                self.counts["telemetry_batches"] += 1
                self.counts["observations"] += len(res.get("accepted", []))
                self.counts["rejected"] += len(res.get("rejected", []))
                self.counts["alerts"] += len(res.get("alerts_created", []))
                if res.get("rejected"):
                    self.last_error = f"rejected: {res['rejected'][:1]}"
            buffer.clear()

        for e in batch:
            s = e.t.replace(minute=(e.t.minute // 30) * 30, second=0, microsecond=0)
            if slot is not None and s != slot:
                flush()
            slot = s
            if e.kind == "telemetry":
                buffer.setdefault(e.device_id, []).extend(e.payload["observations"])
                continue
            flush()
            if e.kind in RECORD_PATHS:
                res = self.transport.record(e.kind, e.astronaut_id, e.payload, self.run_id)
                self.counts["records"] += 1
                ing = (res or {}).get("ingestion") or {}
                self.counts["observations"] += len(ing.get("accepted", []))
                self.counts["alerts"] += len(ing.get("alerts_created", []))
            elif e.kind == "daily_assessment":
                self.transport.daily_assessment(e.astronaut_id, db.iso(e.t), self.run_id)
        flush()

    # ------------------------------------------------------------ status
    def _devices_disconnected(self):
        with db.session() as conn:
            conn.execute("UPDATE devices SET status='disconnected' WHERE is_simulated=1")
        BUS.publish("device.status", {"device_id": "*", "status": "disconnected"})

    _last_pub = 0.0

    def _publish(self, throttle=False):
        now = time.monotonic()
        if throttle and now - self._last_pub < 1.0:
            return
        self._last_pub = now
        BUS.publish("simulator.status", self.status())

    def status(self) -> dict:
        with self.lock:
            met = None
            if self.sim_clock and self.launch:
                secs = (self.sim_clock - self.launch).total_seconds()
                met = {"days": int(secs // 86400), "hours": int(secs % 86400 // 3600), "minutes": int(secs % 3600 // 60),
                       "mission_day": int(secs // 86400) + 1}
            total = len(self.emissions) or 1
            return {"state": self.state, "scenario": self.scenario,
                    "scenario_description": SCENARIOS.get(self.scenario) if self.scenario else None,
                    "speed_sim_hours_per_second": self.speed, "days": self.days, "run_id": self.run_id,
                    "sim_clock": db.iso(self.sim_clock) if self.sim_clock else None,
                    "sim_start": db.iso(self.sim_start) if self.sim_start else None,
                    "sim_end": db.iso(self.sim_end) if self.sim_end else None,
                    "mission_elapsed": met, "progress": round(self.idx / total, 3) if self.emissions else 0.0,
                    "counts": dict(self.counts), "last_error": self.last_error, "started_at": self.started_at,
                    "transport": getattr(self.transport, "name", None), "label": "SYNTHETIC",
                    "scenarios": SCENARIOS}


RUNNER = SimulatorRunner()


def main(argv=None):
    ap = argparse.ArgumentParser(description="ASTRA synthetic mission simulator (HTTP mode)")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), default="nominal")
    ap.add_argument("--speed", type=float, default=24.0, help="simulated hours per real second")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--keys", default=None, help="device key file (default: backend/data/device_keys.json)")
    args = ap.parse_args(argv)
    runner = SimulatorRunner(HttpTransport(args.url, args.keys))
    runner.start(args.scenario, args.speed, args.days, args.seed)
    try:
        while runner.state in ("running", "paused"):
            time.sleep(1)
            s = runner.status()
            print(f"[{s['state']}] {s['scenario']} sim={s['sim_clock']} progress={s['progress']:.0%} counts={s['counts']}")
    except KeyboardInterrupt:
        runner.stop()
    print("final:", json.dumps(runner.status()["counts"]))


if __name__ == "__main__":
    main()
