# Security and privacy

| Control | Implementation | Level |
|---|---|---|
| Authentication | Username/password; passwords hashed with scrypt (n=2¹⁴, per-user salt); HS256-signed session tokens with 12 h expiry; failed and successful logins audited | Prototype (no lockout, no MFA, no password policy, shared demo password) |
| Token secret | `ASTRA_SECRET_KEY` env var or a random key generated into `backend/data/.secret_key`; never in frontend code | Prototype-appropriate; production needs managed secrets and rotation |
| Device authentication | Per-device API key (`X-Device-Key`), stored only as SHA-256 hash; device can only submit for its mission/assigned astronaut and its declared metrics | Prototype; production would use mutual TLS / device certificates |
| Role-based authorization | Roles astronaut, medical_officer, flight_surgeon, admin enforced on every route (`roles=` in the route registry) and in services | Implemented and tested |
| Data scoping | Astronauts see only their own health data; admin has no medical data access | Implemented and tested |
| Behavioral privacy | Mood/stress/fatigue/workload/connectedness/reaction-time observations, check-ins and behavioral alerts/events are private: visible to the astronaut and the flight surgeon; the CMO sees a redacted placeholder; WebSocket events filtered the same way; reading check-ins is audited | Implemented and tested |
| Audit history | Append-only `audit_log` for logins, ingestion batches, baseline changes, rule versions, alert/event actions, report reads, sync, simulator | Implemented; production would add tamper-evidence (hash chain) |
| Input validation | Pydantic schemas (`extra=forbid`), per-observation validation, unit and range checks, timezone-aware timestamps, size limits | Implemented and tested |
| Transport | HTTP in the prototype | **Production must use TLS** (reverse proxy) |
| Storage | SQLite file on the onboard server | **Not encrypted at rest** in the prototype |
| Medical data minimisation in sync | Only reports explicitly generated/escalated are queued for ground | Implemented |

Never commit `backend/data/` (database, secret key, device keys) — it is in `.gitignore`.
