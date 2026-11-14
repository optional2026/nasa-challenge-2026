import { useMemo, useState } from "react";
import { LuLock, LuPlug } from "react-icons/lu";
import { Chip, Empty, ErrorBox, Field, Loading, Panel, Scale, Tabs, useAsyncAction } from "../components/ui";
import { submitWithOutbox } from "../lib/api";
import { ago, fmtTime, humanize } from "../lib/format";
import { HEALTH_EVENTS, useApp, useData } from "../lib/store";
import { MeasureGuide } from "../components/MeasureGuide";

const nowLocal = () => { const d = new Date(); d.setSeconds(0, 0); return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16); };
const toIso = (local: string) => new Date(local).toISOString();

const SCALES = {
  mood: ["Very low", "Low", "Neutral", "Good", "Very good"],
  stress: ["Very low", "Low", "Moderate", "High", "Very high"],
  fatigue: ["Fully rested", "Slightly tired", "Moderately tired", "Very tired", "Exhausted"],
  sleep: ["Very poor", "Poor", "Fair", "Good", "Very good"],
  workload: ["Very light", "Light", "Moderate", "Heavy", "Very heavy"],
  connected: ["Very disconnected", "Somewhat disconnected", "Neutral", "Connected", "Very connected"],
};

function Result({ res }: { res: any }) {
  if (!res) return null;
  if (res.queued) return <div className="note warn">The onboard server could not be reached. The entry is saved on this device and will be sent automatically when the connection returns.</div>;
  const r = res.result?.ingestion || res.result;
  const acc = r?.accepted?.length ?? 0, rej = r?.rejected || [];
  return (
    <div className={`note ${rej.length ? "warn" : "ok"}`} role="status">
      {res.result?.duplicate ? "Already saved earlier — no duplicate created." : `Saved ${acc} measurement${acc === 1 ? "" : "s"}.`}
      {rej.length > 0 && <ul>{rej.map((x: any, i: number) => <li key={i}>Not saved: {x.errors.join("; ")}</li>)}</ul>}
      {r?.alerts_created?.length > 0 && <div>The assessment engine raised {r.alerts_created.length} new alert(s). See Medical response.</div>}
    </div>
  );
}

function useSymptoms() {
  const { data } = useData<any[]>("/symptoms");
  return data || [];
}

function SymptomPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const vocab = useSymptoms();
  return (
    <details className="symptom-picker">
      <summary>Symptoms ({value.length ? value.map(humanize).join(", ") : "none"})</summary>
      <div className="chips">
        {vocab.map((s) => (
          <button type="button" key={s.code} className={`chip ${value.includes(s.code) ? "chip-on" : "chip-plain"}`}
            onClick={() => onChange(value.includes(s.code) ? value.filter((x) => x !== s.code) : [...value, s.code])}>{s.label}</button>
        ))}
      </div>
    </details>
  );
}

const VITALS = [
  { id: "bp", title: "Blood pressure", device: "blood_pressure_monitor",
    fields: [{ code: "bp_systolic", label: "Systolic", units: ["mmHg"] }, { code: "bp_diastolic", label: "Diastolic", units: ["mmHg"] }],
    contexts: ["resting", "after_exercise", "standing"], ctxKey: "activity", help: "Rest quietly first and stay still during the reading." },
  { id: "hr", title: "Heart rate", device: "heart_rate_wearable", fields: [{ code: "heart_rate", label: "Heart rate", units: ["bpm"] }],
    contexts: ["resting", "exercise", "post_exercise"], ctxKey: "activity", help: "Resting values are compared with your resting baseline." },
  { id: "spo2", title: "Oxygen saturation", device: "pulse_oximeter", fields: [{ code: "spo2", label: "SpO₂", units: ["%"] }],
    contexts: ["resting", "after_exercise"], ctxKey: "activity", help: "Keep the finger warm and still until the reading is stable." },
  { id: "temp", title: "Body temperature", device: "thermometer", fields: [{ code: "body_temperature", label: "Temperature", units: ["degC", "degF"] }],
    contexts: ["oral", "tympanic", "skin"], ctxKey: "method", help: "Use the same method each time. °F is converted to °C; your entry is kept as typed." },
  { id: "glu", title: "Blood glucose", device: "glucose_monitor", fields: [{ code: "blood_glucose", label: "Glucose", units: ["mg/dL", "mmol/L"] }],
    contexts: ["fasting", "before_meal", "after_meal", "after_exercise"], ctxKey: "meal_context", help: "Clinician-directed measurement." },
  { id: "rr", title: "Respiratory rate", device: null, fields: [{ code: "respiratory_rate", label: "Breaths per minute", units: ["breaths/min"] }],
    contexts: ["counted", "wearable_estimate"], ctxKey: "method", help: "Count breaths for a full minute while resting." },
];

function VitalForm({ cfg, devices, astronautId }: { cfg: any; devices: any[]; astronautId: string }) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [unitSel, setUnitSel] = useState<string>(cfg.fields[0].units[0]);
  const [time, setTime] = useState(nowLocal());
  const [source, setSource] = useState("manual");
  const [device, setDevice] = useState("");
  const [quality, setQuality] = useState("unverified");
  const [ctx, setCtx] = useState(cfg.contexts[0]);
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [res, setRes] = useState<any>(null);
  const act = useAsyncAction();
  const devs = devices.filter((d) => d.device_type === cfg.device);
  const submit = (e: any) => {
    e.preventDefault();
    act.run(async () => {
      const body: any = {
        astronaut_id: astronautId, measured_at: toIso(time), source_type: source, device_id: source === "medical_device" ? device || null : null,
        quality, context: { [cfg.ctxKey]: ctx }, notes: notes || null, method: cfg.ctxKey === "method" ? ctx : undefined,
        items: cfg.fields.map((f: any) => ({ metric_code: f.code, value: Number(vals[f.code]), unit: f.units.length > 1 ? unitSel : f.units[0] })),
        symptoms: symptoms.map((c) => ({ code: c })),
      };
      const r = await submitWithOutbox("/measurements/manual", body);
      setRes(r);
      if (!r.queued) { setVals({}); setSymptoms([]); setNotes(""); }
    });
  };
  return (
    <form className="form-card" onSubmit={submit} aria-label={cfg.title}>
      <h3>{cfg.title}</h3>
      <p className="muted small">{cfg.help}</p>
      <MeasureGuide id={cfg.id} />
      <div className="form-grid">
        {cfg.fields.map((f: any) => (
          <Field key={f.code} label={f.label}>
            <div className="inline-form">
              <input type="number" step="any" required inputMode="decimal" value={vals[f.code] || ""} onChange={(e) => setVals({ ...vals, [f.code]: e.target.value })} />
              {f.units.length > 1 ? (
                <select value={unitSel} onChange={(e) => setUnitSel(e.target.value)} aria-label="Unit">{f.units.map((u: string) => <option key={u} value={u}>{u.replace("deg", "°")}</option>)}</select>
              ) : <span className="unit">{f.units[0]}</span>}
            </div>
          </Field>
        ))}
        <Field label="Measured at (your local time)"><input type="datetime-local" value={time} onChange={(e) => setTime(e.target.value)} required /></Field>
        <Field label={humanize(cfg.ctxKey)}>
          <select value={ctx} onChange={(e) => setCtx(e.target.value)}>{cfg.contexts.map((c: string) => <option key={c} value={c}>{humanize(c)}</option>)}</select>
        </Field>
        <Field label="Measured with">
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="manual">Manual / not recorded</option>
            {cfg.device && <option value="medical_device">Medical device</option>}
          </select>
        </Field>
        {source === "medical_device" && (
          <Field label="Device"><select value={device} onChange={(e) => setDevice(e.target.value)} required>
            <option value="">Choose…</option>{devs.map((d) => <option key={d.id} value={d.id}>{d.id} · {d.model}</option>)}
          </select></Field>
        )}
        <Field label="Measurement quality">
          <select value={quality} onChange={(e) => setQuality(e.target.value)}>
            <option value="valid">Good — taken as instructed</option>
            <option value="unverified">Not sure</option>
            <option value="questionable">Questionable (movement, poor contact…)</option>
          </select>
        </Field>
      </div>
      <SymptomPicker value={symptoms} onChange={setSymptoms} />
      <Field label="Notes (optional)"><input value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <ErrorBox error={act.error} />
      <Result res={res} />
      <button className="btn btn-primary" disabled={act.busy}>{act.busy ? "Saving…" : `Save ${cfg.title.toLowerCase()}`}</button>
    </form>
  );
}

function SymptomForm({ astronautId }: { astronautId: string }) {
  const [codes, setCodes] = useState<string[]>([]);
  const [sev, setSev] = useState(2);
  const [time, setTime] = useState(nowLocal());
  const [notes, setNotes] = useState("");
  const [res, setRes] = useState<any>(null);
  const act = useAsyncAction();
  return (
    <form className="form-card" onSubmit={(e) => { e.preventDefault(); act.run(async () => {
      const r = await submitWithOutbox("/measurements/manual", { astronaut_id: astronautId, measured_at: toIso(time), quality: "unverified",
        context: { severity: sev }, notes: notes || null, items: codes.map((c) => ({ metric_code: "symptom", value: c, unit: "category" })) });
      setRes(r); if (!r.queued) setCodes([]);
    }); }}>
      <h3>Report symptoms</h3>
      <p className="muted small">Symptoms are evaluated together with your measurements. Reported vision changes are always referred for a clinician eye examination.</p>
      <SymptomPicker value={codes} onChange={setCodes} />
      <div className="form-grid">
        <Field label="Severity (1 mild – 5 severe)"><input type="number" min={1} max={5} value={sev} onChange={(e) => setSev(Number(e.target.value))} /></Field>
        <Field label="Started at"><input type="datetime-local" value={time} onChange={(e) => setTime(e.target.value)} /></Field>
      </div>
      <Field label="Description (optional)"><input value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <ErrorBox error={act.error} /><Result res={res} />
      <button className="btn btn-primary" disabled={!codes.length || act.busy}>Report {codes.length || ""} symptom{codes.length === 1 ? "" : "s"}</button>
    </form>
  );
}

function SleepForm({ astronautId }: { astronautId: string }) {
  const y = new Date(Date.now() - 9 * 3600e3);
  const [start, setStart] = useState(new Date(y.getTime() - y.getTimezoneOffset() * 6e4).toISOString().slice(0, 16));
  const [end, setEnd] = useState(nowLocal());
  const [corrected, setCorrected] = useState("");
  const [quality, setQuality] = useState<number | null>(null);
  const [awakenings, setAwakenings] = useState("");
  const [rest, setRest] = useState<number | null>(null);
  const [fatigue, setFatigue] = useState<number | null>(null);
  const [opp, setOpp] = useState("8.5");
  const [res, setRes] = useState<any>(null);
  const act = useAsyncAction();
  const computed = (new Date(end).getTime() - new Date(start).getTime()) / 6e4;
  return (
    <form className="form-card" onSubmit={(e) => { e.preventDefault(); act.run(async () => {
      setRes(await submitWithOutbox("/sleep", { astronaut_id: astronautId, sleep_start: toIso(start), sleep_end: toIso(end),
        corrected_duration_min: corrected ? Number(corrected) * 60 : null, quality, awakenings: awakenings === "" ? null : Number(awakenings),
        restfulness: rest, fatigue_after_waking: fatigue, scheduled_opportunity_min: opp ? Number(opp) * 60 : null }));
    }); }}>
      <h3>Sleep</h3>
      <MeasureGuide id="sleep" />
      <div className="form-grid">
        <Field label="Fell asleep"><input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
        <Field label="Woke up"><input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} required /></Field>
        <Field label="Calculated duration"><output>{computed > 0 ? `${Math.floor(computed / 60)} h ${Math.round(computed % 60)} min` : "Check the times"}</output></Field>
        <Field label="Actual sleep if interrupted (hours)" hint="Leave empty to use the calculated duration"><input type="number" step="0.1" min={0} max={24} value={corrected} onChange={(e) => setCorrected(e.target.value)} /></Field>
        <Field label="Awakenings (if known)"><input type="number" min={0} value={awakenings} onChange={(e) => setAwakenings(e.target.value)} /></Field>
        <Field label="Scheduled sleep period (hours)" hint="From the mission schedule. NASA's scheduling reference is 8.5 h."><input type="number" step="0.25" value={opp} onChange={(e) => setOpp(e.target.value)} /></Field>
      </div>
      <Field label="Sleep quality"><Scale labels={SCALES.sleep} value={quality} onChange={setQuality} name="Sleep quality" /></Field>
      <Field label="How rested do you feel?"><Scale labels={SCALES.sleep} value={rest} onChange={setRest} name="Restfulness" /></Field>
      <Field label="Fatigue after waking"><Scale labels={SCALES.fatigue} value={fatigue} onChange={setFatigue} name="Fatigue" /></Field>
      <ErrorBox error={act.error} /><Result res={res} />
      <button className="btn btn-primary" disabled={act.busy}>Save sleep</button>
    </form>
  );
}

function CheckinForm({ astronautId, self }: { astronautId: string; self: boolean }) {
  const [v, setV] = useState<Record<string, number | null>>({ mood: null, stress: null, fatigue: null, sleep_rating: null, workload: null, connectedness: null });
  const [note, setNote] = useState("");
  const [priv, setPriv] = useState("");
  const [pvt, setPvt] = useState("");
  const [res, setRes] = useState<any>(null);
  const act = useAsyncAction();
  if (!self) return <div className="note"><LuLock aria-hidden /> The private check-in can only be completed by the astronaut. Behavioral-health answers are not shown to other crew members.</div>;
  const set = (k: string) => (x: number | null) => setV({ ...v, [k]: x });
  return (
    <form className="form-card private" onSubmit={(e) => { e.preventDefault(); act.run(async () => {
      setRes(await submitWithOutbox("/mood", { astronaut_id: astronautId, assessed_at: new Date().toISOString(), ...v,
        note_for_medical: note || null, private_note: priv || null, cognitive_pvt_rt_ms: pvt ? Number(pvt) : null }));
      setNote(""); setPriv("");
    }); }}>
      <h3><LuLock aria-hidden /> Private daily check-in</h3>
      <p className="muted small">Only you and the flight surgeon can see your answers. Skip anything you prefer not to answer — skipped answers are recorded as missing, never as "fine". These are self-reported indicators, not a diagnosis.</p>
      <MeasureGuide id="mood" />
      <Field label="How is your mood today?"><Scale labels={SCALES.mood} value={v.mood} onChange={set("mood")} name="Mood" /></Field>
      <Field label="How stressed do you feel?"><Scale labels={SCALES.stress} value={v.stress} onChange={set("stress")} name="Stress" /></Field>
      <Field label="How tired are you?"><Scale labels={SCALES.fatigue} value={v.fatigue} onChange={set("fatigue")} name="Fatigue" /></Field>
      <Field label="How well did you sleep?"><Scale labels={SCALES.sleep} value={v.sleep_rating} onChange={set("sleep_rating")} name="Sleep" /></Field>
      <Field label="How mentally demanding was today's workload?"><Scale labels={SCALES.workload} value={v.workload} onChange={set("workload")} name="Workload" /></Field>
      <Field label="Do you feel socially connected to the crew?"><Scale labels={SCALES.connected} value={v.connectedness} onChange={set("connectedness")} name="Connectedness" /></Field>
      <Field label="Is there anything you want medical support to know?" hint="Sent privately to the flight surgeon. Requires an answer to the mood question.">
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <Field label="Private note to yourself (optional)"><textarea rows={2} value={priv} onChange={(e) => setPriv(e.target.value)} /></Field>
      <Field label="Reaction-time test result, mean ms (optional)"><input type="number" min={100} max={5000} value={pvt} onChange={(e) => setPvt(e.target.value)} /></Field>
      <ErrorBox error={act.error} /><Result res={res} />
      <button className="btn btn-primary" disabled={act.busy}>Save check-in</button>
    </form>
  );
}

function ExerciseForm({ astronautId }: { astronautId: string }) {
  const [f, setF] = useState<any>({ exercise_type: "Treadmill aerobic session", category: "aerobic", duration: "45", intensity: "moderate", status: "completed", notes: "", test: "", testVal: "", testUnit: "kg", pain: "" });
  const [time, setTime] = useState(nowLocal());
  const [res, setRes] = useState<any>(null);
  const act = useAsyncAction();
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <form className="form-card" onSubmit={(e) => { e.preventDefault(); act.run(async () => {
      setRes(await submitWithOutbox("/exercise", { astronaut_id: astronautId, exercise_type: f.exercise_type, category: f.category, start_at: toIso(time),
        duration_min: f.status === "skipped" || f.duration === "" ? null : Number(f.duration), intensity: f.status === "skipped" ? null : f.intensity,
        completion_status: f.status, performance_notes: f.notes || null, pain_score: f.pain === "" ? null : Number(f.pain),
        performance_test: f.test && f.testVal ? { test: f.test, value: Number(f.testVal), unit: f.testUnit } : null }));
    }); }}>
      <h3>Exercise session</h3>
      <MeasureGuide id="exercise" />
      <div className="form-grid">
        <Field label="Exercise"><input value={f.exercise_type} onChange={set("exercise_type")} required /></Field>
        <Field label="Type"><select value={f.category} onChange={set("category")}>{["aerobic", "resistive", "flexibility", "balance", "other"].map((c) => <option key={c} value={c}>{humanize(c)}</option>)}</select></Field>
        <Field label="Started"><input type="datetime-local" value={time} onChange={(e) => setTime(e.target.value)} /></Field>
        <Field label="Duration (min)"><input type="number" min={0} max={300} value={f.duration} onChange={set("duration")} /></Field>
        <Field label="Intensity"><select value={f.intensity} onChange={set("intensity")}>{["low", "moderate", "high", "max"].map((c) => <option key={c} value={c}>{humanize(c)}</option>)}</select></Field>
        <Field label="Completion"><select value={f.status} onChange={set("status")}>{["completed", "partial", "skipped"].map((c) => <option key={c} value={c}>{humanize(c)}</option>)}</select></Field>
        <Field label="Performance test (optional)"><select value={f.test} onChange={set("test")}><option value="">None</option><option value="grip_strength">Grip strength</option><option value="sit_to_stand_30s">30-s sit-to-stand</option></select></Field>
        {f.test && <Field label="Result"><div className="inline-form"><input type="number" step="any" value={f.testVal} onChange={set("testVal")} />
          <select value={f.testUnit} onChange={set("testUnit")}><option value="kg">kg</option><option value="count">count</option><option value="s">s</option></select></div></Field>}
        <Field label="Pain 0–10 (optional)"><input type="number" min={0} max={10} value={f.pain} onChange={set("pain")} /></Field>
      </div>
      <Field label="Notes"><input value={f.notes} onChange={set("notes")} /></Field>
      <p className="muted small">Exercise records show adherence. They do not measure bone density — that needs a specialized assessment.</p>
      <ErrorBox error={act.error} /><Result res={res} />
      <button className="btn btn-primary" disabled={act.busy}>Save exercise</button>
    </form>
  );
}

function NutritionForm({ astronautId }: { astronautId: string }) {
  const [type, setType] = useState("water");
  const [water, setWater] = useState("250");
  const [desc, setDesc] = useState("");
  const [kcal, setKcal] = useState("");
  const [appetite, setAppetite] = useState<number | null>(null);
  const [dig, setDig] = useState("");
  const [time, setTime] = useState(nowLocal());
  const [res, setRes] = useState<any>(null);
  const act = useAsyncAction();
  return (
    <form className="form-card" onSubmit={(e) => { e.preventDefault(); act.run(async () => {
      setRes(await submitWithOutbox("/nutrition", { astronaut_id: astronautId, recorded_at: toIso(time), record_type: type,
        water_ml: water === "" ? null : Number(water), description: desc || null, energy_kcal: kcal === "" ? null : Number(kcal),
        appetite, digestion_symptoms: dig || null }));
    }); }}>
      <h3>Food and water</h3>
      <MeasureGuide id="nutrition" />
      <div className="form-grid">
        <Field label="Entry"><select value={type} onChange={(e) => setType(e.target.value)}><option value="water">Drink</option><option value="meal">Meal</option><option value="snack">Snack</option></select></Field>
        <Field label="Time"><input type="datetime-local" value={time} onChange={(e) => setTime(e.target.value)} /></Field>
        <Field label="Water / fluid (mL)"><input type="number" min={0} value={water} onChange={(e) => setWater(e.target.value)} required={type === "water"} /></Field>
        {type !== "water" && <Field label="Food (as listed on package)"><input value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>}
        {type !== "water" && <Field label="Energy (kcal, if known)"><input type="number" min={0} value={kcal} onChange={(e) => setKcal(e.target.value)} /></Field>}
        <Field label="Digestion symptoms (optional)"><input value={dig} onChange={(e) => setDig(e.target.value)} /></Field>
      </div>
      <Field label="Appetite (optional)"><Scale labels={["Very poor", "Poor", "Normal", "Good", "Very good"]} value={appetite} onChange={setAppetite} name="Appetite" /></Field>
      <ErrorBox error={act.error} /><Result res={res} />
      <button className="btn btn-primary" disabled={act.busy}>Save entry</button>
    </form>
  );
}

/** Placeholder only: no device integration exists and nothing is shown as connected. */
function HardwareLinkPlaceholder() {
  return (
    <section className="hardware-soon" aria-labelledby="hw-title">
      <LuPlug className="hardware-soon-icon" aria-hidden />
      <div>
        <h3 id="hw-title">Hardware Integration — Coming Soon</h3>
        <p>Connect supported medical devices and wearable sensors to automatically transfer measurements into ASTRA. Hardware
          integration is not currently available in this demonstration.</p>
      </div>
    </section>
  );
}

export default function Routine() {
  const { astronautId, user, route } = useApp();
  const [tab, setTab] = useState(route.params.tab || "vitals");
  const { data, error, reload } = useData<any>(astronautId ? `/routine?astronaut_id=${astronautId}` : null, [...HEALTH_EVENTS, "device.status"], [astronautId]);
  const { data: ast } = useData<any>(astronautId ? `/astronauts/${astronautId}` : null, [], [astronautId]);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => new Date(Date.now() - (6 - i) * 864e5).toISOString().slice(0, 10)), []);
  if (!astronautId) return <Empty>Select an astronaut.</Empty>;
  const self = user?.astronaut_id === astronautId;
  const glucose = ast?.glucose_monitoring_enabled;
  return (
    <div className="page routine">
      <div className="grid-2 routine-top">
        <Panel title={`Today's assessments (${data?.date_utc || ""} UTC)`}>
          {error && <ErrorBox error={error} onRetry={reload} />}
          {!data ? <Loading /> : (
            <ul className="task-list">
              {data.tasks.map((t: any) => (
                <li key={t.task_code} className={`task-${t.status}`}>
                  <span>{t.title} {!t.required && <Chip>Optional</Chip>} {t.clinician_directed && <Chip>Clinician-directed</Chip>}</span>
                  <span className="muted">{t.status === "done" ? `Done · ${ago(t.last_recorded_at)}` : t.status === "never_recorded" ? "Never recorded" : `${humanize(t.status)} · last ${ago(t.last_recorded_at)}`}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Devices">
          {!data ? <Loading /> : (
            <ul className="device-list">
              {data.devices.map((d: any) => (
                <li key={d.id}><span className={`dot dot-${d.status}`} aria-hidden /> <span>{d.model}</span>
                  <span className="muted">{humanize(d.status)} · seen {ago(d.last_seen_at)}{d.battery_pct !== null ? ` · ${Math.round(d.battery_pct)}%` : ""}</span>
                  {d.is_simulated && <Chip tone="plain" title="No physical hardware has been tested with ASTRA">Simulated</Chip>}</li>
              ))}
            </ul>
          )}
          <p className="muted small">ASTRA accepts device data through device adapters and the telemetry API. No physical device has been validated; all devices listed are simulated.</p>
        </Panel>
      </div>
      <Panel title="Completion history (7 days)">
        {data && (
          <div className="table-wrap"><table className="history-grid">
            <thead><tr><th>Assessment</th>{days.map((d) => <th key={d}>{d.slice(5)}</th>)}</tr></thead>
            <tbody>{data.tasks.map((t: any) => (
              <tr key={t.task_code}><td>{t.title}</td>{days.map((d) => <td key={d} className={t.completion_history[d] ? "done" : "none"}>{t.completion_history[d] ? "✓" : "–"}</td>)}</tr>
            ))}</tbody>
          </table></div>
        )}
      </Panel>
      {user?.role === "admin" ? (
        <Panel title="Record">
          <div className="note">Read-only: administrators can review the routine but cannot record measurements for crew members.</div>
        </Panel>
      ) : (
      <Panel title="Record">
        <Tabs tabs={[["vitals", "Vital signs"], ["symptoms", "Symptoms"], ["sleep", "Sleep"], ["checkin", "Private check-in"], ["exercise", "Exercise"], ["nutrition", "Food and water"],
          ["hardware", <span className="tab-icon"><LuPlug aria-hidden /> Hardware link</span>]]} value={tab} onChange={setTab} />
        {!self && user?.role !== "astronaut" && tab !== "hardware" && <div className="note">You are recording on behalf of {ast?.name}. Entries are attributed to you in the audit log.</div>}
        {tab === "hardware" && <HardwareLinkPlaceholder />}
        <div className="forms">
          {tab === "vitals" && VITALS.filter((v) => v.id !== "glu" || glucose).map((v) => <VitalForm key={v.id} cfg={v} devices={data?.devices || []} astronautId={astronautId} />)}
          {tab === "vitals" && !glucose && <div className="note">Blood glucose monitoring is clinician-directed and not enabled for this astronaut.</div>}
          {tab === "symptoms" && <SymptomForm astronautId={astronautId} />}
          {tab === "sleep" && <SleepForm astronautId={astronautId} />}
          {tab === "checkin" && <CheckinForm astronautId={astronautId} self={self} />}
          {tab === "exercise" && <ExerciseForm astronautId={astronautId} />}
          {tab === "nutrition" && <NutritionForm astronautId={astronautId} />}
        </div>
      </Panel>
      )}
    </div>
  );
}
