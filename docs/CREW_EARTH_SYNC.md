# ASTRA — Crew Side, Earth Side and offline synchronization

ASTRA is one codebase deployed in two places:

| | **Crew Side** (onboard) | **Earth Side** (ground) |
|---|---|---|
| `ASTRA_DEPLOYMENT` | `onboard` | `earth` |
| Who signs in | astronauts, Crew Medical Officer (CMO) | administrators, ground flight surgeons |
| Database | onboard SQLite (authoritative for new crew records) | separate Earth SQLite |
| Creates health records | yes (measurements, logs, assessments, alerts, medical events) | no, it only receives them |
| Background service | replication worker (sends to Earth, fetches ground notes) | replication receiver (signed API) |
| Works without the other side | **yes**, completely | yes, and it shows the last received data |

`standalone` (the default when nothing is configured) is the earlier single-server prototype: every role on one server, with an in-process simulated ground station. It is kept so existing installs and tests keep working.

The servers enforce the side rules: a login on the wrong side returns `403 wrong_side`. On Earth, every write except account management and ground notes returns `409 earth_side_read_only`.

## How records are stored onboard

1. The browser sends a measurement to the onboard backend.
2. The existing ingestion pipeline validates it, authorizes it (an astronaut can only record for themself, the CMO only for their crew) and stores it. Assessments and alerts run as before.
3. **In the same SQLite transaction**, a database trigger adds the record to `replication_outbox` as `PENDING`. Triggers are installed only on the onboard deployment, after the pre-flight reference dataset is seeded. A record can therefore never be "saved but not queued", and no health logic had to change.
4. The record is immediately visible to authorized crew members through the onboard API, with or without Earth.

Replicated tables: observations, sleep, check-in (mood), exercise, nutrition, medication, medical history, assessments (and their links), alerts (and their links), medical events, transitions, actions, medical reports, environment events. Every record has a globally unique id: 80 random bits, or a deterministic hash of the client submission id for retries. Records keep their original timestamps (`measured_at`, `created_at`, …). Synchronization times are stored separately: `synced_at` onboard, `first_received_at` on Earth.

## How synchronization works

```
browser ──► onboard API ──► onboard DB ──(trigger)──► replication_outbox (PENDING)
                                                          │  SyncWorker thread (every ASTRA_SYNC_INTERVAL s,
                                                          │  independent of logins; woken on restore)
                                     link gate ◄──────────┤  1. gate: simulated outage? configured?
                                                          │  2. PENDING/FAILED → SENDING (version captured)
                                                          ▼  3. POST /api/v1/replication/batch (HMAC-signed)
                                                   Earth receiver: verify signature + peer, validate each record,
                                                   store idempotently, answer per record
                                                          │
          SYNCED (only if the acknowledged version  ◄─────┘  stored / duplicate / updated / stale → SYNCED
          is still the current one), REJECTED, or            rejected → REJECTED (audited, kept onboard)
          FAILED + back-off (retried automatically)          deferred (parent missing) → FAILED, retried
                                                          4. GET /api/v1/replication/downlink: ground notes
```

* **Order**: records are sent in change order (`change_seq`), so parents (assessment → alert → medical event) reach Earth before their children. A child whose parent is missing is *deferred*, not dropped. After 12 deferrals it becomes REJECTED and visible.
* **Idempotency**: Earth keeps `replicated_records(record_type, record_id, revision, payload_hash)`. Retransmitting a record Earth already has is acknowledged as `duplicate`. Nothing is inserted twice.
* **Interruption**: a row still `SENDING` at the start of a pass belongs to an interrupted pass, for example a crash or restart, and is re-sent. A lost acknowledgement leads to a resend, which Earth answers with `duplicate`.
* **Conflict rules**:
  * Health observations and logs are **immutable**. A second copy with different content is rejected and never overwritten.
  * Workflow state owned by the onboard side (alerts, medical events, environment events, medical reports) carries an increasing revision. Earth applies only a newer revision.
  * Earth never edits onboard records. Ground clinical follow-up is a separate, attributable `ground_annotations` record. It is delivered to the CMO through the downlink and acknowledged by cursor.
  * An id that already exists on Earth but did not come from the spacecraft is never overwritten.
* **Validation on Earth**:
  * The record type must be replicated, columns are checked against a whitelist, and the key must match `record_id`.
  * The integrity hash must match the payload, and timestamps must be timezone-aware ISO with no future `measured_at`.
  * The mission must be the peer's authorized mission (`ASTRA_SYNC_PEER_MISSION`), and the astronaut must be assigned to that mission. Parents must belong to the same mission. The spacecraft cannot write other missions' astronauts.
* **Server-to-server security**:
  * HMAC-SHA256 signature over the protocol, method, path, timestamp, node id and body hash, using the pre-shared key `ASTRA_SYNC_KEY`, with a ±300 s timestamp window.
  * Only the configured peer node id is accepted. User session tokens are not accepted on the peer API.
  * Transport: the worker **refuses plain HTTP to a non-loopback Earth server**. Configure an `https://` `ASTRA_EARTH_URL` (optional CA bundle `ASTRA_SYNC_CA_BUNDLE`). `run.py --ssl-certfile/--ssl-keyfile` serves HTTPS.
* **Audit**: `replication.batch_sent`, `replication.send_failed`, `replication.rejected`, `replication.batch_received`, `replication.records_rejected`, `replication.auth_rejected`, `replication.downlink*`, `link_simulation.enabled/disabled`.

## CMO-controlled Earth connection simulation (demonstration)

* Shown only to the **CMO**, in *Crew overview* and *Mission operations*: **Simulate Earth Connection Loss** / **Restore Earth Connection**.
* Backend: `POST /api/v1/link/simulation/outage` and `/restore`. These are restricted to the `medical_officer` role, exist only on the onboard deployment, and **only when `ASTRA_ALLOW_LINK_SIMULATION=1`**. Otherwise they return `403 simulation_disabled`, so the feature is off in a normal deployment.
* The state is stored in the onboard database (`replication_state.simulated_outage`). It survives page refreshes, new sessions and server restarts.
* The sync worker checks this gate before **every** network call, both upload and downlink. While it is set, nothing reaches Earth. Records keep being saved onboard and queued as `PENDING`.
* Nothing else is affected: the onboard server, the spacecraft network, sessions, assessments, alerts, medical events and crew monitoring keep working. No record is modified or deleted.
* On restore, all waiting records become due immediately and the worker is woken. The panel shows *Synchronization in progress* → *complete*, or *failed* / *rejected*.

## Demonstration on one computer

Windows: double-click **`start-astra-crew-earth.bat`**. macOS/Linux: `./start-astra-crew-earth.sh`. Manual start:

```
cd backend
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
python run.py --side earth   --reset-db                           # Earth Side  http://127.0.0.1:8100
python run.py --side onboard --allow-link-simulation --reset-db   # Crew Side   http://127.0.0.1:8000
```

`--side` sets the per-side defaults: port, data directory (`backend/data/onboard`, `backend/data/earth`), node ids, Earth URL, peer mission, and a shared generated demo key in `backend/data/demo-sync.key`.

| Account | Password | Server |
|---|---|---|
| `vega`, `okafor` (astronauts), `mori` (CMO) | `optionalwillwin` | Crew Side :8000 |
| `admin` (administrator), `ramirez` (ground flight surgeon, assigned to ARES-T1) | `astra-demo` | Earth Side :8100 |

These are shared **demonstration** passwords and all data is synthetic.

**Script for judges** (use two browser windows; a private window helps when signing in as two crew members):

1. :8000, sign in as **mori** → *Crew overview*. The panel shows *Earth connection available*, 0 waiting, and the last synchronization time.
2. Press **Simulate Earth Connection Loss**. The header turns to *Earth link unavailable · simulated*.
3. In another window on :8000, sign in as **vega** → *Daily routine → Record*. Enter a heart-rate or blood-pressure measurement. The header shows *N pending*.
4. Back as mori: the measurement is visible immediately (open Vega from Crew overview). *Crew records not yet synchronized with Earth* lists it as PENDING.
5. :8100, sign in as **admin** or **ramirez** → *Astronaut records → Elena Vega*. The new measurement is **not** there. The banner says the data is synchronized, not live, and shows when the newest data was taken aboard.
6. As mori, press **Restore Earth Connection**. Within a few seconds the panel shows *Synchronization complete*.
7. Refresh Earth: the measurement appears with its **original** measurement time. *Mission overview → Data received from the spacecraft* shows the arrival time.
8. Optional: as ramirez on Earth, write a *Ground follow-up note* for Vega. It appears in mori's Crew overview after the next synchronization.

For a real outage, close the Earth server window. The onboard side keeps working, shows *Earth server unreachable*, retries automatically, and delivers everything once Earth is started again.

## Configuration reference

| Variable | Side | Meaning |
|---|---|---|
| `ASTRA_DEPLOYMENT` | both | `onboard`, `earth` or `standalone` (default) |
| `ASTRA_NODE_ID` | both | identity of this server |
| `ASTRA_DATA_DIR` / `ASTRA_DB_PATH` | both | separate data directory / database per side |
| `ASTRA_SYNC_KEY` or `ASTRA_SYNC_KEY_FILE` | both | pre-shared HMAC key (same value on both sides) |
| `ASTRA_EARTH_URL` | onboard | Earth base URL (`https://…`; HTTP is allowed only to loopback unless `ASTRA_SYNC_ALLOW_INSECURE=1`) |
| `ASTRA_SYNC_CA_BUNDLE` | onboard | CA bundle for the Earth certificate |
| `ASTRA_SYNC_INTERVAL` | onboard | seconds between passes (default 3) |
| `ASTRA_ALLOW_LINK_SIMULATION` | onboard | `1` enables the CMO demonstration control (test/demo environments only) |
| `ASTRA_SYNC_PEER_ID`, `ASTRA_SYNC_PEER_MISSION` | earth | accepted onboard node and the mission it may deliver |

## Browser offline support (PWA)

`frontend/public/sw.js` caches only the **application shell**: `index.html`, the hashed JS/CSS, the icon and the manifest. A previously loaded ASTRA therefore opens without a network connection. `/api/*` and `/ws` are never cached: health data always comes from the server, and the onboard server is the authoritative database. When the browser cannot reach its server, the UI says so ("Onboard server unreachable"; on the sign-in page, "server cannot be reached"). Entries submitted while the onboard server is unreachable are kept in the existing per-browser outbox and re-sent with the same submission id (no duplicates). A browser cannot talk to a server that is powered off or unreachable. The service worker registers only in a secure context: `localhost` / `127.0.0.1` or HTTPS.

## Limitations and assumptions

* **Provisioning**: both sides are seeded with the same synthetic mission, crew, accounts, devices and pre-flight reference data, as if provisioned before launch. Accounts or crew assignments changed later on Earth are **not** uplinked to the spacecraft. Only ground notes travel Earth → onboard.
* Baselines and rule versions are not replicated. Earth shows the assessments computed aboard and does not re-assess.
* Deleting synthetic demo data onboard ("remove my demo data") does not delete copies that have already reached Earth. Records deleted before transmission are marked `DISCARDED`.
* One onboard peer per Earth server (single pre-shared key, no key rotation, no mutual TLS). The demo runs plain HTTP on loopback; a real deployment needs HTTPS certificates and secret management.
* The HMAC window allows a replay within 300 s. Replays are harmless because storage is idempotent, but they are not rejected.
* The light-time delay is not imposed on the real link; it is shown as a mission setting only.
* Unfinished form drafts are not stored in the browser. Only submissions that fail because the server is unreachable are preserved, in the outbox.

## Public demonstration through Cloudflare Tunnel

Double-click **`start-public-astra.bat`** (project root). It calls `tools\start_public_crew_earth.ps1`, which:

1. starts the Earth Side server on 127.0.0.1:8120 and the Crew Side server on 127.0.0.1:8020. They use their own
   databases in `backend\data-public\` (your local data is never exposed), with public-demo protections on
   (`ASTRA_PUBLIC_DEMO=1`: rate limits and locked rule configuration), fresh synthetic data, a fresh random
   server-to-server key, and the CMO link simulation enabled;
2. opens **two Cloudflare Quick Tunnels**, one per side. The script downloads the official `cloudflared.exe` into
   `tools\bin\` if it isn't on PATH. No Cloudflare account is needed;
3. prints both `https://….trycloudflare.com` links and the passwords, and self-tests each link (health, sign-in,
   WebSocket). Details are saved in `tools\.public_crew_earth\info.txt`.

The two servers synchronize with each other over loopback inside the PC. Only the two web apps are published,
over HTTPS at the Cloudflare edge. Stop everything with **`stop-public-astra.bat`**.

| Side | Accounts | Default password |
|---|---|---|
| Crew Side link | `vega`, `okafor` (astronauts), `mori` (CMO) | `optionalwillwin` |
| Earth Side link | `admin` (administrator), `ramirez` (flight surgeon) | `AstraJudges2026` |

Options: `start-public-astra.bat -EarthPassword <pw> -CrewPassword <pw> -NoLinkSimulation`, or `-NoTunnel` to
start both servers locally without publishing anything. Quick Tunnel URLs change on every start and stay up only
while the PC and the script run. The older single-server public demo is still available as
`tools\start_public_demo.bat`.
