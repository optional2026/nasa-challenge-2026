# ASTRA Architecture

## 1. Context

ASTRA runs **onboard** (spacecraft, station, lunar or Mars habitat) on a local server. Crew devices (tablets,
laptops) use the web interface over the habitat network. Nothing in the basic operation depends on internet access,
cloud AI services or the Earth link. Communication with ground medical teams is store-and-forward.

```
 Crew tablets / laptops (browser)                 Ground segment (flight surgeons)
        │  HTTPS (prod) / HTTP (proto)                      ▲
        │  WebSocket /ws                                   │ store-and-forward (sync queue)
        ▼                                                  │  SIMULATED in prototype
 ┌───────────────────────── ASTRA onboard server (Python) ──────────────────────────┐
 │ Starlette app ─ REST /api/v1 (74 paths, OpenAPI 3.1) ─ WebSocket /ws ─ static UI │
 │   │                                                                              │
 │   ├─ security.py        auth (scrypt, signed tokens), roles, privacy rules       │
 │   ├─ services/ingestion  ← manual forms, devices, wearables, env sensors, sim    │
 │   ├─ services/assessment_engine → alerts → medical_events → reports → sync       │
 │   ├─ services/baselines, trends, environment, records, knowledge                 │
 │   ├─ devices/adapters    device-native payload → unified observation             │
 │   ├─ bus.py              in-process event bus → WebSocket fan-out (privacy-aware)│
 │   └─ SyncWorker thread   retries queue items when the Earth link allows          │
 │ SQLite (WAL) — 44 relational tables, FK + indexes, audit log                     │
 └──────────────────────────────────────────────────────────────────────────────────┘
        ▲ POST /api/v1/telemetry (X-Device-Key)          ▲ same handler functions
 Physical devices via adapters (future)            Simulator (8 scenarios, SYNTHETIC)
```

## 2. Data flow for one measurement

1. **Entry** — manual form (`POST /measurements/manual`, `/sleep`, `/mood`, `/exercise`, `/nutrition`), device
   (`POST /telemetry` or `/devices/{id}/readings` through an adapter) or simulator.
2. **Validation** (per item): schema (Pydantic) → metric exists → subject (astronaut vs environment) → astronaut and
   mission identity → device registration and supported metrics → role authorization → timestamp (timezone required,
   not in the future, not older than 2 years) → unit (explicit; unsupported units rejected) → value type and
   plausible input range (input validation only) → idempotency (same `observation_id` + same content = duplicate;
   different content = conflict).
3. **Storage** with provenance: original value and unit, canonical value and unit, measured/received timestamps
   (UTC), source type, device, quality, context, who entered it, SYNTHETIC flag, privacy flag.
4. **Assessment** (`assessment_engine.assess`) for the affected astronaut (or the cabin): active versioned rules
   from `assessment_rules` are evaluated against the approved baselines; findings, limitations, baseline comparisons,
   evidence observation IDs, risk IDs, rule versions and the recommended next step are stored as a `health_assessment`.
5. **Alerts** are created or updated (de-duplicated per rule and indicator). Rules can open a **medical event**
   (state machine) and attach a preloaded procedure. Environmental rules open **environment events**.
6. **Real-time** events are published to WebSocket subscribers (privacy-filtered).

## 3. Main components

| Component | Responsibility |
|---|---|
| `knowledge/data/*.json` | Single source of truth for hazards, risks, indicators, countermeasures, symptoms, procedures, rules and sources. Loaded idempotently into the DB at start-up. |
| `services/baselines.py` | Versioned baselines per astronaut × indicator × context (e.g. resting heart rate, grip-strength test, daily water total). Draft → approved (medical role) → retired. Only `valid` observations are used. |
| `services/trends.py` | Baseline z-scores, recent vs earlier means, slope, consecutive deviations, rapid changes, gaps, bucketing for charts. |
| `services/assessment_engine.py` | 17 evaluation methods dispatched by rule configuration (see `rules.json`). No thresholds in code. |
| `services/medical_events.py` | DETECTED → VERIFYING → ACTIVE → ESCALATED → MONITORING → RESOLVED with validated transitions, required reasons, medical-only resolution, full transition history. |
| `services/reports.py` | Structured medical report (astronaut, mission, event, symptoms, measurements, baseline comparisons, findings, actions, outstanding questions, status, supporting records) + plain-text rendering. |
| `services/sync.py` | Outgoing queue with idempotency keys, priority, exponential back-off, conflict detection, link status and light-time delay; simulated ground station. |
| `services/environment.py` | Cabin readings, radiation summary per dosimeter, environment events, medical/environment overlay with causation disclaimer. |
| `devices/adapters.py` | 7 adapters (HR wearable, BP monitor, pulse oximeter, thermometer, glucose meter, environmental sensor, dosimeter). |
| `simulator/` | Deterministic scenario builder + runner (start/pause/resume/stop/reset/speed) + HTTP CLI. |
| `frontend/` | React 19 + TypeScript. 8 pages, SVG charts, interactive body map, WebSocket client with reconnect, 10 s polling fallback, offline outbox for manual entries. |

## 4. Database (SQLite, `schema.sql`)

Knowledge: `evidence_sources`, `hazard_definitions`, `hazard_sources`, `risk_definitions`, `risk_hazard_relationships`,
`risk_sources`, `health_indicators`, `risk_indicators`, `countermeasures`, `risk_countermeasures`,
`countermeasure_sources`, `symptom_vocabulary`, `medical_protocols`, `assessment_rules`.
Mission and people: `missions`, `mission_environments`, `astronauts`, `users`, `devices`, `assessment_schedule`.
Data: `observations`, `sleep_records`, `mood_assessments`, `exercise_records`, `nutrition_records`,
`medication_records`, `medical_history`.
Analysis and response: `health_baselines`, `baseline_observations`, `health_assessments`, `assessment_observations`,
`alerts`, `alert_observations`, `medical_events`, `medical_event_transitions`, `medical_event_actions`,
`medical_reports`, `environment_events`, `environment_event_observations`.
Operations: `audit_log`, `sync_queue`, `ground_inbox` (simulated ground), `telemetry_batches` (idempotency).

JSON columns hold extensible metadata only (context, params); every relationship is a foreign key or link table.

## 5. Offline behaviour

* Onboard server: all knowledge, assessment, alerting and procedures are local. Earth link status (`online`,
  `degraded`, `offline`) and one-way delay are mission settings; the sync worker retries with back-off.
* Browser: if the onboard server is unreachable, manual entries are kept in a local outbox (browser storage) with a
  client submission ID and re-sent on reconnection; the server de-duplicates by that ID.
* WebSocket reconnects with exponential back-off; while disconnected, live views poll every 10 s.

## 6. Extending

* **New device**: implement a `DeviceAdapter` subclass (`to_observations`) and register a device row with its key.
* **New rule**: add an entry to `rules.json` (or create a new version via `POST /rules/{id}/versions`); add an
  evaluator only for a new *evaluation method*.
* **Clinical ranges**: approve a baseline with `ref_low/ref_high`, then activate `CLIN-REFERENCE-RANGE` with a
  clinician-approved version.
