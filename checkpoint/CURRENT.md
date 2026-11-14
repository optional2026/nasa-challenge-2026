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
* Demo logins: crew profiles vega, okafor (astronauts), mori (CMO) — select profile, no password (simulation only);
  Earth-side admin and ramirez (flight surgeon) — password `astra-demo`.
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
