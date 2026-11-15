# CURRENT CHECKPOINT (authoritative) — Stage 10: Hackathon demonstration

1. **Current stage:** 10 — Hackathon demonstration — COMPLETE
2. **Completed stages:** Stage 0, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6, Stage 7, Stage 8, Stage 9, Stage 10
3. **Implemented features:** Demo environment (start-astra.bat, run.py --reset-db), synthetic crew/mission, scenarios, screenshots, architecture/research/API/testing/decisions/compliance/security docs, demo script, presentation, known limitations.
4. **Files created:** README.md; start-astra.bat; run-tests.bat; docs/*; docs/screenshots/*; presentation/ASTRA_presentation.pptx; scripts/gen_api_docs.py
5. **Files modified:** later refinements tracked in git history
6. **Tests executed:** Final runs: backend 46 passed, E2E 9 passed, tsc 0 errors, build OK.
7. **Tests passed/failed:** see item 6 (no failing tests at checkpoint time)
8. **Known bugs:** None open.
9. **Outstanding requirements:** See DEVELOPMENT_STATUS known limitations.
10. **Current architecture:** Starlette + Pydantic backend (backend/astra), SQLite (WAL) relational schema, simulator package, React+TypeScript frontend served from frontend/dist. See docs/ARCHITECTURE.md.
11. **Research integrated:** See docs/RESEARCH.md.
12. **Next exact tasks:** Team review; optional: install on Windows, run start-astra.bat, rehearse docs/DEMO_SCRIPT.md.
13. **Resume instructions:** cd backend && pip install -r requirements-dev.txt && python -m pytest -q; python run.py; open http://127.0.0.1:8000. Read checkpoint/CURRENT.md first.

## Quick facts
* Project root: this folder. Backend `backend/`, frontend `frontend/` (prebuilt `frontend/dist/`), tests `backend/tests/` + `e2e/`.
* Demo logins (password for EVERY role): vega, okafor (astronauts), mori (CMO) — shared crew demo password
  `optionalwillwin`; admin and ramirez (flight surgeon) — `astra-demo`. Shared demo passwords: change before real use.
* 2026-11-15 (roles & login update):
  - Profile-selection sign-in for crew (`/auth/profiles`, `/auth/select-profile`); Earth-side accounts keep passwords.
  - Admin user management (`/users`, PATCH `/users/{id}`, `/deactivate`, `/activate`); crew assignment column
    `astronauts.crew` (only DB migration; additive, auto-applied in `db._migrate`).
  - Roles: astronaut (own), CMO (own + same mission/crew), admin (read-only, privacy-filtered health views; `VIEW_ROLES`
    in `api/routes_data.py`), flight surgeon retained (ground medical).
  - `/crew/overview` (CMO, admin, FS) with summary counts and categories derived from the existing assessment statuses.
  - Demo-data bug fixed: generator produces data for ONE astronaut (`ScenarioBuilder(crew_ids=...)`); crew members only
    for themselves; whole crew only with `whole_crew` (admin/FS); scoped reset.
  - Frontend: new Login, Crew overview, User management pages; role-based nav; "viewing records of" banner; read-only
    Medical Response/Routine for admin; Hardware Link placeholder tab in Daily routine → Record.
  - Tests: backend 64 passed (new: `test_roles_users.py`, `test_demo_isolation.py`); `tsc` 0 errors; `vite build` OK
    (`frontend/dist` rebuilt). E2E (Playwright) helper updated but not run.
* All stage reports: `checkpoint/history/STAGE_00.md` … `STAGE_10.md`. Status table: `docs/DEVELOPMENT_STATUS.md`.
* 2026-11-15 (role separation & password authentication):
  - Profile selection removed (`/auth/profiles`, `/auth/select-profile` deleted); all roles use `/auth/login`.
  - Crew demo password from `config.crew_demo_password()` (env `ASTRA_CREW_DEMO_PASSWORD`); one-time migration
    `seed.apply_demo_password` (schema_meta key `crew_password_auth_v1`) updates vega/okafor/mori in place.
  - New column `users.mission_id` (Earth accounts; `db._migrate`). Flight surgeon limited to the assigned mission
    (`Principal.scope_astronaut_ids`); admin unrestricted unless assigned. FS writes (ingestion/records/simulator) scoped too.
  - `POST /users` requires `password` (policy in `security.password_problems`); new `POST /users/{id}/password`
    (admin reset, crew accounts only); PATCH can set a flight surgeon's `mission_id`.
  - Frontend: password Login; Earth roles get Mission overview + Astronaut records (reuses Overview/BodySystems/
    Analytics/Routine) instead of personal tabs; Users page has password, reset, FS mission.
  - Tests: backend 75 passed (new `tests/test_role_separation.py`); tsc 0 errors; vite build OK. E2E updated, not run
    (Playwright not installed).
* 2026-11-15 (Crew Side / Earth Side + offline synchronization):
  - `ASTRA_DEPLOYMENT=onboard|earth|standalone` (default standalone = previous behaviour). `astra/sides.py`: login and
    route policy per side (crew roles onboard, Earth roles on Earth; Earth refuses health-record writes).
  - `services/replication.py`: SQLite triggers -> `replication_outbox` (PENDING/SENDING/SYNCED/FAILED/REJECTED/DISCARDED),
    `SyncWorker` thread, HMAC-signed `POST /api/v1/replication/batch` + `GET /replication/downlink`, Earth validation,
    idempotent storage (`replicated_records`), immutable vs revisioned records, ground annotations (Earth -> CMO).
  - CMO demo control `POST /link/simulation/outage|restore` (requires ASTRA_ALLOW_LINK_SIMULATION=1; persistent; audited).
  - New tables: replication_outbox, replication_state, replicated_records, replication_batches, ground_annotations.
    `db.new_id` now 80-bit ids.
  - `run.py --side onboard|earth`, `start-astra-crew-earth.bat/.sh`, docs/CREW_EARTH_SYNC.md.
  - Frontend: side-aware login/header, `components/EarthLink.tsx` (CMO panel, unsynced list, Earth freshness, ground
    notes), PWA (public/sw.js shell cache, manifest).
  - Tests: new `tests/test_crew_earth_sync.py` (15, two real server processes). See final report for full-suite result.
  - Final: backend 91 tests (90 full-suite pass + new large-batch test pass); tsc 0 errors; vite build OK.
* 2026-11-15 (visual redesign + public two-side demo):
  - Light blue / white / charcoal / purple design with Light, Dark and System themes (`src/lib/theme.ts`,
    `components/ThemeSwitch.tsx`, `public/theme-init.js` applies the theme before first paint). All colours are tokens
    in `styles.css`; chart series use `--series-*`. Backup of the old styling: `backups/pre-color-redesign/`.
  - `start-public-astra.bat` / `stop-public-astra.bat` -> `tools/start_public_crew_earth.ps1`: both sides behind two
    Cloudflare Quick Tunnels (ports 8020/8120, backend/data-public/*). `-NoTunnel` for a local dry run.
  - Fix: the signed replication endpoint is exempt from the 512 KB user body limit (own 20 MB limit).
