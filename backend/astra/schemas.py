"""Pydantic request/response schemas (also used to generate OpenAPI)."""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import db

SourceType = Literal["manual", "medical_device", "wearable", "environmental_sensor", "clinician", "simulator"]
Quality = Literal["valid", "questionable", "unverified"]
ID_PATTERN = r"^[A-Za-z0-9._:\-]{1,64}$"


def _check_ts(v: str) -> str:
    db.parse_iso(v)
    return v


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ auth
class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginOut(BaseModel):
    token: str
    user: dict


CrewRole = Literal["astronaut", "medical_officer"]
USERNAME_PATTERN = r"^[a-z][a-z0-9._-]{1,31}$"


class UserCreateIn(Strict):
    """Administrator: register a crew account. Every crew account (astronaut or CMO) gets its own astronaut
    health record."""
    username: str = Field(pattern=USERNAME_PATTERN, description="lower-case login name, 2–32 characters")
    display_name: str = Field(min_length=1, max_length=80)
    role: CrewRole
    password: str = Field(min_length=1, max_length=256, description="Initial password (validated by the server "
                          "password policy, stored only as a scrypt hash, never returned)")
    name: str = Field(min_length=1, max_length=80, description="Astronaut's full name")
    call_sign: Optional[str] = Field(default=None, max_length=24)
    crew_role: Optional[str] = Field(default=None, max_length=60, description="Position, e.g. Flight Engineer")
    mission_id: Optional[str] = Field(default=None, pattern=ID_PATTERN, description="Defaults to the current mission")
    crew: str = Field(default="Prime Crew", min_length=1, max_length=40)
    birth_year: Optional[int] = Field(default=None, ge=1940, le=2015)


class PasswordResetIn(Strict):
    """Administrator: set a new password for a crew account. Existing passwords can never be retrieved."""
    password: str = Field(min_length=1, max_length=256)


class UserUpdateIn(Strict):
    """Administrator: edit a user. Only crew roles can be assigned; administrators cannot be created here.
    For a flight-surgeon account only display_name and mission_id (the assigned mission) can be changed."""
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    role: Optional[CrewRole] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    call_sign: Optional[str] = Field(default=None, max_length=24)
    crew_role: Optional[str] = Field(default=None, max_length=60)
    mission_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    crew: Optional[str] = Field(default=None, min_length=1, max_length=40)


# ------------------------------------------------------------------ observations
class SymptomIn(Strict):
    code: str = Field(description="Symptom code from the ASTRA symptom vocabulary (GET /api/v1/symptoms)")
    severity: Optional[int] = Field(default=None, ge=1, le=5)
    onset_at: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("onset_at")
    @classmethod
    def _onset(cls, v):
        return _check_ts(v) if v else v


class ObservationIn(Strict):
    """Unified observation format used by ALL input methods (manual, device, wearable, environmental)."""
    observation_id: Optional[str] = Field(default=None, pattern=ID_PATTERN,
                                          description="Sender-assigned unique ID (idempotency). Assigned by server if omitted.")
    astronaut_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    mission_id: str = Field(pattern=ID_PATTERN)
    metric_code: str
    value: Union[bool, float, int, str, dict]
    unit: str
    measured_at: str = Field(description="ISO-8601 timestamp with timezone; stored in UTC")
    source_type: SourceType
    device_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    quality: Quality = "unverified"
    context: dict[str, Any] = Field(default_factory=dict)
    location: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    symptoms: list[SymptomIn] = Field(default_factory=list)
    synthetic: bool = Field(default=False, description="Sender declares the record SYNTHETIC")

    @field_validator("measured_at")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class TelemetryBatchIn(Strict):
    batch_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    observations: list[dict[str, Any]] = Field(min_length=1, max_length=1000,
                                               description="Each item must follow the ObservationIn schema; items are validated individually")


class AcceptedItem(BaseModel):
    index: int
    observation_id: str
    metric_code: str
    status: Literal["accepted", "duplicate"]


class RejectedItem(BaseModel):
    index: int
    observation_id: Optional[str]
    errors: list[str]


class TelemetryResult(BaseModel):
    processing_status: Literal["complete", "partial", "rejected"]
    batch_id: Optional[str]
    accepted: list[AcceptedItem]
    rejected: list[RejectedItem]
    validation_errors: int
    assessments: list[str]
    alerts_created: list[str]
    alerts_updated: list[str]


class ManualItem(Strict):
    metric_code: str
    value: Union[bool, float, int, str, dict]
    unit: str


class ManualMeasurementIn(Strict):
    """Manual astronaut input. Several items measured together (e.g. systolic + diastolic) form one panel."""
    client_submission_id: Optional[str] = Field(default=None, pattern=ID_PATTERN,
                                                description="Client-generated ID so retried submissions are not duplicated")
    astronaut_id: Optional[str] = None
    measured_at: str
    source_type: Literal["manual", "medical_device", "clinician"] = "manual"
    device_id: Optional[str] = None
    method: Optional[str] = Field(default=None, max_length=64, description="Measurement method, e.g. 'oral', 'cuff_upper_arm'")
    quality: Quality = "unverified"
    context: dict[str, Any] = Field(default_factory=dict)
    items: list[ManualItem] = Field(min_length=1, max_length=10)
    symptoms: list[SymptomIn] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("measured_at")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class HistoryQuery(Strict):
    astronaut_id: Optional[str] = None
    metric_code: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    source_type: Optional[str] = None
    quality: Optional[str] = None
    location: Optional[str] = None
    context_key: Optional[str] = Field(default=None, description="e.g. 'resting' for heart rate, test name for performance tests")
    bucket: Optional[Literal["raw", "hour", "day", "week"]] = "raw"
    limit: int = Field(default=500, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)
    order: Literal["asc", "desc"] = "asc"


class LatestQuery(Strict):
    astronaut_id: Optional[str] = None
    metric_code: Optional[list[str] | str] = None


# ------------------------------------------------------------------ domain records
class SleepIn(Strict):
    client_submission_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    astronaut_id: Optional[str] = None
    sleep_start: str
    sleep_end: str
    corrected_duration_min: Optional[float] = Field(default=None, ge=0, le=1440,
                                                    description="Correction for interrupted sleep; otherwise computed from start/end")
    interruption_note: Optional[str] = Field(default=None, max_length=500)
    quality: Optional[int] = Field(default=None, ge=1, le=5)
    awakenings: Optional[int] = Field(default=None, ge=0, le=50)
    restfulness: Optional[int] = Field(default=None, ge=1, le=5)
    fatigue_after_waking: Optional[int] = Field(default=None, ge=1, le=5)
    scheduled_opportunity_min: Optional[float] = Field(default=None, ge=0, le=1440)
    source_type: Literal["manual", "wearable", "simulator"] = "manual"
    synthetic: bool = False

    @field_validator("sleep_start", "sleep_end")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class MoodIn(Strict):
    client_submission_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    astronaut_id: Optional[str] = None
    assessed_at: str
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    stress: Optional[int] = Field(default=None, ge=1, le=5)
    fatigue: Optional[int] = Field(default=None, ge=1, le=5)
    sleep_rating: Optional[int] = Field(default=None, ge=1, le=5, description="How well did you sleep?")
    workload: Optional[int] = Field(default=None, ge=1, le=5, description="How mentally demanding was today's workload?")
    connectedness: Optional[int] = Field(default=None, ge=1, le=5, description="Do you feel socially connected to the crew?")
    note_for_medical: Optional[str] = Field(default=None, max_length=2000, description="Anything you want medical support to know?")
    private_note: Optional[str] = Field(default=None, max_length=2000)
    cognitive_pvt_rt_ms: Optional[float] = Field(default=None, ge=100, le=5000)
    synthetic: bool = False

    @field_validator("assessed_at")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class ExerciseIn(Strict):
    client_submission_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    astronaut_id: Optional[str] = None
    exercise_type: str = Field(min_length=1, max_length=64)
    category: Literal["aerobic", "resistive", "flexibility", "balance", "performance_test", "other"]
    start_at: str
    duration_min: Optional[float] = Field(default=None, ge=0, le=300)
    intensity: Optional[Literal["low", "moderate", "high", "max"]] = None
    completion_status: Literal["completed", "partial", "skipped", "planned"]
    performance_notes: Optional[str] = Field(default=None, max_length=1000)
    performance_test: Optional[dict[str, Any]] = Field(default=None, description="{'test': 'grip_strength', 'value': 42, 'unit': 'kg'}")
    pain_score: Optional[int] = Field(default=None, ge=0, le=10)
    pain_location: Optional[str] = Field(default=None, max_length=64)
    source_type: Literal["manual", "medical_device", "simulator"] = "manual"
    device_id: Optional[str] = None
    synthetic: bool = False

    @field_validator("start_at")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class NutritionIn(Strict):
    client_submission_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    astronaut_id: Optional[str] = None
    recorded_at: str
    record_type: Literal["water", "meal", "snack"]
    water_ml: Optional[float] = Field(default=None, ge=0, le=10000)
    description: Optional[str] = Field(default=None, max_length=500)
    energy_kcal: Optional[float] = Field(default=None, ge=0, le=5000)
    appetite: Optional[int] = Field(default=None, ge=1, le=5)
    digestion_symptoms: Optional[str] = Field(default=None, max_length=500)
    source_type: Literal["manual", "simulator"] = "manual"
    synthetic: bool = False

    @field_validator("recorded_at")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class MedicationIn(Strict):
    astronaut_id: str
    medication: str = Field(min_length=1, max_length=128)
    dose_text: Optional[str] = Field(default=None, max_length=128)
    route: Optional[str] = Field(default=None, max_length=64)
    administered_at: str
    approved_instruction_ref: str = Field(min_length=1, max_length=128,
                                          description="Reference to the approved medical instruction authorizing this medication")
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("administered_at")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class MedicalHistoryIn(Strict):
    astronaut_id: str
    entry_type: Literal["allergy", "condition", "examination", "prior_event", "clinician_observation", "procedure"]
    title: str = Field(min_length=1, max_length=200)
    details: Optional[str] = Field(default=None, max_length=4000)
    is_private: bool = True


# ------------------------------------------------------------------ baselines / rules
class BaselineProposeIn(Strict):
    astronaut_id: str
    metric_code: str
    context_key: str = ""
    period_start: str
    period_end: str
    source: Literal["pre_mission", "in_flight_window"] = "in_flight_window"
    notes: Optional[str] = Field(default=None, max_length=1000)


class BaselineApproveIn(Strict):
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class RuleUpdateIn(Strict):
    active: Optional[bool] = None
    params: Optional[dict[str, Any]] = None
    approval_status: Optional[str] = Field(default=None, max_length=64)
    effective_date: Optional[str] = None


# ------------------------------------------------------------------ alerts / events
class AlertActionIn(Strict):
    note: Optional[str] = Field(default=None, max_length=2000)


class EventTransitionIn(Strict):
    to_state: Literal["DETECTED", "VERIFYING", "ACTIVE", "ESCALATED", "MONITORING", "RESOLVED"]
    reason: Optional[str] = Field(default=None, max_length=2000)


class EventActionIn(Strict):
    action_type: Literal["checklist_item", "protocol_step", "note", "observation_link"]
    description: str = Field(min_length=1, max_length=2000)
    data: dict[str, Any] = Field(default_factory=dict)


class EscalateIn(Strict):
    note: Optional[str] = Field(default=None, max_length=2000)
    outstanding_questions: list[str] = Field(default_factory=list)


class ReportCreateIn(Strict):
    outstanding_questions: list[str] = Field(default_factory=list)
    queue_for_transmission: bool = True


class ListQuery(Strict):
    astronaut_id: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AstronautQuery(Strict):
    astronaut_id: Optional[str] = None
    days: int = Field(default=14, ge=1, le=3650)


# ------------------------------------------------------------------ devices / sim / sync
class DeviceStatusIn(Strict):
    status: Literal["connected", "disconnected", "error", "low_battery"]
    battery_pct: Optional[float] = Field(default=None, ge=0, le=100)


class DeviceReadingIn(Strict):
    """Raw device-native payload converted by the device's adapter."""
    reading: dict[str, Any]
    measured_at: str
    reading_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    astronaut_id: Optional[str] = Field(default=None, description="Required for shared devices (e.g. med-bay BP cuff) that are not assigned to one astronaut")

    @field_validator("measured_at")
    @classmethod
    def _ts(cls, v):
        return _check_ts(v)


class SimulatorStartIn(Strict):
    scenario: Literal["nominal", "cardiovascular", "sleep_fatigue", "illness", "radiation_event",
                      "musculoskeletal", "behavioral", "emergency"]
    speed: float = Field(default=6.0, ge=0.25, le=96, description="Simulated hours per real second")
    days: int = Field(default=10, ge=2, le=30)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    astronaut_id: Optional[str] = Field(default=None, pattern=ID_PATTERN,
                                        description="Astronaut to generate data for. Crew members: must be omitted or their own id. "
                                                    "Administrator/flight surgeon: default AST-001")
    whole_crew: bool = Field(default=False, description="Administrator/flight surgeon only: also generate nominal data for "
                                                        "every other crew member (mission-operations simulation)")


class SimulatorResetQuery(Strict):
    astronaut_id: Optional[str] = Field(default=None, pattern=ID_PATTERN,
                                        description="Administrator/flight surgeon: remove only this astronaut's generated data")


class SimulatorSpeedIn(Strict):
    speed: float = Field(ge=0.25, le=96)


class LinkIn(Strict):
    earth_link_status: Literal["online", "degraded", "offline"]
    comm_delay_seconds: Optional[float] = Field(default=None, ge=0, le=3600)


class EnvironmentQuery(Strict):
    metric_code: Optional[str] = None
    location: Optional[str] = None
    hours: int = Field(default=240, ge=1, le=24 * 365)


class AssessmentRunIn(Strict):
    astronaut_id: Optional[str] = None
