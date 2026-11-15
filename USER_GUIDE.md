# ASTRA — User Guide

**ASTRA** (Astronaut Self-assessment, Tracking and Response Assistant) is a health-monitoring and medical
decision-support prototype for long-duration space missions. It is a demonstration for the NASA Space Apps
Challenge 2026: **not a medical device and not an autonomous doctor**. All crew data is **synthetic**.

This guide covers starting ASTRA, signing in, the screens each role uses, the Earth-link demonstration and the
public (internet) demo.

## Live demo: try it in your browser

The public two-sided demo is **live**. No installation is needed; open the links in any browser.

| Side | Link | Accounts | Password |
|---|---|---|---|
| **Crew Side** (onboard) | https://immigration-tells-holidays-passing.trycloudflare.com | `vega`, `okafor` (astronauts), `mori` (CMO) | `optionalwillwin` |
| **Earth Side** (ground) | https://manuals-documentary-marsh-pipeline.trycloudflare.com | `admin` (administrator), `ramirez` (flight surgeon) | `AstraJudges2026` |

* Synthetic data only.
* The links work while the host PC runs the public demo. If it is restarted, new links are generated and the
  data is reset; the current links are always in [usage_links.txt](usage_links.txt).
* Want a quick tour? Follow the 5-minute script in [section 8](#8-demonstration-script-about-5-minutes).

---

## 1. Two sides of ASTRA

ASTRA runs as two servers built from the same software:

| | **Crew Side** (onboard the spacecraft) | **Earth Side** (ground operations) |
|---|---|---|
| Used by | Astronauts and the Crew Medical Officer (CMO) | Administrators and ground flight surgeons |
| Purpose | Record and monitor health aboard; works with **no** connection to Earth | Review the astronaut data that has reached Earth |
| Data | The onboard database (the authoritative copy of new records) | A separate Earth database, filled by synchronization |

Every record saved aboard is queued and sent to Earth automatically whenever the Earth link is available.
If the link is down, nothing is lost: records wait onboard and are sent later.

---

## 2. Starting ASTRA

Requirement: **Python 3.10 or newer** ("Add python.exe to PATH" ticked during installation). The first start
creates a virtual environment and installs a few packages automatically. Node.js is not needed.

| What you want | Double-click | Open in the browser |
|---|---|---|
| **Crew Side + Earth Side on this PC** (recommended for the demo) | `start-astra-crew-earth.bat` | Crew: http://127.0.0.1:8000 · Earth: http://127.0.0.1:8100 |
| **Public demo on the internet** (two Cloudflare links) | `start-public-astra.bat` | the two `https://….trycloudflare.com` links it prints |
| Older single-server prototype (all roles on one server) | `start-astra.bat` | http://127.0.0.1:8000 |

macOS / Linux: `./start-astra-crew-earth.sh`.

**Stopping:** close the server windows (local) or double-click `stop-public-astra.bat` (public demo).

> **Data is reset on every start.** All three launchers wipe their database and re-create the synthetic demo
> mission and crew each time they start, so every session begins clean. Data recorded during a session is lost
> when the servers are restarted with these launchers. To keep data between restarts, start the servers manually
> without `--reset-db` (see section 9).

---

## 3. Accounts

All passwords are **shared demonstration passwords**. Change them before any real use.

| Username | Role | Sign in on | Password (local) | Password (public demo) |
|---|---|---|---|---|
| `vega` | Astronaut (Commander) | Crew Side | `optionalwillwin` | `optionalwillwin` |
| `okafor` | Astronaut (Flight Engineer) | Crew Side | `optionalwillwin` | `optionalwillwin` |
| `mori` | Crew Medical Officer | Crew Side | `optionalwillwin` | `optionalwillwin` |
| `admin` | Mission administrator | Earth Side | `astra-demo` | `AstraJudges2026` |
| `ramirez` | Ground flight surgeon | Earth Side | `astra-demo` | `AstraJudges2026` |

Crew accounts sign in only on the Crew Side and Earth accounts only on the Earth Side. If you use the wrong
server, ASTRA tells you which one to use. The sign-in page shows which side you are on, and its
*Demonstration accounts* buttons fill in the username for you.

Tip: use a second browser window, or a private window, to be signed in as two people at once (for example
`vega` and `mori`).

---

## 4. Finding your way around

* **Sidebar (left):** the pages available to your role. Items you are not allowed to use are not shown, and the
  server enforces the same rules.
* **Top strip:**
  * mission name, mission day and mission clock (MET / UTC);
  * **Earth link** status (Crew Side) or **Spacecraft data received …** (Earth Side);
  * whether your browser is connected to its server (*Onboard server · live*, *Earth server connected*, or
    *… unreachable*);
  * on the Crew Side, how many records are *pending* for Earth.
* **"Viewing records of" banner:** shows whose health records you are looking at.
* **Theme:** use the **Light / Dark / System** switch at the bottom of the sidebar (top-right on the sign-in
  page). The choice is remembered by your browser. *System* follows your computer's light or dark setting.
* **Status colours** always mean the same thing:

  | Colour | Meaning |
  |---|---|
  | Green | no current concern |
  | Yellow | reassessment recommended |
  | Orange | medical review |
  | Red | urgent |
  | Gray | insufficient or unavailable data |

* Anything labelled **SYNTHETIC** was generated for the demonstration.

---

## 5. Astronauts (`vega`, `okafor`) — Crew Side

You see and record **only your own** health data.

| Page | What you do there |
|---|---|
| **My dashboard** | Overall status lamp, latest vital signs, open alerts, today's tasks |
| **Daily routine → Record** | Enter measurements on the tabs *Vital signs* (blood pressure, heart rate, SpO₂, temperature, respiration …), *Symptoms*, *Sleep*, *Private check-in* (mood, stress, fatigue …), *Exercise* and *Food and water*. Each form has a *How to measure* guide. |
| **Daily routine** | Which assessments are done, due or overdue today, plus 7-day completion history |
| **Health records** | Body map and body systems with related measurements, symptoms and assessments |
| **Health analytics** | Trends against your personal baseline, measurement history |
| **Alerts & response** | Your alerts and the preloaded procedures for open medical events |
| **Mission environment** | Cabin readings (CO₂, radiation …). These describe the cabin, not you. |
| **Knowledge library** | Space-health hazards, risks and evidence sources |

**Private check-in:** your private notes are visible only to you and the ground flight surgeon. The CMO only
sees that a private entry exists.

**Demo data** (chip in the top strip): generates a few days of synthetic history for **your own** profile in
about 10–25 seconds, and can remove it again.

**If the onboard server is unreachable:** entries you submit are kept in your browser and sent automatically
when the connection returns, without creating duplicates.

---

## 6. Crew Medical Officer (`mori`) — Crew Side

Everything an astronaut has for your own record, plus:

| Page | What you do there |
|---|---|
| **Crew overview** | Status of every astronaut in your crew. Click a tile to filter, open an astronaut's records, see the **Earth connection & synchronization** panel and **Ground follow-up notes** from Earth. |
| **Header "Viewing records of"** | Switch between crew members' records |
| **Medical response** | Crew alerts and medical events: acknowledge, follow procedures and checklists, escalate, generate medical reports |
| **Mission operations** | Earth-link panel, simulator, devices, baselines, audit |

The **Earth connection & synchronization** panel shows:

* whether the Earth connection is available;
* the synchronization state (pending, in progress, complete, failed);
* how many records are waiting, when the last successful synchronization happened;
* **Crew records not yet synchronized with Earth**, a list with each record's original measurement time.

### Earth-link demonstration (CMO only)

* **Simulate Earth Connection Loss**: cuts only the link between the onboard server and the Earth server.
  Everyone aboard keeps working normally. New records are saved onboard and wait in the queue; nothing reaches
  Earth.
* **Restore Earth Connection**: everything waiting is sent within seconds. The panel then shows *Synchronization
  complete*, or lists any record that failed.

This is a clearly labelled **demonstration control**, not a network setting. It never changes or deletes
records. It stays in effect across page reloads, new sign-ins and server restarts until you restore it. Each
use is written to the audit log.

---

## 7. Earth Side — administrator (`admin`) and ground flight surgeon (`ramirez`)

Earth users have no personal health pages and cannot record astronaut measurements. They review what has
arrived from the spacecraft.

| Page | Administrator | Flight surgeon |
|---|---|---|
| **Mission overview** | All missions, crew status, **Data received from the spacecraft** (last synchronization, newest measurement per astronaut) | Assigned mission only |
| **Crew overview** | Crew status (read-only) | Assigned mission's crew |
| **Astronaut records** | Pick an astronaut. Summary, body systems & measurements, trends & history, logs & assessments. Read-only; private check-ins hidden. | Same, including private check-ins of the assigned crew |
| **Alerts & medical events / Medical response & reports** | Read-only | Medical events, alerts and reports as recorded aboard |
| **Ground follow-up notes** (bottom of Astronaut records) | Read | **Write** follow-ups or requests for the CMO. They are delivered at the next synchronization, and each note shows whether it has reached the spacecraft. |
| **User management** | Register crew accounts, edit, deactivate, reset passwords, assign missions | — |

**Earth data is not live.** Every Earth page shows the time of the last synchronization and when the newest
measurement was taken aboard. Measurements keep their **original** measurement time; the time they reached
Earth is shown separately.

Onboard records are never edited from Earth. Ground notes are separate records signed by their author.

---

## 8. Demonstration script (about 5 minutes)

1. Start `start-astra-crew-earth.bat` (or `start-public-astra.bat` for the internet links).
2. **Crew Side**: sign in as **mori** and open **Crew overview**. The panel shows *Earth connection available*.
3. Press **Simulate Earth Connection Loss**. The header changes to *Earth link unavailable · simulated*.
4. In a second window on the **Crew Side**, sign in as **vega**. Go to **Daily routine → Record → Vital signs** and
   save a heart rate or blood pressure reading. The header shows *1 pending* (or more).
5. As **mori**: the reading is visible immediately (open Elena Vega from Crew overview). It also appears under
   *Crew records not yet synchronized with Earth*.
6. **Earth Side**: sign in as **ramirez** (or **admin**) and open **Astronaut records → Elena Vega**. The new
   reading is **not** there yet; the banner explains that the data is synchronized, not live.
7. As **mori**, press **Restore Earth Connection**. Within a few seconds the panel shows *Synchronization
   complete*.
8. Refresh the Earth page. The reading appears with its original measurement time.
9. Optional: as **ramirez**, write a ground follow-up note for Vega. Shortly afterwards it appears in mori's
   Crew overview.

For a *real* outage: close the Earth server window. The Crew Side keeps working, reports *Earth server
unreachable*, retries automatically and delivers everything once the Earth server is started again.

---

## 9. Public demo on the internet (Cloudflare)

`start-public-astra.bat`:

* starts both servers with their **own public databases** (your local data is never exposed);
* turns on rate limits and the locked rule configuration;
* opens **two Cloudflare Quick Tunnels**, downloading `cloudflared` if needed (no Cloudflare account required);
* prints the **Crew Side link**, the **Earth Side link** and both passwords, then self-tests each link.

The details are also saved in `tools\.public_crew_earth\info.txt`.

* **Both public databases are wiped and re-seeded on every start.**
* The links change every time and work only while the PC and the script keep running.
* Stop with `stop-public-astra.bat`.
* Options, added after the file name in a command prompt:
  * `-EarthPassword <pw>`, `-CrewPassword <pw>`: choose the demo passwords;
  * `-NoLinkSimulation`: hide the CMO Earth-link demonstration control;
  * `-NoTunnel`: start both servers locally without publishing anything.

**Keeping data between restarts (manual start):**

```
cd backend
.venv\Scripts\activate
python run.py --side earth                              # http://127.0.0.1:8100
python run.py --side onboard --allow-link-simulation    # http://127.0.0.1:8000
```

Without `--reset-db` the databases in `backend\data\earth` and `backend\data\onboard` are kept.

---

## 10. Offline use

* ASTRA can be installed as an app (browser menu → *Install*). A previously opened ASTRA still loads its screens
  without a network connection, but health data always comes from the server.
* **Aboard:** the browser needs the spacecraft network and the onboard server. It does **not** need Earth.
* If the onboard server cannot be reached, the header says *Onboard server unreachable* and entries you submit
  wait in the browser until it is back.

---

## 11. Troubleshooting

| Problem | What to do |
|---|---|
| "This is the onboard (Crew Side) server…" when signing in | You used an Earth account on the Crew Side (or the reverse). Open the other link or port. |
| "Python 3.10+ is required" | Install Python from python.org with "Add python.exe to PATH" ticked, then start again. |
| The Earth page does not show a new measurement | Check the Crew Side header. If the Earth link is unavailable (simulated or unreachable), the record is still queued. Restore the link and refresh. |
| *Simulate Earth Connection Loss* button missing | Only the CMO (`mori`) sees it, only on the Crew Side, and only when the demo control is enabled (the launchers enable it). |
| Public links do not open | Wait up to a minute after start (DNS). Check that the script window is still running, then see `tools\.public_crew_earth\*.log`. |
| Port already in use | Stop the other ASTRA instance (close its window or run `stop-public-astra.bat`). |

More detail: **[docs/CREW_EARTH_SYNC.md](docs/CREW_EARTH_SYNC.md)** (architecture, security and limitations) and
**[README.md](README.md)**.
