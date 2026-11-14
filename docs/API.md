# ASTRA REST API

Version 1.0.0. Generated from the server's route registry (`scripts/gen_api_docs.py`).
Interactive list: `/api/docs` · machine-readable: `/api/openapi.json` (also saved as `docs/openapi.json`).

Authentication: `POST /api/v1/auth/login` returns a bearer token (12 h). Devices authenticate with `X-Device-Key`.
Errors use one shape: `{"error": {"code", "message", "details"}}`. Validation errors return HTTP 422.

Real-time: WebSocket `/ws?token=<session token>` streams events (`observations.created`, `assessment.created`, `alert.created`,
`alert.updated`, `alert.acknowledged`, `alert.resolved`, `medical_event.created`, `medical_event.updated`, `environment.warning`,
`device.status`, `simulator.status`, `sync.updated`, `notification`). Private behavioral-health events are delivered only to
authorized connections (redacted for the Crew Medical Officer).

## alerts

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/alerts` | Alerts (filtered by role and privacy) | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/alerts/{alert_id}` | Alert detail | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/alerts/{alert_id}/acknowledge` | Acknowledge an alert (does not resolve the medical event) | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/alerts/{alert_id}/resolve` | Resolve an alert | bearer | astronaut, medical_officer, flight_surgeon |

## assessments

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/assessments` | Assessment history | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/assessments` | Run a full assessment now (all rules + missing-data checks) | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/assessments/{assessment_id}` | Assessment detail (findings, evidence, limitations) | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/trends` | Trend analysis for one indicator | bearer | astronaut, medical_officer, flight_surgeon |

## audit

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/audit` | Audit log (administrator, flight surgeon) | bearer | admin, flight_surgeon |

## auth

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| POST | `/api/v1/auth/login` | Log in and receive a session token | none | — |
| GET | `/api/v1/auth/me` | Current user | bearer | — |
| GET | `/api/v1/users` | List users (administrator) | bearer | admin |

## baselines

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/baselines` | Individual baselines (all versions) | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/baselines` | Propose a baseline from a period of valid observations (draft) | bearer | medical_officer, flight_surgeon |
| POST | `/api/v1/baselines/{baseline_id}/approve` | Approve a draft baseline (optionally with reference range) | bearer | medical_officer, flight_surgeon |
| POST | `/api/v1/baselines/{baseline_id}/retire` | Retire a baseline version | bearer | medical_officer, flight_surgeon |

## crew

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/astronauts` | Crew list (no health data) | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/astronauts/{astronaut_id}` | Astronaut profile, schedule and medical history | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/astronauts/{astronaut_id}/glucose-monitoring` | Enable/disable clinician-directed glucose monitoring | bearer | medical_officer, flight_surgeon |

## devices

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/devices` | Devices and connection status | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/devices/adapters` | Device adapter catalogue with example native payloads | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/devices/{device_id}/status` | Device heartbeat / status (device key) | bearer or device key | — |
| POST | `/api/v1/devices/{device_id}/readings` | Submit a device-native reading (converted by the device adapter) | bearer or device key | — |

## environment

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/environment` | Environment status: latest readings, open events, mission phase | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/environment/history` | Environmental history (optionally bucketed) | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/environment/events` | Environmental events | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/environment/radiation` | Radiation exposure history and dosimeters | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/environment/overlay` | Medical series alongside an environmental series (context only) | bearer | astronaut, medical_officer, flight_surgeon |

## ingestion

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| POST | `/api/v1/telemetry` | Telemetry ingestion (unified observation format) | bearer or device key | — |
| POST | `/api/v1/measurements/manual` | Manual measurement entry (one panel) | bearer | astronaut, medical_officer, flight_surgeon |

## knowledge

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/indicators` | Health indicator definitions | none | — |
| GET | `/api/v1/symptoms` | Symptom vocabulary | none | — |
| GET | `/api/v1/hazards` | Five hazards with related risks and sources | none | — |
| GET | `/api/v1/risks` | Risk definitions | none | — |
| GET | `/api/v1/risks/{risk_id}` | Risk detail | none | — |
| GET | `/api/v1/countermeasures` | Countermeasure references | none | — |
| GET | `/api/v1/sources` | Evidence sources with verification status | none | — |

## measurements

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/measurements/history` | Measurement history with pagination, filters and aggregation | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/measurements/latest` | Latest observation per metric | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/measurements/{observation_id}` | Observation detail with provenance and linked assessments | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/measurements` | Alias of /measurements/history | bearer | astronaut, medical_officer, flight_surgeon, admin |

## medical-events

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/medical-events` | Medical events | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/medical-events/{event_id}` | Medical event detail (timeline, protocol, checklist) | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/medical-events/{event_id}/transition` | Change medical event state (validated state machine) | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/medical-events/{event_id}/actions` | Record an action (checklist item, note, step) | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/medical-events/{event_id}/escalate` | Escalate: notify medical personnel and queue report to ground | bearer | astronaut, medical_officer, flight_surgeon |

## medical-protocols

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/medical-protocols` | Preloaded procedures (approval status shown) | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/medical-protocols/{protocol_id}` | Procedure detail | bearer | astronaut, medical_officer, flight_surgeon, admin |

## medical-reports

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| POST | `/api/v1/medical-events/{event_id}/reports` | Generate a structured medical report | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/medical-reports` | Medical reports | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/medical-reports/{report_id}` | Medical report detail | bearer | astronaut, medical_officer, flight_surgeon |

## mission

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/missions` | Missions | bearer | astronaut, medical_officer, flight_surgeon, admin |
| GET | `/api/v1/missions/{mission_id}` | Mission detail incl. phases | bearer | astronaut, medical_officer, flight_surgeon, admin |

## records

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| POST | `/api/v1/sleep` | Sleep assessment | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/sleep` | Sleep records | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/mood` | Private daily check-in (mood, stress, fatigue …) | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/mood` | Private check-ins (astronaut and flight surgeon only) | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/exercise` | Exercise record | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/exercise` | Exercise records and adherence | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/nutrition` | Nutrition / hydration record | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/nutrition` | Nutrition records with daily water totals | bearer | astronaut, medical_officer, flight_surgeon |
| POST | `/api/v1/medications` | Record medication given under an approved instruction | bearer | medical_officer, flight_surgeon |
| POST | `/api/v1/medical-history` | Add medical history entry | bearer | medical_officer, flight_surgeon |

## rules

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/rules` | Centralized rule configuration (all versions) | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/rules/{rule_id}/versions` | Create a new rule version (flight surgeon) | bearer | flight_surgeon |

## simulator

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/simulator` | Simulator status (SYNTHETIC data source) | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/simulator/start` | Start a scenario | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/simulator/pause` | Pause | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/simulator/resume` | Resume | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/simulator/stop` | Stop | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/simulator/speed` | Change speed | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/simulator/reset` | Stop and delete all simulator-generated records | bearer | astronaut, medical_officer, flight_surgeon, admin |

## sync

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/sync` | Synchronization queue and Earth-link status | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/sync/link` | Set Earth link status / delay (mission operations) | bearer | admin, medical_officer, flight_surgeon, astronaut |
| POST | `/api/v1/sync/run` | Run one synchronization pass now | bearer | astronaut, medical_officer, flight_surgeon, admin |
| POST | `/api/v1/sync/{queue_id}/retry` | Retry a failed or conflicted item | bearer | astronaut, medical_officer, flight_surgeon, admin |

## system

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/health` | Service health | none | — |

## views

| Method | Path | Summary | Auth | Roles |
|---|---|---|---|---|
| GET | `/api/v1/overview` | Mission overview for one astronaut | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/body-systems/{system}` | Body-system view: risks, hazards, measurements, symptoms, assessments | bearer | astronaut, medical_officer, flight_surgeon |
| GET | `/api/v1/routine` | Today's required assessments and completion history | bearer | astronaut, medical_officer, flight_surgeon |

## Telemetry example (synthetic)

```http
POST /api/v1/telemetry
X-Device-Key: <device key>
Idempotency-Key: batch-2026-11-14-0001
Content-Type: application/json

{
  "observations": [
    {
      "observation_id": "OBS-0001",
      "astronaut_id": "AST-001",
      "mission_id": "MSN-ARES-T1",
      "metric_code": "heart_rate",
      "value": 78,
      "unit": "bpm",
      "measured_at": "2026-11-14T10:30:00Z",
      "source_type": "wearable",
      "device_id": "DEV-HRW-001",
      "quality": "valid",
      "context": {
        "activity": "resting",
        "position": "seated"
      }
    }
  ]
}
```

Response: `processing_status` (complete | partial | rejected), `accepted[]` (accepted | duplicate), `rejected[]` with
per-item `errors`, `validation_errors`, `assessments[]`, `alerts_created[]`, `alerts_updated[]`.
