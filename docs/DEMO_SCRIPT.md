# Demonstration script (≈ 6 minutes)

Preparation: `start-astra.bat` (or `python run.py --reset-db`), browser at http://127.0.0.1:8000.
Use two windows: **mori** (Crew Medical Officer) and **vega** (astronaut). Optional third: **ramirez** (flight surgeon).

1. **Problem (30 s)** — Mars transit: 5–20 minute light delay, no evacuation. ASTRA lets the crew monitor, analyze,
   respond and coordinate without Earth. All data shown is synthetic.
2. **Missing data is not healthy (30 s)** — as `vega`, Mission overview shows a grey lamp, "Not enough data": only
   pre-mission measurements exist. Vitals are grey and marked stale.
3. **Record a measurement (45 s)** — Daily routine → Blood pressure, enter 118/76, quality "Good", save. Show
   "Saved 2 measurements". Enter 900 → rejected with a clear reason ("input validation, not a clinical threshold").
4. **Run the mission (45 s)** — as `mori`, Mission operations → Simulator → *Emergency*, speed 48 → Start. Point out
   SYNTHETIC labels, device status, and that the simulator posts to the same telemetry API devices use.
5. **Urgent response (90 s)** — red banner appears. Overview lamp turns red. Medical response: the event explains
   what triggered it (heart rate z ≈ +20, SpO₂ z ≈ −14, reported shortness of breath), the evidence table shows
   every measurement with device and quality. The procedure is clearly labelled synthetic and contains no
   treatment. Tick two checklist items; add a note.
6. **Earth link down (60 s)** — Mission operations → Earth link **Offline**. Back in the event, **Escalate**. The
   state moves to Escalated; report shows *queued*. Set link **Online** → *transmitted* → *acknowledged* by the
   (simulated) flight-surgeon console. Open the report text.
7. **Explainability (45 s)** — Health analytics → heart rate (resting) with the personal baseline band, alert
   markers, trend analysis; click a point → full provenance (original value/unit, device, received time).
8. **Body systems and science (30 s)** — click lungs/heart on the body map; show hazards, NASA risk titles,
   limitations ("A wrist wearable is not an ECG"), sources with verification status.
9. **Privacy (30 s)** — Run *Behavioral* scenario. `mori` sees "Private behavioral-health follow-up" redacted;
   `ramirez` sees the content; `okafor` sees nothing about other crew.
10. **Close (15 s)** — 46 backend + 9 browser tests, open API at `/api/docs`, knowledge base with 21 traceable
    sources, adapters ready for real devices.
