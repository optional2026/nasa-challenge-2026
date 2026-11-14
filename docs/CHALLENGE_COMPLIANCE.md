# Challenge compliance — NASA Space Apps 2026: Health Monitoring Software for Astronauts on Space Missions

Status legend: **IMPLEMENTED AND TESTED** · IMPLEMENTED BUT UNTESTED · PARTIALLY IMPLEMENTED · PLANNED · BLOCKED

## Official requirements

| Requirement | How ASTRA meets it | Status |
|---|---|---|
| Address the five hazards (radiation, isolation/confinement, distance, gravity fields, hostile/closed environments) | 5 hazard definitions with sources; 12 risks with many-to-many hazard relationships and rationale; body-system view shows hazards per system; library page | IMPLEMENTED AND TESTED |
| Show how hazards contribute to health risks | Risk ↔ hazard rationale; risk ↔ indicator ↔ countermeasure links; limitations per risk | IMPLEMENTED AND TESTED |
| Blood pressure | Manual panel (systolic + diastolic), BP monitor adapter, baseline comparison | IMPLEMENTED AND TESTED |
| Heart rate | Manual, wearable telemetry (context: resting/exercise/sleep), resting baseline | IMPLEMENTED AND TESTED |
| Blood glucose | mg/dL and mmol/L, clinician-directed per astronaut (toggle by medical role) | IMPLEMENTED AND TESTED |
| Body temperature | °C/°F with conversion, original preserved, method recorded | IMPLEMENTED AND TESTED |
| Sleep duration | Start/end with computed duration and interruption correction, quality, awakenings, scheduled opportunity | IMPLEMENTED AND TESTED |
| Mood | Private five-level check-in with skippable questions, stress, fatigue, workload, connectedness, note to medical | IMPLEMENTED AND TESTED |
| Help astronauts evaluate and respond to changes | Individual baselines, trend analysis, explainable assessments, four alert categories, medical events, preloaded (synthetic) procedures, escalation, reports | IMPLEMENTED AND TESTED |
| Remain useful when communication with Earth is delayed/unavailable | Fully onboard; store-and-forward queue with link status and delay; browser outbox | IMPLEMENTED AND TESTED (server); browser outbox IMPLEMENTED BUT UNTESTED in E2E |

## Specification parts I–XIII (summary)

| Part | Status | Notes |
|---|---|---|
| I Product definition (monitor/analyze/respond/coordinate) | IMPLEMENTED AND TESTED | |
| II Scientific model: 12 risks with all required fields; hazard relationships | IMPLEMENTED AND TESTED | `risks.json`, `hazards.json` |
| III Data collection: 4 input methods, manual forms for every listed indicator, device adapters (7), unified format, telemetry API and listed endpoints | IMPLEMENTED AND TESTED | Physical devices: none (by design, no claims) |
| IV Baselines, trend analysis, assessment engine, multi-indicator analysis (A–F), centralized rules with 3 classes | IMPLEMENTED AND TESTED | Clinician class mechanism present but intentionally unconfigured |
| V Alerts (4 categories, all fields), medical event state machine with audit, Medical Response Center, medical reports and communication | IMPLEMENTED AND TESTED | Procedures are synthetic and labelled |
| VI Environment module (radiation dose/rate, CO₂, temperature, humidity, air quality, O₂, phase, elapsed time, events, overlay) | IMPLEMENTED AND TESTED | |
| VII UI: 7 required pages (+ Mission operations), color semantics, missing ≠ healthy, interactive body map | IMPLEMENTED AND TESTED | Charts are custom SVG instead of Recharts (D-004) |
| VIII Simulator: 8 scenarios, start/pause/resume/stop/reset/speed/MET/device status, SYNTHETIC labels, same API | IMPLEMENTED AND TESTED | |
| IX Relational models and REST organisation, pagination/filtering, Pydantic, OpenAPI, WebSockets | IMPLEMENTED AND TESTED | Starlette instead of FastAPI, sqlite3 instead of SQLAlchemy (D-001/D-002) |
| X Offline-first and security | IMPLEMENTED AND TESTED (prototype-level controls documented in SECURITY.md) | TLS/encryption at rest: PLANNED |
| XI Stages 0–10 | Completed in order; see `checkpoint/history/` | |
| XII Checkpoints and documents | Present | |
| XIII Constraints 1–18 | Respected — see RESEARCH.md "Things ASTRA deliberately does not claim" | |

## Engineering constraints checklist

1 preserve working code — folder was empty · 2 no rewrite — n/a · 3 no fake hardware — all devices "Simulated — not
validated" · 4 simulated data labelled — SYNTHETIC on every record/tile/chart drawer · 5–6 no invented research or
references — verified sources with status · 7 no invented thresholds — rule classes · 8 no emergency treatments ·
9 missing ≠ healthy — grey "missing/stale/not enough data" · 10 exercise ≠ bone density · 11 mood ≠ diagnosis ·
12 correlation ≠ causation — overlay disclaimer · 13 no external AI APIs · 14 no dead buttons (E2E-exercised) ·
15 UI connected to backend · 16 no device-compatibility claims · 17 end-to-end flows tested · 18 plain-language UI.
