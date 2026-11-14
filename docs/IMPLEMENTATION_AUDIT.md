# ASTRA — Stage 0 Implementation Audit

Audit date: 2026-11-14 (UTC+05:00 local)

## 1. Existing repository inspection

| Item | Finding |
|---|---|
| Target folder | `C:\Users\LAPTOP\Documents\nasa` (connected through the Claude desktop bridge) |
| Contents at audit time | **Empty** — no files, no sub-folders, no Git history |
| Backend | None present |
| Frontend | None present |
| Database | None present |
| Telemetry implementation | None present |
| Baseline / alert logic | None present |
| Tests | None present — nothing to run |

Conclusion: there is no existing working code to preserve. ASTRA is implemented from scratch,
following the specification stage order (0 → 10).

## 2. Build environment inspection

The build/test machine is an isolated Linux workspace. Its network allow-list blocks package
registries for this account (`pip download fastapi` and `npm view vite` both fail), so only
pre-installed packages can be used **and tested**.

| Needed by spec | Available for testing? | Decision |
|---|---|---|
| Python 3 | Yes (3.13) | Used |
| FastAPI | **No** | Use **Starlette** (FastAPI's own foundation) + **Pydantic v2** + a small in-house router that validates with Pydantic and **generates OpenAPI 3.1** (see DECISIONS D-001) |
| SQLAlchemy | **No** | Use Python's built-in **sqlite3** with an explicit relational DDL (foreign keys, indexes) (D-002) |
| Uvicorn | Yes | Used |
| PyJWT | Yes | Used for signed session tokens |
| pytest + Starlette TestClient | Yes | Used for backend, integration and WebSocket tests |
| React 19, TypeScript, esbuild | Yes | Used |
| Vite | **No** | Project ships a standard Vite config (`npm run dev/build`) **and** an esbuild build script that was actually executed here; the prebuilt bundle is served by the backend so the app runs with Python only (D-003) |
| Recharts | **No** | Charts implemented as dependency-free React/SVG components (D-004). Recharts code could not be compiled or tested here, so it was not shipped untested. |
| Icon library | `react-icons` available | Used (Lucide set via `react-icons/lu`) |
| Browser for E2E | Playwright + Chromium | Used for end-to-end tests and screenshots |

## 3. Comparison with specification

At audit time 0 % of the specification was implemented (empty folder). The full gap is the
whole specification; see `docs/DEVELOPMENT_STATUS.md` for the live status of every requirement.

## 4. Risks identified at Stage 0

1. No official clinical thresholds are available to the team. ⇒ All numeric alert criteria are
   either (a) cited NASA operational references used only for their stated purpose
   (e.g. NASA-STD-3001 V2 [6004] habitat CO₂ limit, the 8.5 h sleep-scheduling reference), or
   (b) explicitly labelled **DEMONSTRATION-ONLY** statistical rules relative to the individual
   baseline.
2. No physical devices are available. ⇒ Device adapters + simulated devices + documented JSON API;
   no claim of hardware compatibility.
3. The user's computer cannot run commands from this session (file bridge only). ⇒ Everything is
   built and tested in the workspace, then copied to the folder with run instructions for Windows.
