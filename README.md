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

Requirements: Python 3.10+ (python.org — tick "Add python.exe to PATH"). Node.js is **not** required to run ASTRA — the
built web interface is included in `frontend/dist`. It is only needed to rebuild the interface after changing
`frontend/src` (`cd frontend && npm install && npm run build`).

1. Double-click **`start-astra.bat`** (first run creates a virtual environment and installs 5 small packages).
2. Open **http://127.0.0.1:8000** in your browser.
3. **Crew:** click a profile card to enter — no password. **Mission Control (Earth):** pick the account and enter the
   password (`astra-demo` locally).

| Account | Role | Sign-in | Sees / does |
|---|---|---|---|
| Elena Vega (`vega`) | Astronaut (Commander) | Profile selection | Own dashboard, measurements, routine, history, analytics, alerts, demo data (own profile) |
| Amara Okafor (`okafor`) | Astronaut (Flight Engineer) | Profile selection | Own data only |
| Kenji Mori (`mori`) | Crew Medical Officer | Profile selection | Everything an astronaut has for self, plus **Crew overview**, full records of astronauts in the same crew (private check-ins redacted) and the Medical Response Center |
| Mission Systems Administrator (`admin`) | Earth-based administrator | Password | **Crew overview**, **User management** (register/edit/assign/deactivate crew accounts), **read-only** health records of every astronaut (privacy-filtered, no clinical actions), mission operations, audit |
| Lucia Ramirez (`ramirez`) | Ground flight surgeon (pre-existing) | Password | Whole mission incl. private check-ins; approves baselines and rules |

**Crew overview** (CMO, administrator): summary tiles (total, no concern, needs attention, needs medical review,
insufficient/no data, with active alerts; click to filter) and one card per astronaut. Click a name or *Open dashboard* to
open that astronaut's own dashboard/records; a banner shows whose records you are viewing.

**Demo data** (header button, crew members): generates synthetic data for **your own profile only**. Mission control can
generate for one selected astronaut — or, explicitly, the whole crew — in *Mission operations → Mission simulator*.

**Hardware Link**: *Daily routine → Record → Hardware link* shows a "Hardware Integration — Coming Soon" placeholder
(no device integration exists).

> ⚠ Crew profile selection is a **simulation-only** sign-in without credentials. It does not verify identity and is
> not suitable for an operational medical system. Permissions are still enforced by the server. See `docs/SECURITY.md`.

4. As a crew member, press **Demo data** in the header; or as the administrator go to **Mission operations → Mission
   simulator**, pick a scenario (e.g. *Emergency*) and press **Start**.

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

## Demo for judges

* **Demo data** button (top bar): generate random normal crew history or a chosen situation (fatigue, cardiovascular
  change, illness, radiation event, musculoskeletal, behavioral, emergency) for a chosen astronaut.
* **Public link:** `tools\start_public_demo.bat` starts ASTRA in public-demo mode behind a Cloudflare Quick Tunnel,
  prints the URL and a fresh password, and self-tests the link (API + WebSocket). Stop with `tools\stop_public_demo.bat`.
  Details: `docs/PUBLIC_DEMO.md`.

## Key documents

**Start here:** `docs/USER_GUIDE.md` (how ASTRA works and how to use it) · `docs/PUBLIC_DEMO.md` · `docs/REAL_DATA_INPUT.md`


`docs/CHALLENGE_COMPLIANCE.md` · `docs/ARCHITECTURE.md` · `docs/RESEARCH.md` · `docs/API.md` · `docs/TESTING.md` ·
`docs/SECURITY.md` · `docs/DECISIONS.md` · `docs/DEVELOPMENT_STATUS.md` · `docs/DEMO_SCRIPT.md` ·
`checkpoint/CURRENT.md`
