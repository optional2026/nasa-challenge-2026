import { useEffect, useMemo, useState } from "react";
import { BodyMap, SYSTEMS } from "../components/BodyMap";
import { TimeSeriesChart } from "../components/Charts";
import { ObservationDrawer } from "../components/ObservationDrawer";
import { Chip, Empty, ErrorBox, Loading, Panel, Severity, StatusPill, Synthetic } from "../components/ui";
import { SEVERITY_TONE, Tone, ago, fmtTime, fmtValue, humanize, unit } from "../lib/format";
import { HEALTH_EVENTS, useApp, useData } from "../lib/store";

const PRIMARY_METRIC: Record<string, string> = {
  cardiovascular: "heart_rate", respiratory: "spo2", neurological: "sleep_duration", musculoskeletal: "exercise_session",
  immune: "body_temperature", behavioral: "mood", renal_metabolic: "water_intake",
};

export default function BodySystems() {
  const { astronautId, route, navigate } = useApp();
  const [sys, setSys] = useState(route.params.system || "cardiovascular");
  const [obs, setObs] = useState<string | null>(null);
  const { data, error, reload } = useData<any>(astronautId ? `/body-systems/${sys}?astronaut_id=${astronautId}&days=14` : null, HEALTH_EVENTS, [sys, astronautId]);
  const { data: alerts } = useData<any[]>(astronautId ? `/alerts?status=open&astronaut_id=${astronautId}` : null, HEALTH_EVENTS, [astronautId]);
  const { data: rules } = useData<any[]>("/rules");
  const [metric, setMetric] = useState(PRIMARY_METRIC[sys]);
  useEffect(() => setMetric(PRIMARY_METRIC[sys]), [sys]);
  const { data: hist } = useData<any>(astronautId && metric ? `/measurements/history?astronaut_id=${astronautId}&metric_code=${metric}${metric === "heart_rate" ? "&context_key=resting" : ""}&start=${new Date(Date.now() - 14 * 864e5).toISOString()}&limit=3000` : null,
    ["observations.created", "simulator.reset"], [metric, astronautId]);

  // colour each region by its most severe open alert
  const tones = useMemo(() => {
    const out: Record<string, Tone> = {};
    const order: Tone[] = ["none", "info", "ok", "attn", "review", "urgent"];
    const riskToSystems: Record<string, string[]> = {
      "RISK-CV": ["cardiovascular"], "RISK-MSK": ["musculoskeletal"], "RISK-IMM": ["immune"], "RISK-BHV": ["behavioral"],
      "RISK-SLEEP": ["neurological", "behavioral"], "RISK-SANS": ["neurological"], "RISK-SMV": ["neurological"],
      "RISK-NUT": ["renal_metabolic"], "RISK-RENAL": ["renal_metabolic"], "RISK-RESP": ["respiratory"], "RISK-RAD": [], "RISK-MED": [],
    };
    for (const a of alerts || []) {
      if (!a.astronaut_id) continue;
      const rule = (rules || []).find((r) => r.id === a.rule_id && r.version === a.rule_version);
      for (const rid of rule?.risk_ids || []) for (const s of riskToSystems[rid] || []) {
        const t = SEVERITY_TONE[a.severity];
        if (order.indexOf(t) > order.indexOf(out[s] || "none")) out[s] = t;
      }
    }
    SYSTEMS.forEach((s) => { if (!out[s.id]) out[s.id] = "ok"; });
    return out;
  }, [alerts, rules]);

  const points = (hist?.items || []).filter((o: any) => typeof o.value === "number")
    .map((o: any) => ({ t: o.measured_at, v: o.value, id: o.id, quality: o.quality }));
  const latestFor = (code: string) => data?.latest?.find((l: any) => l.metric_code === code);
  const chartUnit = hist?.items?.[0]?.unit;

  return (
    <div className="page body-systems">
      <div className="body-layout">
        <Panel title="Select a body system" className="map-panel">
          <BodyMap selected={sys} onSelect={(s) => { setSys(s); navigate("body", { system: s }); }} tones={tones} />
          <ul className="system-list">
            {SYSTEMS.map((s) => (
              <li key={s.id}><button className={`${sys === s.id ? "active" : ""} tone-${tones[s.id]}`} onClick={() => { setSys(s.id); navigate("body", { system: s.id }); }}>
                <i aria-hidden /> {s.label}</button></li>
            ))}
          </ul>
          <p className="muted small">Colours show the most serious open alert linked to each system. Green means no open alert, not a diagnosis.</p>
        </Panel>
        <div className="stack">
          {error && <ErrorBox error={error} onRetry={reload} />}
          {!data ? <Loading /> : (
            <>
              <header className="system-head">
                <h1>{data.label}</h1>
                <div className="chips">{data.hazards.map(([id, name]: [string, string]) => <Chip key={id} tone="hazard">{name}</Chip>)}</div>
              </header>
              {data.private_hidden && <div className="note">Behavioral-health self-reports are private. They are visible to the astronaut and the flight surgeon only.</div>}
              <Panel title="Latest measurements">
                {data.latest.length === 0 ? <Empty>No measurements for this system yet.</Empty> : (
                  <div className="mini-vitals">
                    {data.latest.map((l: any) => (
                      <button key={l.metric_code} className={`mini ${metric === l.metric_code ? "active" : ""}`} onClick={() => setMetric(l.metric_code)}>
                        <span>{data.metric_names?.[l.metric_code] || humanize(l.metric_code)}</span>
                        <strong>{fmtValue(l.value, l.unit, l.metric_code)} <small>{l.metric_code === "sleep_duration" ? "" : unit(l.unit)}</small></strong>
                        <small>{ago(l.measured_at)} {l.quality !== "valid" && `· ${l.quality}`}</small>
                      </button>
                    ))}
                  </div>
                )}
              </Panel>
              <Panel title={`${data.metric_names?.[metric] || humanize(metric)}${metric === "heart_rate" ? " at rest" : ""} — last 14 days`} actions={<button className="btn btn-quiet" onClick={() => navigate("analytics", { metric })}>Open in analytics</button>}>
                <TimeSeriesChart series={[{ name: data.metric_names?.[metric] || humanize(metric), points }]} unit={unit(chartUnit)} onPointClick={(p) => p.id && setObs(p.id)} height={220} />
              </Panel>
              <div className="grid-2">
                <Panel title="Reported symptoms (14 days)">
                  {data.symptoms.length === 0 ? <Empty>No symptoms reported for this system.</Empty> : (
                    <ul className="plain-list">{data.symptoms.map((s: any) => <li key={s.id}><button className="linkish" onClick={() => setObs(s.id)}>{s.label}</button> <span className="muted">severity {s.severity ?? "n/a"} · {fmtTime(s.measured_at)}</span></li>)}</ul>
                  )}
                </Panel>
                <Panel title="Open findings and next steps">
                  {data.open_alerts.map((a: any) => <div key={a.id} className="row-line"><Severity value={a.severity} /> {a.title}</div>)}
                  <ul className="plain-list">{data.next_steps.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
                </Panel>
              </div>
              <Panel title="Recent assessment results">
                {data.assessment_findings.length === 0 ? <Empty>No assessment findings for the risks of this system in the last 14 days.</Empty> : (
                  <ul className="plain-list">
                    {data.assessment_findings.filter((f: any, i: number, arr: any[]) => {
                      const key = f.status + f.findings.map((x: any) => x.title).join("|");
                      return arr.findIndex((g: any) => g.status + g.findings.map((x: any) => x.title).join("|") === key) === i;
                    }).slice(0, 6).map((f: any) => (
                      <li key={f.assessment_id}><StatusPill status={f.status} /> <span className="muted">{fmtTime(f.created_at)}</span>
                        <ul>{f.findings.filter((x: any) => !x.finding_only).slice(0, 3).map((x: any, i: number) => <li key={i}>{x.title} <Chip tone="plain">{x.rule_class === "DEMONSTRATION_ONLY" ? "Demonstration rule" : humanize(x.rule_class)}</Chip></li>)}</ul>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
              <Panel title="Related NASA risks">
                {data.risks.map((r: any) => (
                  <details key={r.id} className="risk">
                    <summary><strong>{r.name}</strong> <span className="muted">{r.nasa_risk_title}</span></summary>
                    <p>{r.description}</p>
                    <p><b>Hazards:</b> {r.hazards.map((h: any) => `${h.name} — ${h.rationale}`).join(" ")}</p>
                    <p><b>Measured with:</b> {r.measurement_methods.join("; ")}</p>
                    <p><b>Countermeasures:</b> {r.countermeasures.map((c: any) => c.name).join("; ")}</p>
                    <div className="limits"><b>Measurement limitations</b><ul>{r.limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul></div>
                    <p className="muted small">Evidence status: {humanize(r.evidence_status)} · Sources: {r.sources.map((s: any) => s.document_id || s.title).join("; ")}</p>
                  </details>
                ))}
              </Panel>
              <Panel title="Scientific sources">
                <ul className="sources">{data.sources.map((s: any) => <li key={s.id}><a href={s.url || undefined} target="_blank" rel="noreferrer">{s.title}</a> <Chip tone={s.verification_status === "VERIFIED_ONLINE" ? "ok" : "plain"}>{humanize(s.verification_status)}</Chip></li>)}</ul>
              </Panel>
            </>
          )}
        </div>
      </div>
      <ObservationDrawer id={obs} onClose={() => setObs(null)} />
    </div>
  );
}
