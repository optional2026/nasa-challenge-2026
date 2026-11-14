import { useState } from "react";
import { LuPause, LuPlay, LuRotateCcw, LuSquare } from "react-icons/lu";
import { Chip, Empty, ErrorBox, Field, KV, Loading, Panel, Synthetic, useAsyncAction } from "../components/ui";
import { post } from "../lib/api";
import { ago, fmtTime, fmtValue, humanize } from "../lib/format";
import { useApp, useData } from "../lib/store";

function Simulator() {
  const { toast } = useApp();
  const { data: s, reload } = useData<any>("/simulator", ["simulator.status", "simulator.reset"]);
  const [scenario, setScenario] = useState("emergency");
  const [speed, setSpeed] = useState(12);
  const [days, setDays] = useState(10);
  const act = useAsyncAction();
  if (!s) return <Loading />;
  const running = s.state === "running", paused = s.state === "paused";
  const call = (path: string, body?: any, msg?: string) => act.run(async () => { await post(`/simulator/${path}`, body); if (msg) toast(msg, "ok"); reload(); });
  return (
    <Panel title={<>Mission simulator <Synthetic /></>} className="sim-panel">
      <p className="muted">Generates coherent synthetic mission data and sends it through the same telemetry and record endpoints that real devices and crew forms use. Every simulated record is labelled SYNTHETIC.</p>
      <div className="form-grid">
        <Field label="Scenario" wide>
          <select value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={running || paused}>
            {Object.entries(s.scenarios).map(([k]) => <option key={k} value={k}>{humanize(k)}</option>)}
          </select>
        </Field>
        <Field label={`Speed: ${speed} simulated hours per second`}>
          <input type="range" min={1} max={96} value={speed} onChange={(e) => setSpeed(Number(e.target.value))}
            onMouseUp={() => (running || paused) && call("speed", { speed })} onKeyUp={() => (running || paused) && call("speed", { speed })} />
        </Field>
        <Field label="Days of mission data"><input type="number" min={2} max={30} value={days} onChange={(e) => setDays(Number(e.target.value))} disabled={running || paused} /></Field>
      </div>
      <p className="scenario-desc">{s.scenarios[running || paused ? s.scenario : scenario]}</p>
      <div className="btn-row">
        <button className="btn btn-primary" disabled={act.busy || running || paused} onClick={() => call("start", { scenario, speed, days }, `Started ${humanize(scenario)} scenario`)}><LuPlay aria-hidden /> Start</button>
        <button className="btn" disabled={act.busy || !running} onClick={() => call("pause")}><LuPause aria-hidden /> Pause</button>
        <button className="btn" disabled={act.busy || !paused} onClick={() => call("resume")}><LuPlay aria-hidden /> Resume</button>
        <button className="btn" disabled={act.busy || !(running || paused)} onClick={() => call("stop", undefined, "Simulator stopped")}><LuSquare aria-hidden /> Stop</button>
        <button className="btn btn-quiet" disabled={act.busy} title="Stops the simulator and deletes every record it generated" onClick={() => call("reset", undefined, "Simulated data removed")}><LuRotateCcw aria-hidden /> Reset simulated data</button>
      </div>
      <ErrorBox error={act.error} />
      <div className="sim-status">
        <div className="progress" role="progressbar" aria-valuenow={Math.round(s.progress * 100)} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${s.progress * 100}%` }} /></div>
        <KV items={[
          ["State", <Chip tone={running ? "ok" : s.state === "error" ? "urgent" : "plain"}>{humanize(s.state)}</Chip>],
          ["Scenario", s.scenario ? humanize(s.scenario) : "—"],
          ["Simulated clock", fmtTime(s.sim_clock)],
          ["Mission elapsed (simulated)", s.mission_elapsed ? `Day ${s.mission_elapsed.mission_day}, ${s.mission_elapsed.hours} h ${s.mission_elapsed.minutes} min` : "—"],
          ["Delivered", `${s.counts.observations} observations · ${s.counts.records} crew records · ${s.counts.telemetry_batches} telemetry batches`],
          ["Rejected by validation", s.counts.rejected],
          ["Alerts raised", s.counts.alerts],
          ["Transport", s.transport || "—"],
        ]} />
        {s.last_error && <div className="note warn">{s.last_error}</div>}
      </div>
    </Panel>
  );
}

function SyncPanel() {
  const { user, toast } = useApp();
  const { data, reload } = useData<any>("/sync", ["sync.updated", "sync.link", "medical_report.created"]);
  const [delay, setDelay] = useState("");
  const act = useAsyncAction();
  if (!data) return <Loading />;
  const setLink = (st: string) => act.run(async () => { await post("/sync/link", { earth_link_status: st, comm_delay_seconds: delay === "" ? null : Number(delay) }); toast(`Earth link set to ${st}`, "ok"); reload(); });
  return (
    <Panel title="Earth link and synchronization">
      <p className="muted">{data.ground_segment}. Items wait in this queue while the link is down and are retried with back-off; each item carries an idempotency key so the ground never receives duplicates.</p>
      <div className="btn-row">
        {["online", "degraded", "offline"].map((st) => (
          <button key={st} className={`btn ${data.earth_link_status === st ? "btn-primary" : ""}`} disabled={act.busy} onClick={() => setLink(st)}>{humanize(st)}</button>
        ))}
        <label className="inline-form">One-way delay (s) <input type="number" min={0} max={3600} placeholder={String(data.comm_delay_seconds)} value={delay} onChange={(e) => setDelay(e.target.value)} style={{ width: 90 }} /></label>
        <button className="btn btn-quiet" onClick={() => act.run(async () => { await post("/sync/run"); reload(); })}>Run sync now</button>
      </div>
      <ErrorBox error={act.error} />
      <KV items={Object.entries(data.counts).map(([k, v]) => [humanize(k), v as any])} />
      {data.items.length === 0 ? <Empty>The outgoing queue is empty.</Empty> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Item</th><th>Status</th><th>Attempts</th><th>Queued</th><th>Delivered</th><th>Acknowledged</th><th></th></tr></thead>
          <tbody>{data.items.map((i: any) => (
            <tr key={i.id}><td>{humanize(i.item_type)} <code>{i.item_id}</code>{i.is_private ? <Chip tone="attn">Private</Chip> : null}</td>
              <td><Chip tone={i.status === "acknowledged" ? "ok" : i.status === "failed" || i.status === "conflict" ? "attn" : "plain"}>{humanize(i.status)}</Chip>{i.last_error && <div className="muted small">{i.last_error}</div>}</td>
              <td>{i.attempts}</td><td>{fmtTime(i.created_at)}</td><td>{fmtTime(i.delivered_at)}</td><td>{i.acknowledged_at ? `${fmtTime(i.acknowledged_at)}` : "—"}</td>
              <td>{(i.status === "failed" || i.status === "conflict") && <button className="btn btn-quiet" onClick={() => act.run(async () => { await post(`/sync/${i.id}/retry`); reload(); })}>Retry</button>}</td></tr>
          ))}</tbody>
        </table></div>
      )}
    </Panel>
  );
}

function Devices() {
  const { data } = useData<any[]>("/devices", ["device.status", "observations.created"]);
  const { data: adapters } = useData<any[]>("/devices/adapters");
  return (
    <Panel title="Devices and adapters">
      {!data ? <Loading /> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Device</th><th>Type</th><th>Assigned to</th><th>Status</th><th>Last data</th><th>Hardware</th></tr></thead>
          <tbody>{data.map((d) => (
            <tr key={d.id}><td><code>{d.id}</code><div className="muted small">{d.model}</div></td><td>{humanize(d.device_type)}</td>
              <td>{d.astronaut_id || d.location || "Shared"}</td><td><span className={`dot dot-${d.status}`} aria-hidden /> {humanize(d.status)}</td>
              <td>{ago(d.last_seen_at)}</td><td>{d.is_simulated ? <Chip tone="plain">Simulated — not validated</Chip> : d.hardware_validated ? "Validated" : "Not validated"}</td></tr>))}</tbody>
        </table></div>
      )}
      <details><summary>Adapter catalogue (for integrating a physical device)</summary>
        {(adapters || []).map((a) => <div key={a.device_type} className="source-entry"><strong>{a.adapter}</strong> → {a.metrics.join(", ")}<pre className="json">{JSON.stringify(a.example_reading, null, 1)}</pre></div>)}
        <p className="muted small">POST a native reading to <code>/api/v1/devices/&lt;id&gt;/readings</code> with the device's <code>X-Device-Key</code>, or send unified observations to <code>/api/v1/telemetry</code>. API reference: <a href="/api/docs" target="_blank" rel="noreferrer">/api/docs</a>.</p>
      </details>
    </Panel>
  );
}

function Baselines() {
  const { astronautId, user, toast } = useApp();
  const medical = user?.role === "medical_officer" || user?.role === "flight_surgeon";
  const { data, reload } = useData<any[]>(astronautId && user?.role !== "admin" ? `/baselines?astronaut_id=${astronautId}` : null, ["baseline.updated"], [astronautId]);
  const [form, setForm] = useState({ metric_code: "heart_rate", context_key: "resting", days: "7" });
  const [lo, setLo] = useState(""); const [hi, setHi] = useState("");
  const act = useAsyncAction();
  if (user?.role === "admin") return null;
  return (
    <Panel title="Individual baselines">
      <p className="muted">Baselines are computed only from measurements marked valid, are versioned, and become active only after approval by medical personnel. New measurements never silently change an approved baseline.</p>
      {!data ? <Loading /> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Indicator</th><th>Version</th><th>Status</th><th>Mean ± SD (n)</th><th>Period</th><th>Source</th><th>Approved by</th><th></th></tr></thead>
          <tbody>{data.map((b) => (
            <tr key={b.id}><td>{humanize(b.metric_code)}{b.context_key ? ` (${humanize(b.context_key)})` : ""}</td><td>v{b.version}</td>
              <td><Chip tone={b.status === "approved" ? "ok" : b.status === "draft" ? "attn" : "plain"}>{humanize(b.status)}</Chip></td>
              <td>{fmtValue(b.mean)} ± {fmtValue(b.sd)} ({b.n})</td><td className="small">{fmtTime(b.period_start)} – {fmtTime(b.period_end)}</td>
              <td>{humanize(b.source)} <Synthetic show={b.is_synthetic} /></td><td>{b.approved_by || "—"}{b.ref_low !== null ? <div className="small">range {b.ref_low}–{b.ref_high}</div> : null}</td>
              <td>{medical && b.status === "draft" && <button className="btn btn-quiet" onClick={() => act.run(async () => {
                await post(`/baselines/${b.id}/approve`, { ref_low: lo === "" ? null : Number(lo), ref_high: hi === "" ? null : Number(hi) }); toast("Baseline approved", "ok"); reload(); })}>Approve</button>}</td></tr>))}</tbody>
        </table></div>
      )}
      {medical && (
        <form className="inline-form wrap" onSubmit={(e) => { e.preventDefault(); act.run(async () => {
          await post("/baselines", { astronaut_id: astronautId, metric_code: form.metric_code, context_key: form.context_key,
            period_start: new Date(Date.now() - Number(form.days) * 864e5).toISOString(), period_end: new Date().toISOString(), source: "in_flight_window" });
          toast("Draft baseline proposed", "ok"); reload(); }); }}>
          <span>Propose from the last</span><input type="number" min={1} max={90} value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} style={{ width: 70 }} /><span>days of</span>
          <select value={form.metric_code} onChange={(e) => setForm({ ...form, metric_code: e.target.value, context_key: e.target.value === "heart_rate" ? "resting" : "" })}>
            {["heart_rate", "bp_systolic", "bp_diastolic", "spo2", "respiratory_rate", "body_temperature", "sleep_duration"].map((m) => <option key={m} value={m}>{humanize(m)}</option>)}
          </select>
          <button className="btn">Propose draft</button>
          <span className="muted small">Optional reference range when approving:</span>
          <input placeholder="low" value={lo} onChange={(e) => setLo(e.target.value)} style={{ width: 70 }} /><input placeholder="high" value={hi} onChange={(e) => setHi(e.target.value)} style={{ width: 70 }} />
        </form>
      )}
      <ErrorBox error={act.error} />
    </Panel>
  );
}

function Audit() {
  const { user } = useApp();
  const allowed = user?.role === "admin" || user?.role === "flight_surgeon";
  const { data } = useData<any[]>(allowed ? "/audit?limit=60" : null, ["alert.created", "medical_event.updated", "sync.updated"]);
  if (!allowed) return null;
  return (
    <Panel title="Audit log (latest 60)">
      {!data ? <Loading /> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th></tr></thead>
          <tbody>{data.map((r) => <tr key={r.id}><td>{fmtTime(r.at)}</td><td>{r.actor}</td><td>{r.action}</td><td>{r.entity_type} {r.entity_id && <code>{r.entity_id}</code>}</td></tr>)}</tbody>
        </table></div>
      )}
    </Panel>
  );
}

export default function Operations() {
  return (
    <div className="page ops">
      <div className="grid-2"><Simulator /><SyncPanel /></div>
      <Devices />
      <Baselines />
      <Audit />
    </div>
  );
}
