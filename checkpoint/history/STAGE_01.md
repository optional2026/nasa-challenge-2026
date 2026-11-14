# Checkpoint — Stage 1: Scientific knowledge foundation

1. **Current stage:** 1 — Scientific knowledge foundation — COMPLETE
2. **Completed stages:** Stage 0, Stage 1
3. **Implemented features:** Five hazards, 12 risks (all required fields), many-to-many risk–hazard relationships with rationale, 42 health indicators with measurement instructions and limitations, 25 symptoms, 13 countermeasures, 21 evidence sources with verification status, 17 versioned rules in three classes, 7 synthetic procedures; idempotent loader and query service.
4. **Files created:** backend/astra/knowledge/data/{sources,hazards,risks,indicators,symptoms,countermeasures,protocols,rules}.json; backend/astra/services/knowledge.py
5. **Files modified:** later refinements tracked in git history
6. **Tests executed:** Seeding smoke test (twice, idempotent) — counts 21/5/12/42/13/7/17/25; all risk-indicator links resolve. Later covered by tests/test_knowledge.py (6 passed).
7. **Tests passed/failed:** see item 6 (no failing tests at checkpoint time)
8. **Known bugs:** None
9. **Outstanding requirements:** Frontend pages (by design not in this stage).
10. **Current architecture:** Starlette + Pydantic backend (backend/astra), SQLite (WAL) relational schema, simulator package, React+TypeScript frontend served from frontend/dist. See docs/ARCHITECTURE.md.
11. **Research integrated:** NASA-STD-3001 V1 Rev C ([V1 6001] 8.5 h sleep period rationale, [V1 6002], [V1 3004], [V1 4029], [V1 4030]); OCHMO-TB-004 ([V2 6004] 3 mmHg CO2), TB-016, TB-020, TB-041; NTRS 20230015521, 20190001026, 20230017691, 20150019624, 20250001454; PMC10919966.
12. **Next exact tasks:** Schema and ingestion (Stage 2).
13. **Resume instructions:** cd backend && pip install -r requirements-dev.txt && python -m pytest -q; python run.py; open http://127.0.0.1:8000. Read checkpoint/CURRENT.md first.
