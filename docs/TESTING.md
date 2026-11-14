# Testing

Last full run: 2026-11-14, build sandbox (Linux, Python 3.13.18, Starlette 1.7.0, Pydantic 2.13.5, Uvicorn 0.54.0,
Playwright 1.63 / Chromium).

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration + WebSocket (Starlette TestClient) | `cd backend && python -m pytest -q` | **46 passed** |
| Browser end-to-end (Playwright, live Uvicorn server) | `python run.py --reset-db` then `python -m pytest e2e -q` | **9 passed** |
| Frontend type-check (offline React type shims) | `npx tsc -p tsconfig.offline.json` | **0 errors** |
| Frontend production build (esbuild) | `node build.mjs` | **built** (`dist/assets/app.js` ≈ 320 kB, `app.css` ≈ 24 kB) |
| Scenario verification (all 8 scenarios, 10 simulated days, max speed) | ad-hoc script (see below) | expected findings produced, **0 rejected observations** |

## Backend tests (`backend/tests/`)

* `test_knowledge.py` (6) — five hazards and relations, all 12 risks have every required field and sources, the six
  challenge indicators, every source reference resolves, clinician rule inactive, procedures labelled synthetic.
* `test_ingestion.py` (14) — unit conversions, provenance preserved, °F→°C with original kept, eight rejection cases
  (unit, implausible value, future time, unknown metric/astronaut, missing timezone, wrong type, wrong astronaut for
  device), idempotency and conflict, batch `Idempotency-Key`, environment vs astronaut subject, device key checks,
  manual BP panel with symptoms, astronauts cannot submit for others, clinician-only indicators, pagination and
  aggregation, device adapters (shared device attribution, low signal quality kept as *questionable*), personal dosimeter.
* `test_assessment_response.py` (12) — seeded approved baselines, baseline versioning and medical-only approval,
  questionable quality → reassessment (not abnormal), sustained deviation → reassessment → medical review + event,
  state machine (invalid jumps, reason required, medical-only resolution, alert cannot close while event open,
  acknowledgement does not close event), urgent combined rule → checklist → escalation → report with all required
  sections → offline queue → delivered → acknowledged, idempotent re-queue, degraded link, CO₂ NASA rule creates
  environment event with source, missing data never shown as healthy, sleep schedule reference, exercise/nutrition
  validation, medication requires approved instruction and medical role.
* `test_security_privacy.py` (9) — login failures, crew isolation, admin without medical access, private check-in
  visibility (astronaut + flight surgeon only; CMO redacted; other crew nothing), audit log, no secrets in responses,
  OpenAPI coverage of every required endpoint, WebSocket authentication and privacy filtering.
* `test_simulator.py` (5) — eight scenarios defined; start/pause (clock frozen)/resume/speed/stop/reset; emergency
  scenario end to end through the API (URGENT alert, medical event, SYNTHETIC labels, environment data); radiation
  and behavioral scenarios produce their expected rules.

## End-to-end tests (`e2e/test_e2e.py`)

Login rejection · manual blood-pressure entry and server-side rejection of an implausible value · private check-in
and privacy across three roles · full emergency workflow in the browser (urgent overview → response center →
checklist → escalation → report queued offline → acknowledged after link restored → monitoring → resolved) · body
map selection changes content · analytics point click opens provenance drawer · radiation event on environment page
and rule library · administrator sees operations only · mobile layout. Screenshots: `docs/screenshots/`.

## Scenario outcomes (10 simulated days, seed 42)

| Scenario | Main findings |
|---|---|
| Nominal | No health findings (occasional *questionable quality → repeat* from synthetic motion artefacts; one scheduling note) |
| Cardiovascular | Sustained resting heart-rate deviation → medical review → medical event |
| Sleep and fatigue | Sustained short sleep with high fatigue → medical review → event |
| Possible illness | Temperature above baseline with symptoms → medical review → event (+ sustained temperature/HR reassessment) |
| Radiation event | Dose-rate spike → URGENT environmental alert + radiation environment event (peak ≈ 560 µGy/h, synthetic) |
| Musculoskeletal | Grip-strength decline → medical review + specialized assessment reminder |
| Behavioral | Private mood/stress trend → private medical review event; private note to medical |
| Emergency | URGENT combined HR/SpO₂/symptom alert with synthetic procedure, sustained HR/RR deviation, CO₂ habitat-limit alert |

## Not tested

* Live WebSocket delivery **in the browser**: the sandbox Uvicorn had no WebSocket library; the UI fell back to
  polling during E2E. WebSocket behaviour is covered by backend tests with the Starlette test client. On a normal
  install `uvicorn[standard]` provides WebSockets.
* `npm run dev` / `vite build` and `@types/react` type-checking (packages unavailable in the sandbox).
* Windows execution of `start-astra.bat` (written for Windows; not executed in the sandbox).
* Any physical medical device.
