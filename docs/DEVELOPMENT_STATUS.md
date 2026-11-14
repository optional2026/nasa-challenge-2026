# Development status

Updated 2026-11-14 after Stage 10. Legend: **IT** implemented and tested · **IU** implemented but untested ·
**PI** partially implemented · **PL** planned · **BL** blocked.

| Stage | Scope | Status |
|---|---|---|
| 0 | Repository inspection, audit, architecture, checkpoint | IT (folder was empty) |
| 1 | Scientific knowledge base (hazards, risks, relationships, indicators, methods, limitations, countermeasures, sources, evidence/approval status) | IT |
| 2 | Schema, astronaut/mission/device models, observation model, manual + telemetry APIs, validation, units, provenance, duplicates, quality, history | IT |
| 3 | Baselines, historical/trend analysis, rule management, multi-indicator assessment, explanations, missing data, medical review | IT |
| 4 | Alerts, event lifecycle, verification, procedure retrieval, escalation, history, reports, audit | IT |
| 5 | Simulator — 8 scenarios through the real API, controls | IT |
| 6 | Environmental telemetry, radiation history, cabin conditions, exposure events | IT |
| 7 | Frontend — 7 required pages + operations page, connected to the backend | IT (E2E) |
| 8 | WebSockets, local persistence, offline mode, sync, queued reports, retry, duplicate prevention | IT server-side; browser WebSocket IU (see TESTING) ; browser outbox IU |
| 9 | Authentication, authorization, privacy, audit, validation, backend/frontend/integration/E2E tests | IT |
| 10 | Demo environment, sample profiles, scenarios, screenshots, docs, references, compliance, script, presentation, limitations | IT |

## Known limitations

1. **No clinical validation.** Deviation rules are DEMONSTRATION_ONLY; the clinician rule mechanism ships inactive.
2. **Procedures are synthetic** placeholders that reference mission checklists; no treatment content.
3. **No physical devices tested.** Adapters define reference payloads only.
4. **Ground segment simulated** in-process; no real network transport to Earth.
5. **Prototype security**: HTTP (TLS required in production), SQLite not encrypted at rest, demo passwords, no MFA.
6. **Recharts and FastAPI/SQLAlchemy/Vite replaced** by tested equivalents because they could not be installed in
   the build environment (DECISIONS D-001…D-004).
7. **Browser WebSocket path** not exercised in E2E (sandbox Uvicorn lacked a WebSocket library); UI falls back to
   10 s polling.
8. Single mission and a single onboard node; no multi-node replication or schema migrations tool.
9. Baselines from the synthetic pre-mission window only (14 days); in-flight re-baselining is available to medical
   roles but its scientific suitability is a clinical decision.
10. Simulator timelines end at "now"; the 8.5 h sleep reference is applied only to the scheduled sleep opportunity.

## Bugs

None open from the final test runs. Fixed during development: chronological delivery in the simulator (cause before
effect), SD floor too large for temperature, symptom provenance inheriting device IDs, FK errors on simulator reset,
duplicate rapid-change alerts, legend overlap on charts.
