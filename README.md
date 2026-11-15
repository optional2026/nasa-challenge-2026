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

> **New here?** Read the **[User Guide](USER_GUIDE.md)**: starting ASTRA, accounts, what each role does, the
> Earth-link demonstration and the public Cloudflare demo. A 7-slide version is in
> [presentation/ASTRA_User_Guide.pptx](presentation/ASTRA_User_Guide.pptx).

## Quick start (Windows)

Requirements: Python 3.10+ (python.org — tick "Add python.exe to PATH"). Node.js is **not** required to run ASTRA — the
built web interface is included in `frontend/dist`. It is only needed to rebuild the interface after changing
`frontend/src` (`cd frontend && npm install && npm run build`).

1. Double-click **`start-astra.bat`** (first run creates a virtual environment and installs 5 small packages).
2. Open **http://127.0.0.1:8000** in your browser.
3. Sign in with a **username and password** (every role, crew and Earth-side).

| Account | Role | Password (demo) | Sees / does |
|---|---|---|---|
| Elena Vega (`vega`) | Astronaut (Commander) | `optionalwillwin` | My dashboard, record a measurement, daily routine (sleep, mood/stress check-in, exercise, nutrition/hydration), health records, analytics and history, alerts & medical response — **own record only** |
| Amara Okafor (`okafor`) | Astronaut (Flight Engineer) | `optionalwillwin` | Same as above, own record only |
| Kenji Mori (`mori`) | Crew Medical Officer (aboard) | `optionalwillwin` | Everything an astronaut has for their own record, plus **Crew overview**, records of astronauts in the **same mission and crew** (other members' private check-ins redacted), crew alerts/medical events and response coordination |
| Mission Systems Administrator (`admin`) | Earth-based administrator | `astra-demo` | **No personal health pages.** Mission overview, Crew overview, **Astronaut records** (select any astronaut — read-only, privacy-filtered: summary, body systems & measurements, trends & history, logs & assessments), Alerts & medical events (read-only), Mission ops & sync, **Users & crew assignment** |
| Lucia Ramirez (`ramirez`) | Ground flight surgeon (Earth) | `astra-demo` | **No personal health pages.** Mission overview and Crew overview of the **assigned mission only**, Astronaut medical records (incl. private check-ins), Medical response & reports (escalations from the onboard CMO), medical operations (baselines, rules, audit) |

> ⚠ **Shared demonstration passwords.** `optionalwillwin` (the three pre-created crew accounts) and `astra-demo`
> (Earth-side demo accounts) are public demo passwords and **must be changed before any real deployment**:
> set `ASTRA_CREW_DEMO_PASSWORD` / `ASTRA_DEMO_PASSWORD` before the database is first created, and/or reset each crew
> account in *Users & crew assignment → Reset password*. Passwords are stored only as salted scrypt hashes; they are
> never sent to the browser, never returned by the API and cannot be retrieved by an administrator.

**Accounts and passwords**
* The administrator registers new astronaut / CMO accounts in *Users & crew assignment* and must set an initial
  password (server policy: 8–128 characters, at least 4 different characters, not the username, not a common password,
  no leading/trailing spaces). Nobody can self-register or change their own role.
* *Reset password* replaces a crew account's password (the old one is never shown). Earth-side account passwords are
  managed by server configuration.
* The flight surgeon's assigned mission is set by the administrator (*Edit* on the flight-surgeon row). A flight
  surgeon without an assigned mission can see no astronaut records. An administrator account without a mission
  assignment oversees all missions.
* Upgrading an existing database: on first start the three pre-created crew accounts are updated **in place** to the
  shared crew demo password and an unassigned flight surgeon is assigned to the demo mission (one-time migration,
  recorded in `schema_meta`; later starts never overwrite crew passwords). Crew accounts created earlier through
  user management had random, unknown passwords — reset them in *Users & crew assignment*.

**Crew overview** (CMO, administrator, flight surgeon): summary tiles (total, no concern, needs attention, needs
medical review, insufficient/no data, with active alerts; click to filter) and one card per astronaut. Crew members
open that astronaut's dashboard; Earth-side roles open *Astronaut records*.

**Demo data** (header button, crew members): generates synthetic data for **your own profile only**. Mission control can
generate for one selected astronaut — or, explicitly, the whole crew — in *Mission operations → Mission simulator*.

**Hardware Link**: *Daily routine → Record → Hardware link* shows a "Hardware Integration — Coming Soon" placeholder
(no device integration exists).

4. As a crew member, press **Demo data** in the header; or as the administrator go to **Mission operations → Mission
   simulator**, pick a scenario (e.g. *Emergency*) and press **Start**.

Manual start (any OS):

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # --reset-db to start from a fresh synthetic dataset
```

## Crew Side and Earth Side (offline synchronization)

ASTRA runs as **two deployments of the same codebase**. The **Crew Side** onboard server (astronauts and the CMO)
keeps working with no connection to Earth. The **Earth Side** server (administrators and ground flight surgeons)
receives astronaut records through a signed, acknowledged, idempotent store-and-forward synchronization API.
Double-click **`start-astra-crew-earth.bat`** (or run `./start-astra-crew-earth.sh`). This starts the onboard server
at http://127.0.0.1:8000 and the Earth server at http://127.0.0.1:8100, each with its own database. Sign in as
`mori` to use **Simulate Earth Connection Loss / Restore Earth Connection**. The architecture, demonstration script,
configuration and limitations are in **[docs/CREW_EARTH_SYNC.md](docs/CREW_EARTH_SYNC.md)**.
`start-astra.bat` still starts the earlier single-server prototype (all roles on one server).

**Public demo for judges:** **`start-public-astra.bat`** publishes both sides through two Cloudflare Quick Tunnels
and prints two `https://…trycloudflare.com` links. Stop with `stop-public-astra.bat`. See *Public demonstration*
in [docs/CREW_EARTH_SYNC.md](docs/CREW_EARTH_SYNC.md).

**Light and dark themes:** use the **Light / Dark / System** switch at the bottom of the sidebar (also top-right on
the sign-in page). The choice is remembered per browser. *System* follows the operating-system setting.

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
cd backend && pip install -r requirements-dev.txt && python -m pytest -q        # 75 tests
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
