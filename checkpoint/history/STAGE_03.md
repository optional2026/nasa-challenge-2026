# Checkpoint — Stage 3: Individual baselines and assessment engine

1. **Current stage:** 3 — Individual baselines and assessment engine — COMPLETE
2. **Completed stages:** Stage 0, Stage 1, Stage 2, Stage 3
3. **Implemented features:** Versioned baselines per astronaut × indicator × context (draft/approved/retired, medical approval, reference ranges); trend analysis; assessment engine with 17 evaluation methods driven by rules.json; multi-indicator rules (cardiorespiratory, temperature+symptoms, sleep+fatigue, mood+stress, exercise/performance, hydration, environment); missing-data findings; explainable stored assessments.
4. **Files created:** backend/astra/services/{baselines,trends,assessment_engine}.py
5. **Files modified:** later refinements tracked in git history
6. **Tests executed:** tests/test_assessment_response.py baseline/assessment tests passed.
7. **Tests passed/failed:** see item 6 (no failing tests at checkpoint time)
8. **Known bugs:** Fixed: SD floor too large for temperature.
9. **Outstanding requirements:** —
10. **Current architecture:** Starlette + Pydantic backend (backend/astra), SQLite (WAL) relational schema, simulator package, React+TypeScript frontend served from frontend/dist. See docs/ARCHITECTURE.md.
11. **Research integrated:** Baseline-relative rules marked DEMONSTRATION_ONLY; NASA references used only for their stated purpose.
12. **Next exact tasks:** Medical response (Stage 4).
13. **Resume instructions:** cd backend && pip install -r requirements-dev.txt && python -m pytest -q; python run.py; open http://127.0.0.1:8000. Read checkpoint/CURRENT.md first.
