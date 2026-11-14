// Crew overview for the Crew Medical Officer (own crew) and the ground flight surgeon (whole mission).
// The server decides which astronauts are included; private check-in content is never shown here.
import { useState } from "react";
import { Avatar, Chip, Empty, ErrorBox, Loading, Panel, Severity, StatusPill } from "../components/ui";
import { ago, fmtTime, fmtValue, unit } from "../lib/format";
import { HEALTH_EVENTS, useApp, useData } from "../lib/store";

const SHORT: Record<string, string> = {
  heart_rate: "HR", bp_systolic: "SYS", bp_diastolic: "DIA", spo2: "SpO₂", respiratory_rate: "RR", body_temperature: "Temp",
};

// Grouping of the assessment engine's statuses (server-provided `category`); no thresholds are computed here.
const CATEGORY: Record<string, { label: string; tone: string }> = {
  ok: { label: "No current concern", tone: "ok" }, attention: { label: "Needs attention", tone: "attn" },
  medical_review: { label: "Medical review", tone: "urgent" }, no_data: { label: "Insufficient data", tone: "none" },
};

export default function CrewOverview() {
  const { setAstronautId, navigate, user } = useApp();
  const { data, error, reload } = useData<any>("/crew/overview", HEALTH_EVENTS);
  const [filter, setFilter] = useState<string>("all");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading crew overview" />;
  const open = (id: string, page = "overview") => { setAstronautId(id); navigate(page); };
  const s = data.summary;
  const tiles: [string, string, number, string][] = [
    ["all", "Crew members", s.total, "plain"], ["ok", "No current concern", s.no_concern, "ok"],
    ["attention", "Need attention", s.attention, "attn"], ["medical_review", "Need medical review", s.medical_review, "urgent"],
    ["no_data", "Insufficient / no data", s.no_data, "none"], ["alerts", "With active alerts", s.with_active_alerts, "review"],
  ];
  const shown = data.crew.filter((c: any) => filter === "all" || (filter === "alerts" ? c.open_alerts.total > 0 : c.category === filter));

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Crew overview</h1>
        <p className="muted">{data.scope === "crew" ? <>Health status of every astronaut assigned to <b>{data.crew_name || "your crew"}</b></> : <>All astronauts on the mission</>} · {data.mission.name} · Day {data.mission.mission_day}
          {" · "}last update {s.last_update_at ? ago(s.last_update_at) : "never"}
          {user?.role === "admin" && <> · <b>read-only</b> (administrator)</>}</p>
      </div>
      <div className="crew-summary" role="group" aria-label="Crew status summary (click to filter)">
        {tiles.map(([k, label, n, tone]) => (
          <button key={k} className={`crew-tile tone-${tone} ${filter === k ? "on" : ""}`} aria-pressed={filter === k} onClick={() => setFilter(filter === k && k !== "all" ? "all" : k)}>
            <b>{n}</b><span>{label}</span>
          </button>
        ))}
      </div>
      {data.crew.length === 0 ? <Empty>No astronauts are assigned to your crew.</Empty> : shown.length === 0 ? <Empty>No crew member matches this filter.</Empty> : (
        <div className="crew-grid">
          {shown.map((c: any) => {
            const a = c.astronaut;
            const cat = CATEGORY[c.category] || CATEGORY.no_data;
            return (
              <Panel key={a.id} className={`crew-card cat-${c.category}`} title={
                <button className="crew-card-h linkish-plain" onClick={() => open(a.id)} title={`Open ${a.name}'s dashboard`}>
                  <Avatar name={a.name} seed={a.id} size={36} />
                  <span><strong>{a.name}</strong>{a.is_self && <Chip>you</Chip>}<small className="muted">{a.crew_role}{a.call_sign ? ` · ${a.call_sign}` : ""} · {a.crew}</small></span>
                </button>}
                actions={<><Chip tone={cat.tone}>{c.has_data ? cat.label : "NO DATA"}</Chip><StatusPill status={c.current_status} /></>}>
                {a.account_active === false && <p className="note warn small">Account deactivated — records retained.</p>}
                <p className="muted small">Last measurement: {c.last_measured_at ? `${ago(c.last_measured_at)} (${fmtTime(c.last_measured_at)})` : "none recorded"}</p>
                <div className="crew-vitals">
                  {c.vitals.map((v: any) => (
                    <div key={v.metric_code} className={`crew-vital ${v.status}`} title={`${v.name}${v.measured_at ? ` · ${ago(v.measured_at)}` : ""}`}>
                      <span className="k">{SHORT[v.metric_code] || v.name}</span>
                      <span className="v">{v.status === "missing" ? "—" : <>{fmtValue(v.value, v.unit, v.metric_code)}<small>{unit(v.unit)}</small></>}</span>
                      {v.z !== null && v.z !== undefined && Math.abs(v.z) >= 2 && <span className="z" title="Standard deviations from the approved personal baseline">{v.z > 0 ? "+" : ""}{v.z}σ</span>}
                      {v.status === "stale" && <span className="z">stale</span>}
                    </div>
                  ))}
                </div>
                <div className="crew-meta">
                  <span>{c.open_alerts.total === 0 ? <span className="muted">No open alerts</span> :
                    Object.entries(c.open_alerts.by_severity).map(([s, n]) => <span key={s}><Severity value={s} /> ×{n as number} </span>)}
                    {c.open_alerts.private_redacted > 0 && <small className="muted"> ({c.open_alerts.private_redacted} private, redacted)</small>}</span>
                  <span>{c.open_medical_events} open medical event{c.open_medical_events === 1 ? "" : "s"}</span>
                  <span className={c.routine.overdue ? "attn" : ""}>Routine: {c.routine.overdue} overdue · {c.routine.due} due of {c.routine.total_required}</span>
                  <span className="muted">Last assessment: {c.latest_assessment ? ago(c.latest_assessment.created_at) : "none"}</span>
                </div>
                <div className="btn-row">
                  <button className="btn" onClick={() => open(a.id)}>Open dashboard</button>
                  <button className="btn btn-quiet" onClick={() => open(a.id, "analytics")}>Analytics</button>
                  {c.open_alerts.total > 0 && <button className="btn btn-quiet" onClick={() => open(a.id, "response")}>Medical response</button>}
                </div>
              </Panel>
            );
          })}
        </div>
      )}
      <p className="muted small">{data.note}</p>
    </div>
  );
}
