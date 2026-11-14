# ASTRA — Astronaut Self-assessment, Tracking and Response Assistant

**NASA Space Apps Challenge 2026 · Health Monitoring Software for Astronauts on Space Missions**

ASTRA is an offline-first health-monitoring and medical decision-support prototype for long-duration missions
(space stations, lunar bases, Mars transit and surface habitats). It **monitors** health and environment
measurements, **analyzes** them against each astronaut's own approved baseline, **responds** with explainable
findings and preloaded procedures, and **coordinates** medical records and store-and-forward communication with
ground flight surgeons.

> ASTRA is a decision-support prototype, **not an autonomous doctor** and not a diagnostic device. All crew data in
> the demo is **SYNTHETIC**. Rules labelled *Demonstration only* are synthetic statistical rules, not clinical
> thresholds. Procedures labelled *Synthetic demo* contain no treatment instructions.

## Quick start (Windows)

Requirements: Python 3.10+ (python.org — tick "Add python.exe to PATH"). Node.js is **not** required — the built web
interface is included in `frontend/dist`.

1. Double-click **`start-astra.bat`** (first run creates a virtual environment and installs 5 small packages).
2. Open **http://127.0.0.1:8000** in your browser.
3. Sign in with a demo account (password `astra-demo` for all):

| User | Role | Sees |
|---|---|---|
| `vega` | Astronaut (Commander) | Her own data only |
| `okafor` | Astronaut (Flight Engineer) | Her own data only |
| `mori` | Crew Medical Officer | All crew health data; private check-ins redacted |
| `ramirez` | Ground flight surgeon | All crew data including private check-ins |
| `admin` | Systems administrator | Devices, sync, simulator, audit — no medical data |

4. Go to **Mission operations → Mission simulator**, pick a scenario (e.g. *Emergency*) and press **Start**.

Manual start (any OS):

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # --reset-db to start from a fresh synthetic dataset
```

## What is in the box

| Area | Where |
|---|---|
| Scientific knowledge base (5 hazards, 12 risks, 42 indicators, 13 countermeasures, 21 sources, 17 rules, 7 synthetic procedures) | `backend/astra/knowledge/data/*.json` |
| Relational schema (44 tables, foreign keys, indexes) | `backend/astra/schema.sql` |
| Unified ingestion pipeline (manual, device, wearable, environmental) | `backend/astra/services/ingestion.py` |
| Assessment engine | `backend/astra/services/assessment_engine.py` |
| Medical events (state machine), alerts, reports, sync | `backend/astra/services/` |
| Device adapters (hardware-independent) | `backend/astra/devices/adapters.py` |
| Simulator (8 scenarios) | `backend/simulator/source.py`, `scenarios.py` |
| REST API (74 paths) + WebSocket | `backend/astra/api/`, `backend/astra/app.py` — docs at `/api/docs` |
| Web interface (React + TypeScript, 8 pages) | `frontend/src/` (prebuilt in `frontend/dist/`) |
| Tests: 46 backend + 9 browser end-to-end | `backend/tests/`, `e2e/` |
| Documentation, checkpoints, presentation | `docs/`, `checkpoint/`, `presentation/` |

## Developing the frontend

```bash
cd frontend
npm install
npm run dev        # Vite dev server on :5173, proxies /api and /ws to the backend on :8000
npm run build      # production bundle into frontend/dist (served by the backend)
```

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest -q        # 46 tests
python run.py --reset-db                                                       # then, in a second terminal:
playwright install chromium && python -m pytest ../e2e -q                      # 9 browser tests
```

## Key documents

`docs/CHALLENGE_COMPLIANCE.md` · `docs/ARCHITECTURE.md` · `docs/RESEARCH.md` · `docs/API.md` · `docs/TESTING.md` ·
`docs/SECURITY.md` · `docs/DECISIONS.md` · `docs/DEVELOPMENT_STATUS.md` · `docs/DEMO_SCRIPT.md` ·
`checkpoint/CURRENT.md`
