import { useState } from "react";
import { LuClock, LuDumbbell, LuMoon, LuRadiation, LuWind } from "react-icons/lu";
import { BarChart } from "../components/Charts";
import { ObservationDrawer } from "../components/ObservationDrawer";
import { Chip, Empty, ErrorBox, Loading, Panel, Severity, StatusPill, Synthetic } from "../components/ui";
import { STATUS_INFO, ago, fmtTime, fmtValue, humanize, unit } from "../lib/format";
import { HEALTH_EVENTS, useApp, useData } from "../lib/store";

export default function Overview() {
  const { astronautId, navigate } = useApp();
  const [obs, setObs] = useState<string | null>(null);
  const { data, error, loading, reload } = useData<any>(astronautId ? `/overview?astronaut_id=${astronautId}` : null,
    [...HEALTH_EVENTS, "environment.warning", "environment.event_ended", "sync.updated", "sync.link"], [astronautId]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading mission overview" />;
  const st = STATUS_INFO[data.current_status] || STATUS_INFO.INSUFFICIENT_DATA;
  const a = data.astronaut;
  const sleepBars = [...data.sleep_summary.records].reverse().map((s: any) => {
    const v = s.reported_duration_min ?? s.computed_duration_min;
    return { label: s.sleep_end.slice(5, 10), value: Math.round(v / 6) / 10, tone: "plain",
             title: `${s.sleep_end.slice(0, 10)}: ${fmtValue(v, "min", "sleep_duration")} (scheduled ${s.scheduled_opportunity_min ? fmtValue(s.scheduled_opportunity_min, "min", "sleep_duration") : "n/a"})` };
  });
  const env = data.environment.readings;
  const envPick = (code: string, loc = "HAB-A") => env.find((r: any) => r.metric_code === code && (r.location === loc || !r.location)) || env.find((r: any) => r.metric_code === code);
  return (
    <div className="page overview">
      <section className={`lamp tone-${st.tone}`} aria-live="polite">
        <div className="lamp-light" aria-hidden />
        <div className="lamp-text">
          <span className="lamp-who">{a.name} · {a.crew_role} <Synthetic show={a.is_synthetic} /></span>
          <h1>{st.label}</h1>
          <p>{st.meaning}</p>
          {data.latest_assessment && (
            <p className="lamp-meta">Last assessment {ago(data.latest_assessment.created_at)} · next step: {data.latest_assessment.next_step}</p>
          )}
        </div>
        <div className="lamp-side">
          <button className="btn" onClick={() => navigate("routine")}>Record a measurement</button>
          {data.active_alerts.some((x: any) => x.severity === "URGENT") && <button className="btn btn-urgent" onClick={() => navigate("response")}>Open Medical Response Center</button>}
        </div>
      </section>

      <Panel title="Latest vital signs" actions={<span className="muted">Values with no approved baseline or older than 36 h are shown in grey</span>}>
        <div className="vitals">
          {data.vitals.map((v: any) => {
            const tone = v.status !== "current" ? "none" : v.quality !== "valid" ? "attn" : v.z !== null && Math.abs(v.z) > 2.5 ? "attn" : "ok";
            return (
              <button key={v.metric_code} className={`vital tone-${tone}`} onClick={() => v.observation_id ? setObs(v.observation_id) : navigate("routine")}
                aria-label={`${v.name}: ${v.value ?? v.status}`}>
                <span className="vital-name">{v.name}</span>
                {v.value !== undefined ? (
                  <>
                    <span className="vital-value">{fmtValue(v.value, v.unit, v.metric_code)}<small>{v.metric_code === "sleep_duration" ? "" : unit(v.unit)}</small></span>
                    <span className="vital-meta">
                      {v.baseline ? <>Baseline {fmtValue(v.baseline.mean, v.unit, v.metric_code)} ± {fmtValue(v.baseline.sd, v.unit)}{v.z !== null ? ` · z ${v.z > 0 ? "+" : ""}${v.z}` : ""}</> : "No approved baseline"}
                    </span>
                    <span className="vital-meta"><LuClock aria-hidden /> {ago(v.measured_at)} · {humanize(v.source_type)}{v.device_id ? ` (${v.device_id})` : ""}</span>
                    <span className="vital-tags">
                      {v.status === "stale" && <Chip tone="none">Stale</Chip>}
                      {v.quality !== "valid" && <Chip tone="attn">{v.quality}</Chip>}
                      <Synthetic show={v.is_synthetic} />
                    </span>
                  </>
                ) : (
                  <span className="vital-missing">{v.status === "private" ? "Private — visible to the astronaut and flight surgeon" : v.status === "not_configured" ? v.note : "No measurement recorded"}</span>
                )}
              </button>
            );
          })}
        </div>
      </Panel>

      <div className="grid-2">
        <Panel title={`Active alerts (${data.active_alerts.length})`} actions={<button className="btn btn-quiet" onClick={() => navigate("response")}>Medical response</button>}>
          {data.active_alerts.length === 0 ? <Empty>No open alerts. Alerts appear here when an approved or demonstration rule finds something to review.</Empty> : (
            <ul className="alert-list">
              {data.active_alerts.slice(0, 8).map((x: any) => (
                <li key={x.id} className={`sevbar-${x.severity}`}>
                  <button onClick={() => navigate("response", { alert: x.id })}>
                    <Severity value={x.severity} /> <strong>{x.title}</strong>
                    <span className="muted">{x.category === "environment" ? "Cabin environment" : ""} {ago(x.updated_at)}{x.occurrence_count > 1 ? ` · ${x.occurrence_count} updates` : ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Upcoming assessment tasks" actions={<button className="btn btn-quiet" onClick={() => navigate("routine")}>Daily routine</button>}>
          {data.upcoming_tasks.length === 0 ? <Empty>All scheduled assessments are complete for today.</Empty> : (
            <ul className="task-list">
              {data.upcoming_tasks.map((t: any) => (
                <li key={t.task_code} className={`task-${t.status}`}>
                  <span>{t.title}{t.clinician_directed && <Chip>Clinician-directed</Chip>}</span>
                  <span className="muted">{t.status === "never_recorded" ? "Never recorded" : `${humanize(t.status)} · last ${ago(t.last_recorded_at)}`}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid-3">
        <Panel title={<><LuMoon aria-hidden /> Sleep</>}>
          {sleepBars.length ? <>
            <BarChart bars={sleepBars} unit="h" refLine={{ value: 8.5, label: "8.5 h NASA scheduling reference", tone: "info" }} height={150} />
            <p className="muted small">Mean {fmtValue(data.sleep_summary.mean_duration_min, "min", "sleep_duration")} over the last {sleepBars.length} sleep periods. The 8.5 h line is a crew-scheduling reference (NASA-STD-3001 [V1 6001] rationale), not a diagnostic threshold.</p>
          </> : <Empty>No in-mission sleep records yet.</Empty>}
        </Panel>
        <Panel title={<><LuDumbbell aria-hidden /> Exercise (7 days)</>}>
          {data.exercise_summary.sessions_7d ? (
            <div className="stat-pair">
              <span className="big-value">{Math.round((data.exercise_summary.ratio || 0) * 100)}<small>%</small></span>
              <span>{data.exercise_summary.completed_equivalent} of {data.exercise_summary.sessions_7d} logged sessions completed</span>
              <p className="note">Adherence is not a measurement of bone density. Bone health needs a specialized assessment.</p>
            </div>
          ) : <Empty>No exercise sessions logged in the last 7 days.</Empty>}
        </Panel>
        <Panel title={<><LuWind aria-hidden /> Cabin environment</>} actions={<button className="btn btn-quiet" onClick={() => navigate("environment")}>Details</button>}>
          {env.length === 0 ? <Empty>No environmental sensor data received.</Empty> : (
            <div className="env-mini">
              {[["cabin_co2", "CO₂ (HAB-A)"], ["cabin_temperature", "Temperature"], ["cabin_humidity", "Humidity"], ["radiation_dose_rate", "Dose rate"]].map(([c, l]) => {
                const r = envPick(c);
                return r ? <div key={c}><span>{l}</span><strong>{fmtValue(r.value, r.unit)} {unit(r.unit)}</strong><small>{ago(r.measured_at)}</small></div> : null;
              })}
              {data.environment.open_events.map((e: any) => <div key={e.id} className="env-event"><LuRadiation aria-hidden /> {e.description}</div>)}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="Recent health events">
          {data.recent_events.length === 0 ? <Empty>No medical events recorded.</Empty> : (
            <ul className="event-list">
              {data.recent_events.map((e: any) => (
                <li key={e.id}><button onClick={() => !e.redacted && navigate("response", { event: e.id })} disabled={e.redacted}>
                  <Severity value={e.severity} /> <span>{e.title}</span> <Chip tone={e.state === "RESOLVED" ? "ok" : "attn"}>{humanize(e.state)}</Chip>
                  <span className="muted">{fmtTime(e.opened_at)}</span> <Synthetic show={e.is_synthetic} />
                </button></li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Ground communication">
          <p>Earth link <strong>{data.mission.earth_link_status}</strong>, one-way delay {Math.round(data.mission.comm_delay_seconds)} s.</p>
          <p className="muted">Queue: {Object.entries(data.sync.counts || {}).map(([k, v]) => `${v} ${k}`).join(", ") || "empty"}. ASTRA keeps working when the link is down; reports wait in the queue and are sent when it returns.</p>
        </Panel>
      </div>
      <ObservationDrawer id={obs} onClose={() => setObs(null)} />
    </div>
  );
}
