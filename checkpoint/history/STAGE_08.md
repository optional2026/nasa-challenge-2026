# Checkpoint — Stage 8: Real-time and offline functionality

1. **Current stage:** 8 — Real-time and offline functionality — COMPLETE
2. **Completed stages:** Stage 0, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6, Stage 7, Stage 8
3. **Implemented features:** WebSocket /ws with token auth and privacy-filtered fan-out; client reconnect with back-off and 10 s polling fallback; browser outbox with client submission IDs; server sync worker; Earth link controls.
4. **Files created:** backend/astra/{app,bus}.py; frontend/src/lib/{store.tsx,api.ts}
5. **Files modified:** later refinements tracked in git history
6. **Tests executed:** test_websocket_auth_and_privacy_filtering passed; sync tests passed.
7. **Tests passed/failed:** see item 6 (no failing tests at checkpoint time)
8. **Known bugs:** Browser WebSocket not testable in sandbox (no ws library) — documented.
9. **Outstanding requirements:** Browser outbox E2E test.
10. **Current architecture:** Starlette + Pydantic backend (backend/astra), SQLite (WAL) relational schema, simulator package, React+TypeScript frontend served from frontend/dist. See docs/ARCHITECTURE.md.
11. **Research integrated:** —
12. **Next exact tasks:** Security and QA (Stage 9).
13. **Resume instructions:** cd backend && pip install -r requirements-dev.txt && python -m pytest -q; python run.py; open http://127.0.0.1:8000. Read checkpoint/CURRENT.md first.
