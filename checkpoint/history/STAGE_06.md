# Checkpoint — Stage 6: Environmental monitoring

1. **Current stage:** 6 — Environmental monitoring — COMPLETE
2. **Completed stages:** Stage 0, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6
3. **Implemented features:** Cabin CO2/O2/temperature/humidity/TVOC/PM2.5, area and personal radiation dose rate and cumulative dose, environment events (open/peak/close), radiation summary per dosimeter, medical/environment overlay with no-causation disclaimer, mission phases.
4. **Files created:** backend/astra/services/environment.py; backend/astra/api/routes_ops.py
5. **Files modified:** later refinements tracked in git history
6. **Tests executed:** test_co2_rule_creates_environment_event, radiation scenario test — passed.
7. **Tests passed/failed:** see item 6 (no failing tests at checkpoint time)
8. **Known bugs:** —
9. **Outstanding requirements:** —
10. **Current architecture:** Starlette + Pydantic backend (backend/astra), SQLite (WAL) relational schema, simulator package, React+TypeScript frontend served from frontend/dist. See docs/ARCHITECTURE.md.
11. **Research integrated:** OCHMO-TB-004, TB-020, HRP radiation page.
12. **Next exact tasks:** Frontend (Stage 7).
13. **Resume instructions:** cd backend && pip install -r requirements-dev.txt && python -m pytest -q; python run.py; open http://127.0.0.1:8000. Read checkpoint/CURRENT.md first.
