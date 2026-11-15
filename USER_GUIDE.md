# ASTRA — User Guide (live website)

**ASTRA** (Astronaut Self-assessment, Tracking and Response Assistant) helps a space crew monitor its health and
respond to medical problems on board. A ground medical team follows along whenever the link to Earth allows. This
guide explains how to **use the live ASTRA website** in your browser; you don't need to install anything.

> ASTRA is a demonstration for the NASA Space Apps Challenge 2026: **decision support, not a medical device or an
> autonomous doctor**. All crew members and all data are **synthetic**.

---

## 1. Open the website

ASTRA has two websites: one aboard the spacecraft and one on Earth.

| Website | Who uses it | Link | Accounts | Password |
|---|---|---|---|---|
| **Crew Side** (onboard spacecraft) | Astronauts and the Crew Medical Officer | https://immigration-tells-holidays-passing.trycloudflare.com | `vega`, `okafor` (astronauts) · `mori` (Crew Medical Officer, "CMO") | `optionalwillwin` |
| **Earth Side** (ground operations) | Mission administrator and ground flight surgeon | https://manuals-documentary-marsh-pipeline.trycloudflare.com | `admin` (administrator) · `ramirez` (flight surgeon) | `AstraJudges2026` |

* Crew accounts work only on the Crew Side, and Earth accounts only on the Earth Side. If you pick the wrong
  website, ASTRA tells you which one to use.
* On the sign-in page, the **Demonstration accounts** buttons fill in the username; type the password and press
  **Sign in**.
* To be two people at once (for example astronaut `vega` and CMO `mori`), use a second browser window in
  **private / incognito mode**.
* The links are temporary. If they stop working, the current ones are in [usage_links.txt](usage_links.txt).
  Data may be reset when the demo is restarted.

---

## 2. Finding your way around

* **Sidebar (left):** the pages your role may use. Click a page name to open it.
* **Top strip:**
  * mission name, mission day and mission clock;
  * **Earth link** (Crew Side): *available*, *unavailable · simulated* or *unreachable*, with the number of
    records still *pending* for Earth;
  * **Spacecraft data received …** (Earth Side): how old the newest synchronized data is;
  * connection to the website's own server (*Onboard server · live*, *Earth server connected*, or
    *unreachable*).
* **"Viewing records of"** (banner or selector): whose health records you are looking at.
* **Theme:** **Light / Dark / System** at the bottom of the sidebar (top-right on the sign-in page). Your browser
  remembers the choice.
* **Sign out:** bottom of the sidebar.
* **Status colours** mean the same thing everywhere:

  | Colour | Meaning |
  |---|---|
  | Green | no current concern |
  | Yellow | reassessment recommended |
  | Orange | medical review |
  | Red | urgent |
  | Gray | insufficient or unavailable data |

* Items marked **SYNTHETIC** were generated for the demonstration. **Private** marks behavioral-health content.

---

## 3. Astronaut — `vega` or `okafor` (Crew Side)

You see and record **only your own** health data.

### Record a measurement
1. Open **Daily routine** and find the **Record** panel.
2. Choose a tab: **Vital signs**, **Symptoms**, **Sleep**, **Private check-in**, **Exercise** or **Food and water**.
3. Fill in the form. *How to measure* explains how to take the reading. Choose the context (for example *resting*)
   and, if you like, a device.
4. Press the save button (*Save blood pressure*, *Save sleep*, *Save check-in*, …).

The reading is saved aboard immediately. The CMO can see it straight away, and it is sent to Earth automatically.

### See how you are doing
| Page | What you see |
|---|---|
| **My dashboard** | Overall status lamp, latest vital signs, upcoming assessment tasks, recent health events, ground communication |
| **Daily routine** | Which tasks are done, due or overdue today, plus 7-day completion history |
| **Health records** | Body map. Select a body system to see its latest measurements, reported symptoms, open findings, related NASA risks and sources. **Open in analytics** jumps to trends. |
| **Health analytics** | Trends compared with your personal baseline, data quality. Click a point for full details of that measurement. |
| **Alerts & response** | Your alerts, and procedures for any open medical event |
| **Mission environment** | Cabin CO₂, temperature, humidity and radiation (these describe the cabin, not you) |
| **Knowledge library** | Space-health indicators, measurement instructions, assessment rules and evidence sources |

**Private check-in:** your private answers and notes are visible only to you and the ground flight surgeon. The
CMO only sees that a private entry exists.

### Demo data (to explore quickly)
Click the **Demo data** chip in the top strip.

* **Random normal data** → **Generate normal data**: a few days of ordinary history.
* **Trigger a situation**: choose a scenario, then **Generate 10 days ending in this situation**. Scenarios:
  normal mission day, sleep deprivation and fatigue, cardiovascular change, possible illness, radiation exposure
  event, reduced exercise / musculoskeletal concern, behavioral health concern, medical emergency.
* It takes about 10–25 seconds, applies **only to your own profile**, and **Remove my generated demo data**
  deletes it again.

---

## 4. Crew Medical Officer — `mori` (Crew Side)

Everything an astronaut has for your own record, plus responsibility for the crew.

### Watch the crew
* **Crew overview:** one card per crew member with status, latest vitals, open alerts and routine. Click a summary
  tile (for example *Need medical review*) to filter. **Open dashboard**, **Analytics** and **Medical response**
  open that astronaut.
* Use **Viewing records of** in the top strip to switch between crew members on any health page.

### Respond to a problem
Open **Medical response**:

1. Pick an alert or medical event. **What triggered this** explains the finding and the evidence behind it.
2. Follow the **Procedure** and tick the **Verification checklist**.
3. Use **Actions**:
   * **Acknowledge** an alert (it stays open);
   * **Add note**;
   * change the **Event state**;
   * **Escalate to medical personnel**;
   * **Generate report**, a structured medical report for the ground;
   * **Resolve** (a note is required).
4. The **Event timeline** records every step with who did it and when.

### Earth connection
The **Earth connection & synchronization** panel at the top of **Crew overview** (also in **Mission
operations**) shows:

* whether Earth is reachable;
* the synchronization state (pending, in progress, complete, failed);
* how many records are waiting, and when the last successful synchronization happened;
* **Crew records not yet synchronized with Earth**, a list with each record's original time.

**Demonstration control:**

* **Simulate Earth Connection Loss** cuts only the link between the spacecraft and Earth. Everything aboard keeps
  working: astronauts keep recording, you keep monitoring, and new records wait in the queue.
* **Restore Earth Connection** sends everything that was waiting within seconds.

It never changes or deletes records, and it stays in effect for everyone until you restore it.

### Messages from the ground
**Ground follow-up notes** at the bottom of **Crew overview** show requests and follow-ups written by the flight
surgeon on Earth, delivered at the last synchronization.

---

## 5. Ground flight surgeon — `ramirez` (Earth Side)

You oversee the crew of your assigned mission using the data that has **reached Earth**.

* **Mission overview:** mission status, crew status, and **Data received from the spacecraft**, showing when the
  last synchronization arrived and when each astronaut's newest measurement was taken aboard.
* **Crew overview:** status of the assigned crew.
* **Astronaut medical records:** choose an astronaut, then a tab: **Summary**, **Body systems & measurements**,
  **Trends & history**, **Logs & assessments**. You also see private check-ins.
* **Medical response & reports:** alerts, medical events, procedures and reports as recorded aboard.
* **Ground follow-up notes** (bottom of an astronaut's records): choose *Follow-up*, *Request to the CMO* or
  *Note*, write your message and press **Send to crew**. It is delivered to the CMO at the next synchronization,
  and each note shows whether it has reached the spacecraft yet.

**Earth data is never live.** A banner on each astronaut shows when the newest measurement was taken and when it
arrived. Measurements keep their original time. Readings recorded aboard during an Earth-link outage appear only
after the link is restored.

You cannot record measurements or change onboard records from Earth; your clinical input travels as follow-up
notes.

---

## 6. Mission administrator — `admin` (Earth Side)

* **Mission overview** and **Crew overview** for all missions.
* **Astronaut records:** read-only, with private check-ins hidden.
* **Alerts & medical events:** read-only.
* **Mission ops & sync:** what has arrived from the spacecraft, plus the audit log.
* **Users & crew assignment:**
  * **Register crew account** (name, username, password, role, mission, crew);
  * **Edit**;
  * **Reset password**;
  * deactivate or re-activate accounts;
  * assign the flight surgeon's mission.

  Accounts created on Earth are not sent to the spacecraft in this prototype.

---

## 7. Five-minute guided tour

1. **Crew Side**, sign in as **mori** → **Crew overview** → press **Simulate Earth Connection Loss**. The top strip
   shows *Earth link unavailable · simulated*.
2. In a private window, **Crew Side**, sign in as **vega** → **Daily routine → Record → Vital signs** → save a
   heart rate. The strip shows records *pending* for Earth.
3. Back as **mori**: open Elena Vega from **Crew overview**. The reading is already there, and it is listed under
   *Crew records not yet synchronized with Earth*.
4. **Earth Side**, sign in as **ramirez** → **Astronaut medical records → Elena Vega**. The new reading is **not**
   there yet, and the banner explains that the data is not live.
5. As **mori**, press **Restore Earth Connection**. Within seconds the panel says *Synchronization complete*.
6. Refresh the Earth page. The reading appears with its original measurement time.
7. Optional: as **ramirez**, send a **Request to the CMO**. It appears in mori's **Ground follow-up notes** shortly
   afterwards.
8. Optional: as **vega**, use **Demo data → Trigger a situation → Medical emergency** and follow the alert as
   **mori** in **Medical response**.

---

## 8. Troubleshooting

| Problem | What to do |
|---|---|
| "This is the onboard (Crew Side) server…" when signing in | You used an Earth account on the Crew Side, or the reverse. Use the other link. |
| "Invalid username or password" | Usernames are lower-case. Passwords: crew `optionalwillwin`, Earth `AstraJudges2026`. |
| A link does not open | The demo may have been restarted with new links. Check [usage_links.txt](usage_links.txt). |
| A new reading is missing on Earth | Look at the Crew Side top strip. If the Earth link is unavailable, the reading is still queued; the CMO can restore it. |
| *Simulate Earth Connection Loss* is missing | Only the CMO (`mori`) sees it, on the Crew Side, in **Crew overview** or **Mission operations**. |
| "Too many requests" | The public demo limits request rates; wait a minute. |
| You were signed out | Sessions expire. Sign in again; your data is still on the server. |

---

## 9. More information

* **[usage_links.txt](usage_links.txt)**: the current live links and passwords.
* **[README.md](README.md)**: project overview and how to run ASTRA on your own computer.
* **[docs/CREW_EARTH_SYNC.md](docs/CREW_EARTH_SYNC.md)**: Crew Side / Earth Side architecture, synchronization,
  security, configuration and known limitations.
* **[presentation/ASTRA_User_Guide.pptx](presentation/ASTRA_User_Guide.pptx)**: short slide walkthrough of using the
  website.
* **[presentation/demo.pptx](presentation/demo.pptx)**: project demonstration presentation.
