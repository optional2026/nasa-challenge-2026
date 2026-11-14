"""Synthetic demonstration dataset: mission, crew, users, simulated devices,
assessment schedule, pre-mission reference measurements and clinician-approved
(synthetic) baselines. EVERYTHING created here is labelled SYNTHETIC."""
from __future__ import annotations

import json
import math
import random
from datetime import timedelta

from . import config, db, security
from .devices.adapters import ADAPTERS
from .security import SYSTEM, Principal
from .services import baselines, ingestion, knowledge

DEMO_PASSWORD = "astra-demo"
MISSION_ID = "MSN-ARES-T1"

ASTRONAUTS = [
    {"id": "AST-001", "name": "Elena Vega", "call_sign": "VEGA", "crew_role": "Commander", "birth_year": 1986, "glucose": 1,
     "p": {"hr": (58, 3), "sbp": (112, 5), "dbp": (72, 4), "spo2": (98.2, 0.6), "rr": (13, 1.0), "temp": (36.6, 0.12),
           "glu": (88, 6), "sleep": (450, 22), "mood": (4.0, 0.45), "stress": (2.0, 0.45), "fatigue": (2.0, 0.45),
           "workload": (3.0, 0.5), "conn": (4.0, 0.45), "pvt": (268, 12), "water": (2300, 160), "grip": (38, 1.1)}},
    {"id": "AST-002", "name": "Kenji Mori", "call_sign": "MORI", "crew_role": "Crew Medical Officer", "birth_year": 1983, "glucose": 0,
     "p": {"hr": (62, 3.5), "sbp": (118, 6), "dbp": (76, 4), "spo2": (97.8, 0.7), "rr": (14, 1.1), "temp": (36.7, 0.14),
           "glu": (92, 7), "sleep": (420, 25), "mood": (3.8, 0.45), "stress": (2.2, 0.45), "fatigue": (2.2, 0.45),
           "workload": (3.2, 0.5), "conn": (3.8, 0.45), "pvt": (281, 14), "water": (2500, 180), "grip": (44, 1.4)}},
    {"id": "AST-003", "name": "Amara Okafor", "call_sign": "OKAFOR", "crew_role": "Flight Engineer", "birth_year": 1990, "glucose": 0,
     "p": {"hr": (55, 3), "sbp": (108, 5), "dbp": (69, 4), "spo2": (98.4, 0.5), "rr": (12, 1.0), "temp": (36.5, 0.12),
           "glu": (85, 6), "sleep": (465, 20), "mood": (4.2, 0.4), "stress": (1.8, 0.4), "fatigue": (1.8, 0.4),
           "workload": (2.8, 0.5), "conn": (4.2, 0.4), "pvt": (255, 11), "water": (2200, 150), "grip": (35, 1.0)}},
]

USERS = [
    ("vega", "Cmdr. Elena Vega", "astronaut", "AST-001"),
    ("okafor", "Amara Okafor (Flight Engineer)", "astronaut", "AST-003"),
    ("mori", "Dr. Kenji Mori (Crew Medical Officer)", "medical_officer", "AST-002"),
    ("ramirez", "Dr. Lucia Ramirez (Ground Flight Surgeon)", "flight_surgeon", None),
    ("admin", "Mission Systems Administrator", "admin", None),
]

BASELINE_METRICS = [("heart_rate", "resting"), ("bp_systolic", ""), ("bp_diastolic", ""), ("spo2", ""),
                    ("respiratory_rate", ""), ("body_temperature", ""), ("blood_glucose", ""), ("sleep_duration", ""),
                    ("mood", ""), ("stress", ""), ("fatigue", ""), ("workload", ""), ("social_connectedness", ""),
                    ("cognitive_pvt_rt", ""), ("water_intake", "daily_total"), ("physical_performance", "grip_strength")]

SCHEDULE = [
    ("vitals_bp", "Blood pressure", ["bp_systolic", "bp_diastolic"], 24, 1, 0),
    ("vitals_hr", "Resting heart rate", ["heart_rate"], 24, 1, 0),
    ("vitals_spo2", "Oxygen saturation", ["spo2"], 24, 1, 0),
    ("vitals_temp", "Body temperature", ["body_temperature"], 24, 1, 0),
    ("vitals_rr", "Respiratory rate", ["respiratory_rate"], 24, 1, 0),
    ("sleep_log", "Sleep log", ["sleep_duration"], 24, 1, 0),
    ("checkin", "Private daily check-in (mood, stress, fatigue)", ["mood", "stress", "fatigue"], 24, 1, 0),
    ("exercise", "Exercise session log", ["exercise_session"], 24, 1, 0),
    ("hydration", "Water intake", ["water_intake"], 12, 1, 0),
    ("performance", "Weekly physical performance test", ["physical_performance"], 168, 1, 0),
    ("cognitive", "Reaction-time test (optional)", ["cognitive_pvt_rt"], 72, 0, 0),
]

DEVICE_PLAN = [
    # id, type, model, astronaut, location
    ("DEV-HRW-001", "heart_rate_wearable", "SIM-Wristband HRW-1", "AST-001", None),
    ("DEV-HRW-002", "heart_rate_wearable", "SIM-Wristband HRW-1", "AST-002", None),
    ("DEV-HRW-003", "heart_rate_wearable", "SIM-Wristband HRW-1", "AST-003", None),
    ("DEV-BPM-01", "blood_pressure_monitor", "SIM-Cuff BPM-2", None, "MED-BAY"),
    ("DEV-OXI-01", "pulse_oximeter", "SIM-Oximeter OX-3", None, "MED-BAY"),
    ("DEV-THM-01", "thermometer", "SIM-Thermometer TH-1", None, "MED-BAY"),
    ("DEV-GLU-01", "glucose_monitor", "SIM-Glucose Meter GM-1", "AST-001", None),
    ("DEV-ENV-HABA", "environmental_sensor", "SIM-Air Monitor AM-4", None, "HAB-A"),
    ("DEV-ENV-LAB", "environmental_sensor", "SIM-Air Monitor AM-4", None, "LAB"),
    ("DEV-RAD-HABA", "radiation_dosimeter", "SIM-Area Radiation Monitor RAM-1", None, "HAB-A"),
    ("DEV-DOS-001", "radiation_dosimeter", "SIM-Personal Dosimeter PD-1", "AST-001", None),
    ("DEV-DOS-002", "radiation_dosimeter", "SIM-Personal Dosimeter PD-1", "AST-002", None),
    ("DEV-DOS-003", "radiation_dosimeter", "SIM-Personal Dosimeter PD-1", "AST-003", None),
]


def device_keys_path():
    return config.DATA_DIR / "device_keys.json"


def is_seeded(conn) -> bool:
    return db.one(conn, "SELECT id FROM missions WHERE id=?", (MISSION_ID,)) is not None


def seed_all(conn, now=None, rng_seed: int = 7) -> dict:
    knowledge.seed_knowledge(conn)
    if is_seeded(conn):
        return {"seeded": False}
    now = now or db.utcnow()
    rng = random.Random(rng_seed)
    launch = (now - timedelta(days=12)).replace(hour=6, minute=0, second=0, microsecond=0)
    t0 = db.now_iso()
    with db.transaction(conn):
        db.insert(conn, "missions", {"id": MISSION_ID, "name": "ARES-T1 Mars Transit (SYNTHETIC DEMO)",
                                     "mission_type": "mars_transit", "start_utc": db.iso(launch),
                                     "planned_duration_days": 210, "comm_delay_seconds": 300.0,
                                     "earth_link_status": "online", "is_synthetic": 1,
                                     "notes": "Synthetic demonstration mission. Comm delay is a configurable demo value."})
        for phase, loc, g, s, e in [("Pre-flight quarantine", "Earth", 1.0, launch - timedelta(days=45), launch),
                                    ("Launch and Earth-orbit checkout", "Earth orbit", 0.0, launch, launch + timedelta(days=1)),
                                    ("Trans-Mars cruise", "Interplanetary space", 0.0, launch + timedelta(days=1), None)]:
            db.insert(conn, "mission_environments", {"mission_id": MISSION_ID, "phase": phase, "location": loc, "gravity_g": g,
                                                     "start_utc": db.iso(s), "end_utc": db.iso(e) if e else None,
                                                     "notes": "SYNTHETIC"})
        for a in ASTRONAUTS:
            db.insert(conn, "astronauts", {"id": a["id"], "mission_id": MISSION_ID, "name": a["name"], "call_sign": a["call_sign"],
                                           "crew_role": a["crew_role"], "birth_year": a["birth_year"],
                                           "glucose_monitoring_enabled": a["glucose"], "is_synthetic": 1, "created_at": t0})
            for code, title, metrics, interval, required, clin in SCHEDULE:
                db.insert(conn, "assessment_schedule", {"astronaut_id": a["id"], "task_code": code, "title": title,
                                                        "metric_codes": db.dumps(metrics), "interval_hours": interval,
                                                        "required": required, "clinician_directed": clin, "active": 1})
            if a["glucose"]:
                db.insert(conn, "assessment_schedule", {"astronaut_id": a["id"], "task_code": "glucose",
                                                        "title": "Blood glucose (clinician-directed)",
                                                        "metric_codes": db.dumps(["blood_glucose"]), "interval_hours": 24,
                                                        "required": 1, "clinician_directed": 1, "active": 1})
        for username, display, role, ast in USERS:
            db.insert(conn, "users", {"username": username, "display_name": display,
                                      "password_hash": security.hash_password(config.demo_password()), "role": role,
                                      "astronaut_id": ast, "active": 1, "created_at": t0})
        keys = {}
        for dev_id, dtype, model, ast, loc in DEVICE_PLAN:
            key = security.new_device_key()
            keys[dev_id] = key
            db.insert(conn, "devices", {"id": dev_id, "device_type": dtype, "adapter": type(ADAPTERS[dtype]).__name__,
                                        "model": model, "serial": f"SIM-{dev_id[-6:]}", "mission_id": MISSION_ID,
                                        "astronaut_id": ast, "location": loc, "api_key_hash": security.hash_device_key(key),
                                        "status": "disconnected", "is_simulated": 1, "hardware_validated": 0,
                                        "last_seen_at": None, "battery_pct": 100.0,
                                        "metadata": db.dumps({"metrics": list(ADAPTERS[dtype].metrics),
                                                              "note": "SIMULATED device — no physical hardware tested"}),
                                        "created_at": t0})
        for a in ASTRONAUTS:
            for etype, title, details in [
                ("allergy", "No known drug allergies", "SYNTHETIC demonstration record."),
                ("examination", "Pre-flight medical certification complete", "SYNTHETIC demonstration record."),
                ("examination", "Pre-flight eye examination on file (ground)", "SYNTHETIC — detailed results held by ground medical team."),
                ("examination", "Pre-flight bone densitometry on file (ground)", "SYNTHETIC — specialized bone assessment; in-flight equivalent not available on this vehicle."),
            ]:
                db.insert(conn, "medical_history", {"id": db.new_id("MH"), "astronaut_id": a["id"], "entry_type": etype,
                                                    "title": title, "details": details, "recorded_by": "user:ramirez",
                                                    "recorded_at": t0, "is_private": 1, "is_synthetic": 1})
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    device_keys_path().write_text(json.dumps(keys, indent=2))

    # ---------------------------------------------------- pre-mission reference measurements (L-40 .. L-26)
    base_start = launch - timedelta(days=40)
    base_end = launch - timedelta(days=26)
    total = 0
    for a in ASTRONAUTS:
        items = _premission_items(a, base_start, rng)
        res = ingestion.ingest(conn, SYSTEM, items, batch_id=f"SEED-{a['id']}", run_assessment=False)
        assert not res["rejected"], res["rejected"][:3]
        total += len(res["accepted"])
        _premission_records(conn, a, base_start, rng)
    # ---------------------------------------------------- baselines approved by the (synthetic) flight surgeon
    fs = Principal(kind="user", name="ramirez", role="flight_surgeon")
    count = 0
    for a in ASTRONAUTS:
        for metric, ck in BASELINE_METRICS:
            if metric == "blood_glucose" and not a["glucose"]:
                continue
            b = baselines.propose(conn, fs, a["id"], metric, db.iso(base_start), db.iso(base_end), source="pre_mission",
                                  context_key=ck, notes="SYNTHETIC pre-mission baseline (L-40 to L-26)", synthetic=True)
            baselines.approve(conn, fs, b["id"], notes="SYNTHETIC — approved for demonstration only")
            count += 1
    return {"seeded": True, "observations": total, "baselines": count, "launch": db.iso(launch)}


def _g(rng, mean_sd):
    m, s = mean_sd
    return rng.gauss(m, s)


def _premission_items(a, start, rng) -> list[dict]:
    p, aid = a["p"], a["id"]
    items = []

    def add(metric, value, unit, t, ctx=None, src="medical_device", dev=None):
        items.append({"astronaut_id": aid, "mission_id": MISSION_ID, "metric_code": metric, "value": value, "unit": unit,
                      "measured_at": db.iso(t), "source_type": src, "device_id": dev, "quality": "valid",
                      "context": dict(ctx or {}, phase="pre_mission"), "synthetic": True})
    n = int(aid[-1])
    for d in range(14):
        day = start + timedelta(days=d)
        for h in (7, 12, 17, 21):
            add("heart_rate", round(_g(rng, p["hr"]) + 1.5 * math.sin(h / 24 * 2 * math.pi), 1), "bpm",
                day + timedelta(hours=h, minutes=rng.randint(0, 20)), {"activity": "resting"}, "wearable", f"DEV-HRW-00{n}")
        t = day + timedelta(hours=7, minutes=30)
        add("bp_systolic", round(_g(rng, p["sbp"])), "mmHg", t, {"activity": "resting"}, dev="DEV-BPM-01")
        add("bp_diastolic", round(_g(rng, p["dbp"])), "mmHg", t, {"activity": "resting"}, dev="DEV-BPM-01")
        add("spo2", round(min(100, _g(rng, p["spo2"]))), "%", t, dev="DEV-OXI-01")
        add("respiratory_rate", round(_g(rng, p["rr"])), "breaths/min", t, {"method": "counted"}, src="clinician")
        add("body_temperature", round(_g(rng, p["temp"]), 2), "degC", t, {"method": "oral"}, dev="DEV-THM-01")
        if a["glucose"]:
            add("blood_glucose", round(_g(rng, p["glu"])), "mg/dL", t, {"meal_context": "fasting"}, dev="DEV-GLU-01")
        add("sleep_duration", round(_g(rng, p["sleep"])), "min", day + timedelta(hours=6, minutes=30), {}, "wearable", f"DEV-HRW-00{n}")
        ev = day + timedelta(hours=21, minutes=15)
        for metric, key in (("mood", "mood"), ("stress", "stress"), ("fatigue", "fatigue"), ("workload", "workload"),
                            ("social_connectedness", "conn")):
            add(metric, int(min(5, max(1, round(_g(rng, p[key]))))), "score_1_5", ev, {}, "manual")
        if d % 3 == 0:
            add("cognitive_pvt_rt", round(_g(rng, p["pvt"])), "ms", ev, {"test": "pvt_mean_rt"}, "manual")
        daily = _g(rng, p["water"])
        for k, frac in enumerate((0.25, 0.2, 0.2, 0.2, 0.15)):
            add("water_intake", round(daily * frac), "mL", day + timedelta(hours=8 + 3 * k), {"record_type": "water"}, "manual")
        if d in (1, 4, 8, 12):
            add("physical_performance", round(_g(rng, p["grip"]), 1), "kg", day + timedelta(hours=10), {"test": "grip_strength"},
                "manual")
    return items


def _premission_records(conn, a, start, rng):
    with db.transaction(conn):
        for d in range(14):
            day = start + timedelta(days=d)
            for slot, etype, cat in ((9, "Treadmill (T2-style) aerobic", "aerobic"), (15, "Resistive exercise (ARED-style)", "resistive")):
                db.insert(conn, "exercise_records", {
                    "id": db.new_id("EXR"), "astronaut_id": a["id"], "exercise_type": etype, "category": cat,
                    "start_at": db.iso(day + timedelta(hours=slot)), "duration_min": 45.0, "intensity": "moderate",
                    "completion_status": "completed", "performance_notes": "pre-mission (SYNTHETIC)", "observation_id": None,
                    "source_type": "manual", "is_synthetic": 1, "sim_run_id": None, "created_at": db.now_iso()})


def apply_demo_password(conn) -> None:
    """Keep the synthetic demo accounts on the configured demo password (idempotent)."""
    pw = config.demo_password()
    with db.transaction(conn):
        for username, *_ in USERS:
            u = db.one(conn, "SELECT password_hash FROM users WHERE username=?", (username,))
            if u and not security.verify_password(pw, u["password_hash"]):
                conn.execute("UPDATE users SET password_hash=? WHERE username=?", (security.hash_password(pw), username))
