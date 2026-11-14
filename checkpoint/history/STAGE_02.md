# Checkpoint — Stage 2: Data models and ingestion

1. **Current stage:** 2 — Data models and ingestion — COMPLETE
2. **Completed stages:** Stage 0, Stage 1, Stage 2
3. **Implemented features:** 44-table schema; mission/astronaut/user/device models; unified observation format; POST /telemetry (per-item validation, idempotency by observation_id and Idempotency-Key), POST /measurements/manual (panels + symptoms), history/latest with pagination, filters and aggregation; units with explicit conversion and original preserved; quality and provenance; device adapters (7).
4. **Files created:** backend/astra/{schema.sql,db.py,units.py,schemas.py,security.py,audit.py,bus.py,seed.py}; backend/astra/services/{ingestion,records}.py; backend/astra/devices/adapters.py; backend/astra/api/*
5. **Files modified:** later refinements tracked in git history
6. **Tests executed:** tests/test_ingestion.py — 14 passed.
7. **Tests passed/failed:** see item 6 (no failing tests at checkpoint time)
8. **Known bugs:** Fixed: performance-test units, symptom provenance.
9. **Outstanding requirements:** —
10. **Current architecture:** Starlette + Pydantic backend (backend/astra), SQLite (WAL) relational schema, simulator package, React+TypeScript frontend served from frontend/dist. See docs/ARCHITECTURE.md.
11. **Research integrated:** Measurement methods/limitations from the knowledge base used in validation messages.
12. **Next exact tasks:** Baselines and assessment (Stage 3).
13. **Resume instructions:** cd backend && pip install -r requirements-dev.txt && python -m pytest -q; python run.py; open http://127.0.0.1:8000. Read checkpoint/CURRENT.md first.
