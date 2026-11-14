"""Domain records (sleep, private check-in, exercise, nutrition, medication,
medical history). Each record is stored in its own table AND produces
observations through the unified ingestion pipeline, so every input method
shares one validation, storage and assessment path."""
from __future__ import annotations

import hashlib

from .. import audit, db
from ..security import MEDICAL_ROLES, Principal, can_view_astronaut
from . import ingestion


class RecordError(ValueError):
    def __init__(self, message: str, details=None):
        super().__init__(message)
        self.details = details


def resolve_astronaut(conn, p: Principal, astronaut_id: str | None) -> dict:
    ast_id = astronaut_id or p.astronaut_id
    if not ast_id:
        raise RecordError("astronaut_id is required")
    a = db.one(conn, "SELECT * FROM astronauts WHERE id=?", (ast_id,))
    if not a:
        raise LookupError(ast_id)
    if p.kind == "user":
        if p.role == "admin":
            raise PermissionError("administrators cannot create health records")
        if p.role == "astronaut" and p.astronaut_id != ast_id:
            raise PermissionError("astronauts may only create their own records")
        if p.role == "medical_officer" and not can_view_astronaut(p, ast_id):
            raise PermissionError("the Crew Medical Officer may only create records for astronauts in their crew")
    return a


def _rid(prefix: str, client_id: str | None, ast_id: str) -> tuple[str, bool]:
    if client_id:
        return f"{prefix}-" + hashlib.sha256(f"{ast_id}:{client_id}".encode()).hexdigest()[:12].upper(), True
    return db.new_id(prefix), False


def _ingest(conn, p, items, sim_run_id=None):
    res = ingestion.ingest(conn, p, items, batch_id=db.new_id("BATCH"), sim_run_id=sim_run_id)
    if res["rejected"]:
        raise RecordError("record failed validation", res["rejected"])
    return res


def create_sleep(conn, p: Principal, body, sim_run_id=None) -> dict:
    a = resolve_astronaut(conn, p, body.astronaut_id)
    rid, det = _rid("SLP", body.client_submission_id, a["id"])
    if det and db.one(conn, "SELECT id FROM sleep_records WHERE id=?", (rid,)):
        return {"record": db.one(conn, "SELECT * FROM sleep_records WHERE id=?", (rid,)), "duplicate": True}
    start, end = db.parse_iso(body.sleep_start), db.parse_iso(body.sleep_end)
    if end <= start:
        raise RecordError("sleep_end must be after sleep_start")
    computed = (end - start).total_seconds() / 60
    if computed > 24 * 60:
        raise RecordError("sleep period longer than 24 h")
    if body.corrected_duration_min is not None and body.corrected_duration_min > computed:
        raise RecordError("corrected duration cannot exceed the time between sleep start and end")
    duration = body.corrected_duration_min if body.corrected_duration_min is not None else computed
    src = body.source_type
    base = {"astronaut_id": a["id"], "mission_id": a["mission_id"], "measured_at": body.sleep_end,
            "source_type": src, "quality": "valid" if src in ("wearable", "simulator") else "unverified",
            "synthetic": body.synthetic or src == "simulator",
            "context": {"sleep_record_id": rid, "sleep_start": body.sleep_start, "corrected": body.corrected_duration_min is not None}}
    if src == "simulator":
        base["quality"] = "valid"
    items = [dict(base, observation_id=f"{rid}-DUR", metric_code="sleep_duration", value=round(duration, 1), unit="min")]
    if body.quality is not None:
        items.append(dict(base, observation_id=f"{rid}-QUAL", metric_code="sleep_quality", value=body.quality, unit="score_1_5"))
    if body.awakenings is not None:
        items.append(dict(base, observation_id=f"{rid}-AWK", metric_code="sleep_awakenings", value=body.awakenings, unit="count"))
    if body.scheduled_opportunity_min is not None:
        items.append(dict(base, observation_id=f"{rid}-OPP", metric_code="sleep_opportunity", value=body.scheduled_opportunity_min, unit="min"))
    if body.fatigue_after_waking is not None:
        items.append(dict(base, observation_id=f"{rid}-FAT", metric_code="fatigue", value=body.fatigue_after_waking, unit="score_1_5"))
    res = _ingest(conn, p, items, sim_run_id)
    with db.transaction(conn):
        db.insert(conn, "sleep_records", {
            "id": rid, "astronaut_id": a["id"], "sleep_start": db.iso(start), "sleep_end": db.iso(end),
            "computed_duration_min": round(computed, 1),
            "reported_duration_min": body.corrected_duration_min, "interruption_note": body.interruption_note,
            "quality": body.quality, "awakenings": body.awakenings, "restfulness": body.restfulness,
            "fatigue_after_waking": body.fatigue_after_waking, "scheduled_opportunity_min": body.scheduled_opportunity_min,
            "observation_id": f"{rid}-DUR", "source_type": src, "is_synthetic": int(body.synthetic or src == "simulator"),
            "sim_run_id": sim_run_id, "created_at": db.now_iso()})
    return {"record": db.one(conn, "SELECT * FROM sleep_records WHERE id=?", (rid,)), "ingestion": res, "duplicate": False}


def create_mood(conn, p: Principal, body, sim_run_id=None) -> dict:
    a = resolve_astronaut(conn, p, body.astronaut_id)
    if p.kind == "user" and p.role != "astronaut" and p.astronaut_id != a["id"]:
        raise PermissionError("the private check-in can only be completed by the astronaut themself")
    rid, det = _rid("MOOD", body.client_submission_id, a["id"])
    if det and db.one(conn, "SELECT id FROM mood_assessments WHERE id=?", (rid,)):
        return {"record": decode_mood(db.one(conn, "SELECT * FROM mood_assessments WHERE id=?", (rid,))), "duplicate": True}
    fields = ["mood", "stress", "fatigue", "sleep_rating", "workload", "connectedness"]
    skipped = [f for f in fields if getattr(body, f) is None]
    synthetic = body.synthetic or sim_run_id is not None
    src = "simulator" if synthetic and sim_run_id else "manual"
    base = {"astronaut_id": a["id"], "mission_id": a["mission_id"], "measured_at": body.assessed_at, "source_type": src,
            "quality": "valid", "synthetic": synthetic}
    items = []
    mapping = {"mood": "mood", "stress": "stress", "fatigue": "fatigue", "workload": "workload", "connectedness": "social_connectedness"}
    for f, metric in mapping.items():
        v = getattr(body, f)
        if v is not None:
            ctx = {"mood_assessment_id": rid}
            if f == "mood" and body.note_for_medical:
                ctx["has_note_for_medical"] = True
            items.append(dict(base, observation_id=f"{rid}-{f.upper()[:5]}", metric_code=metric, value=v, unit="score_1_5", context=ctx))
    if body.note_for_medical and body.mood is None:
        raise RecordError("to send a note to medical support, please also answer the mood question (or use the medical communication channel)")
    if body.cognitive_pvt_rt_ms is not None:
        items.append(dict(base, observation_id=f"{rid}-PVT", metric_code="cognitive_pvt_rt", value=body.cognitive_pvt_rt_ms,
                          unit="ms", context={"mood_assessment_id": rid, "test": "pvt_mean_rt"}))
    res = _ingest(conn, p, items, sim_run_id) if items else None
    with db.transaction(conn):
        db.insert(conn, "mood_assessments", {
            "id": rid, "astronaut_id": a["id"], "assessed_at": db.iso(db.parse_iso(body.assessed_at)),
            "mood": body.mood, "stress": body.stress, "fatigue": body.fatigue, "sleep_rating": body.sleep_rating,
            "workload": body.workload, "connectedness": body.connectedness, "note_for_medical": body.note_for_medical,
            "private_note": body.private_note, "skipped": db.dumps(skipped), "is_synthetic": int(synthetic),
            "sim_run_id": sim_run_id, "created_at": db.now_iso()})
        audit.record(conn, p, "mood.create", "mood_assessment", rid, {"skipped": skipped})
    return {"record": decode_mood(db.one(conn, "SELECT * FROM mood_assessments WHERE id=?", (rid,))), "ingestion": res, "duplicate": False}


def decode_mood(r: dict) -> dict:
    r = dict(r)
    r["skipped"] = db.loads(r["skipped"], [])
    r["is_synthetic"] = bool(r["is_synthetic"])
    return r


def create_exercise(conn, p: Principal, body, sim_run_id=None) -> dict:
    a = resolve_astronaut(conn, p, body.astronaut_id)
    rid, det = _rid("EXR", body.client_submission_id, a["id"])
    if det and db.one(conn, "SELECT id FROM exercise_records WHERE id=?", (rid,)):
        return {"record": db.one(conn, "SELECT * FROM exercise_records WHERE id=?", (rid,)), "duplicate": True}
    if body.completion_status in ("completed", "partial") and body.duration_min is None and body.category != "performance_test":
        raise RecordError("duration_min is required for completed or partial sessions")
    synthetic = body.synthetic or body.source_type == "simulator"
    base = {"astronaut_id": a["id"], "mission_id": a["mission_id"], "measured_at": body.start_at,
            "source_type": body.source_type, "device_id": body.device_id,
            "quality": "valid" if body.source_type in ("medical_device", "simulator") else "unverified", "synthetic": synthetic}
    items = []
    obs_id = None
    if body.category != "performance_test":
        obs_id = f"{rid}-DUR"
        items.append(dict(base, observation_id=obs_id, metric_code="exercise_session",
                          value=float(body.duration_min or 0), unit="min",
                          context={"exercise_record_id": rid, "exercise_type": body.exercise_type, "category": body.category,
                                   "intensity": body.intensity, "completion_status": body.completion_status}))
    if body.performance_test:
        t = body.performance_test
        if not {"test", "value", "unit"} <= set(t):
            raise RecordError("performance_test requires test, value and unit")
        items.append(dict(base, observation_id=f"{rid}-PERF", metric_code="physical_performance", value=t["value"], unit=t["unit"],
                          context={"exercise_record_id": rid, "test": t["test"]}))
        obs_id = obs_id or f"{rid}-PERF"
    if body.pain_score is not None:
        items.append(dict(base, observation_id=f"{rid}-PAIN", metric_code="pain_score", value=body.pain_score, unit="score_0_10",
                          context={"exercise_record_id": rid, "location": body.pain_location}))
    res = _ingest(conn, p, items, sim_run_id) if items else None
    with db.transaction(conn):
        db.insert(conn, "exercise_records", {
            "id": rid, "astronaut_id": a["id"], "exercise_type": body.exercise_type, "category": body.category,
            "start_at": db.iso(db.parse_iso(body.start_at)), "duration_min": body.duration_min, "intensity": body.intensity,
            "completion_status": body.completion_status, "performance_notes": body.performance_notes,
            "observation_id": obs_id, "source_type": body.source_type, "is_synthetic": int(synthetic),
            "sim_run_id": sim_run_id, "created_at": db.now_iso()})
    return {"record": db.one(conn, "SELECT * FROM exercise_records WHERE id=?", (rid,)), "ingestion": res, "duplicate": False}


def create_nutrition(conn, p: Principal, body, sim_run_id=None) -> dict:
    a = resolve_astronaut(conn, p, body.astronaut_id)
    rid, det = _rid("NUT", body.client_submission_id, a["id"])
    if det and db.one(conn, "SELECT id FROM nutrition_records WHERE id=?", (rid,)):
        return {"record": db.one(conn, "SELECT * FROM nutrition_records WHERE id=?", (rid,)), "duplicate": True}
    if body.record_type == "water" and body.water_ml is None:
        raise RecordError("water_ml is required for water records")
    synthetic = body.synthetic or body.source_type == "simulator"
    base = {"astronaut_id": a["id"], "mission_id": a["mission_id"], "measured_at": body.recorded_at,
            "source_type": body.source_type, "quality": "valid" if synthetic else "unverified", "synthetic": synthetic,
            "context": {"nutrition_record_id": rid, "record_type": body.record_type}}
    items = []
    if body.water_ml is not None:
        items.append(dict(base, observation_id=f"{rid}-H2O", metric_code="water_intake", value=body.water_ml, unit="mL"))
    if body.energy_kcal is not None:
        items.append(dict(base, observation_id=f"{rid}-KCAL", metric_code="energy_intake", value=body.energy_kcal, unit="kcal"))
    if body.appetite is not None:
        items.append(dict(base, observation_id=f"{rid}-APP", metric_code="appetite", value=body.appetite, unit="score_1_5"))
    res = _ingest(conn, p, items, sim_run_id) if items else None
    with db.transaction(conn):
        db.insert(conn, "nutrition_records", {
            "id": rid, "astronaut_id": a["id"], "recorded_at": db.iso(db.parse_iso(body.recorded_at)),
            "record_type": body.record_type, "water_ml": body.water_ml, "description": body.description,
            "energy_kcal": body.energy_kcal, "appetite": body.appetite, "digestion_symptoms": body.digestion_symptoms,
            "source_type": body.source_type, "is_synthetic": int(synthetic), "sim_run_id": sim_run_id,
            "created_at": db.now_iso()})
    return {"record": db.one(conn, "SELECT * FROM nutrition_records WHERE id=?", (rid,)), "ingestion": res, "duplicate": False}


def create_medication(conn, p: Principal, body) -> dict:
    if p.role not in MEDICAL_ROLES:
        raise PermissionError("medication records are entered by medical personnel against an approved instruction")
    a = db.one(conn, "SELECT id FROM astronauts WHERE id=?", (body.astronaut_id,))
    if not a:
        raise LookupError(body.astronaut_id)
    if not can_view_astronaut(p, body.astronaut_id):
        raise PermissionError("the Crew Medical Officer may only record medication for astronauts in their crew")
    rid = db.new_id("MED")
    with db.transaction(conn):
        db.insert(conn, "medication_records", {
            "id": rid, "astronaut_id": body.astronaut_id, "medication": body.medication, "dose_text": body.dose_text,
            "route": body.route, "administered_at": db.iso(db.parse_iso(body.administered_at)),
            "approved_instruction_ref": body.approved_instruction_ref, "recorded_by": p.actor, "notes": body.notes,
            "is_synthetic": 0, "created_at": db.now_iso()})
        audit.record(conn, p, "medication.record", "medication_record", rid, {"astronaut_id": body.astronaut_id})
    return db.one(conn, "SELECT * FROM medication_records WHERE id=?", (rid,))


def create_history(conn, p: Principal, body) -> dict:
    if p.role not in MEDICAL_ROLES:
        raise PermissionError("medical history entries are entered by medical personnel")
    if not db.one(conn, "SELECT id FROM astronauts WHERE id=?", (body.astronaut_id,)):
        raise LookupError(body.astronaut_id)
    if not can_view_astronaut(p, body.astronaut_id):
        raise PermissionError("the Crew Medical Officer may only add history for astronauts in their crew")
    rid = db.new_id("MH")
    with db.transaction(conn):
        db.insert(conn, "medical_history", {
            "id": rid, "astronaut_id": body.astronaut_id, "entry_type": body.entry_type, "title": body.title,
            "details": body.details, "recorded_by": p.actor, "recorded_at": db.now_iso(),
            "is_private": int(body.is_private), "is_synthetic": 0})
        audit.record(conn, p, "medical_history.create", "medical_history", rid, {"type": body.entry_type})
    return db.one(conn, "SELECT * FROM medical_history WHERE id=?", (rid,))
