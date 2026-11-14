// Demo Data panel: generates synthetic history through the simulator (same API path as real devices).
import { useEffect, useState } from "react";
import { LuDatabase } from "react-icons/lu";
import { get, post } from "../lib/api";
import { humanize } from "../lib/format";
import { useApp } from "../lib/store";
import { Drawer, ErrorBox, Field, Tabs, useAsyncAction } from "./ui";

const SITUATIONS: [string, string, string][] = [
  ["nominal", "Normal mission day", "Stable measurements and routine activity — nothing should be flagged."],
  ["sleep_fatigue", "Sleep deprivation and fatigue", "Shorter sleep opportunities, less sleep and rising fatigue over several days."],
  ["cardiovascular", "Cardiovascular change", "Resting heart rate and blood pressure drift upward; palpitations and dizziness reported."],
  ["illness", "Possible illness", "Temperature rises above the personal baseline with sore throat, congestion and fatigue."],
  ["radiation_event", "Radiation exposure event", "A synthetic solar-particle-event profile in area and personal dosimeters."],
  ["musculoskeletal", "Reduced exercise, musculoskeletal concern", "Skipped sessions and declining grip-strength results."],
  ["behavioral", "Behavioral health concern", "Self-reported mood falls and stress rises (private workflow)."],
  ["emergency", "Medical emergency", "Sudden heart-rate rise, SpO₂ fall and breathing symptoms (urgent workflow)."],
];

export function DemoDataButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="chip chip-plain demo-btn" onClick={() => setOpen(true)} title="Generate synthetic demonstration data">
        <LuDatabase aria-hidden /> Demo data
      </button>
      <Drawer open={open} onClose={() => setOpen(false)} title="Demo data">
        {open && <DemoDataPanel onDone={() => setOpen(false)} />}
      </Drawer>
    </>
  );
}

function DemoDataPanel({ onDone }: { onDone: () => void }) {
  // Demo data always applies to the signed-in crew member's own profile (enforced by the server too).
  const { crew, user, navigate, toast, setAstronautId } = useApp();
  const [tab, setTab] = useState("normal");
  const [days, setDays] = useState(7);
  const [situation, setSituation] = useState("sleep_fatigue");
  const [replace, setReplace] = useState(true);
  const own = user?.astronaut_id || null;
  const ownName = crew.find((c) => c.id === own)?.name || user?.display_name;
  const [sim, setSim] = useState<any>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const act = useAsyncAction();
  const running = sim && (sim.state === "running" || sim.state === "paused");

  useEffect(() => {
    let alive = true;
    const tick = () => get("/simulator").then((s) => alive && setSim(s)).catch(() => {});
    tick();
    const t = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const generate = (scenario: string, nDays: number) => act.run(async () => {
    if (running) await post("/simulator/stop");
    if (replace) await post("/simulator/reset");
    const s = await post("/simulator/start", { scenario, speed: 96, days: nDays, seed: Math.floor(Math.random() * 1e9),
      astronaut_id: own });
    setRunId(s.run_id);
    setSim(s);
    toast(`Generating ${humanize(scenario)} data for ${ownName}…`, "info");
  });
  const mine = !!sim && !!runId && sim.run_id === runId;  // only report on the run started from this panel
  const done = mine && sim.state === "completed";
  const go = (page: string) => { onDone(); if (own) setAstronautId(own); navigate(page); };

  return (
    <div className="stack demo-panel">
      <p className="muted">Creates <b>synthetic</b> measurements, check-ins, exercise, nutrition and cabin data and sends them through
        the same pipeline as real devices, so baselines, trends and alerts behave exactly as they would with real input. All
        generated records are labelled SYNTHETIC. Takes about 10–25 seconds.</p>
      <p className="note small">Applies only to <b>your own profile ({ownName})</b>. Other crew members' records are never created, changed or removed. Shared cabin readings are regenerated.</p>
      <Tabs tabs={[["normal", "Random normal data"], ["situation", "Trigger a situation"]]} value={tab} onChange={setTab} />
      {tab === "normal" ? (
        <div className="stack">
          <p>Realistic day-to-day values for your profile with natural variation (new random variation each time).</p>
          <Field label="History to generate">
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} disabled={running}>
              {[3, 7, 10, 14].map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </Field>
          <button className="btn btn-primary" disabled={act.busy || running} onClick={() => generate("nominal", days)}>Generate normal data</button>
        </div>
      ) : (
        <div className="stack">
          <fieldset className="situations" disabled={running}>
            <legend className="field-label">Situation (applied to your profile)</legend>
            {SITUATIONS.map(([id, label, desc]) => (
              <label key={id} className={`situation ${situation === id ? "on" : ""}`}>
                <input type="radio" name="situation" value={id} checked={situation === id} onChange={() => setSituation(id)} />
                <span><strong>{label}</strong><small>{desc}</small></span>
              </label>
            ))}
          </fieldset>
          <button className="btn btn-primary" disabled={act.busy || running} onClick={() => generate(situation, 10)}>Generate 10 days ending in this situation</button>
        </div>
      )}
      <label className="check"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} disabled={running} /> Replace my earlier demo data</label>
      <ErrorBox error={act.error} />
      {running && !mine && <p className="note">Another simulation is running{sim?.started_by ? ` (started by ${sim.started_by.replace(/^user:/, "")})` : ""}. It must finish (or be stopped by whoever started it) first.</p>}
      {mine && (
        <div className="demo-status" role="status">
          <div className="progress"><i style={{ width: `${(sim.progress || 0) * 100}%` }} /></div>
          <p>{running ? `Generating ${humanize(sim.scenario)} — ${Math.round((sim.progress || 0) * 100)}%` :
            done ? `Done: ${humanize(sim.scenario)} — ${sim.counts.observations} measurements, ${sim.counts.alerts} alerts raised.` :
            `Simulator ${humanize(sim.state)}.`}</p>
          {done && (
            <div className="btn-row">
              <button className="btn" onClick={() => go("overview")}>My dashboard</button>
              <button className="btn" onClick={() => go("analytics")}>Health analytics</button>
              <button className="btn" onClick={() => go("response")}>Alerts & response</button>
            </div>
          )}
        </div>
      )}
      <button className="linkish small" disabled={act.busy || running} onClick={() => act.run(async () => { await post("/simulator/reset"); toast("Demo data removed", "ok"); })}>
        Remove my generated demo data
      </button>
    </div>
  );
}
