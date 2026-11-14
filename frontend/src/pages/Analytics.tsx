import { useMemo, useState } from "react";
import { TimeSeriesChart } from "../components/Charts";
import { ObservationDrawer } from "../components/ObservationDrawer";
import { Chip, Empty, ErrorBox, KV, Loading, Panel, Severity, Synthetic, Tabs } from "../components/ui";
import { fmtTime, fmtValue, humanize, unit } from "../lib/format";
import { HEALTH_EVENTS, useApp, useData } from "../lib/store";

const RANGES: [string, string][] = [["day", "Day"], ["week", "Week"], ["mission", "Mission"]];
const NUMERIC_TYPES = new Set(["numeric", "ordinal"]);

export default function Analytics() {
  const { astronautId, route, user } = useApp();
  const [metric, setMetric] = useState(route.params.metric || "heart_rate");
  const [compare, setCompare] = useState("");
  const [range, setRange] = useState("week");
  const [showBaseline, setShowBaseline] = useState(true);
  const [source, setSource] = useState("");
  const [hrCtx, setHrCtx] = useState("resting");
  const [obs, setObs] = useState<string | null>(null);
  const { data: indicators } = useData<any[]>("/indicators");
  const { data: mission } = useData<any[]>("/missions");
  const start = useMemo(() => {
    if (range === "day") return new Date(Date.now() - 864e5).toISOString();
    if (range === "week") return new Date(Date.now() - 7 * 864e5).toISOString();
    const s = mission?.[0]?.start_utc ? new Date(mission[0].start_utc).getTime() - 45 * 864e5 : Date.now() - 60 * 864e5;
    return new Date(s).toISOString();
  }, [range, mission]);
  const bucket = range === "day" ? "raw" : range === "week" ? "raw" : "day";
  const hpath = (m: string) => astronautId ? `/measurements/history?astronaut_id=${astronautId}&metric_code=${m}&start=${start}&limit=5000${source ? `&source_type=${source}` : ""}${m === "heart_rate" && hrCtx ? `&context_key=${hrCtx}` : ""}${bucket !== "raw" ? `&bucket=${bucket}` : ""}` : null;
  const { data: hist, error } = useData<any>(hpath(metric), ["observations.created", "simulator.reset"], [metric, start, source, astronautId, hrCtx]);
  const { data: hist2 } = useData<any>(compare ? hpath(compare) : null, ["observations.created"], [compare, start, astronautId]);
  const days = range === "day" ? 1 : range === "week" ? 7 : 60;
  const { data: trend, error: trendErr } = useData<any>(astronautId ? `/trends?astronaut_id=${astronautId}&metric_code=${metric}&days=${days}&recent_days=${Math.max(0.5, days / 4)}` : null,
    ["observations.created", "baseline.updated"], [metric, days, astronautId]);
  const { data: alerts } = useData<any[]>(astronautId ? `/alerts?astronaut_id=${astronautId}&limit=300` : null, HEALTH_EVENTS, [astronautId]);

  const ind = indicators?.find((i) => i.code === metric);
  const toPts = (h: any) => h ? (h.buckets
    ? h.buckets.map((b: any) => ({ t: b.bucket_start, v: b.mean, id: b.observation_ids[0], label: `${b.mean} (min ${b.min}, max ${b.max}, n=${b.count})` }))
    : h.items.filter((o: any) => typeof o.value === "number").map((o: any) => ({ t: o.measured_at, v: o.value, id: o.id, quality: o.quality })))
    : [];
  const pts = toPts(hist);
  const b = trend?.baseline;
  const k = 2.5;
  const bands = showBaseline && b ? [{ from: b.mean - k * b.sd, to: b.mean + k * b.sd, label: `Personal baseline v${b.version} ± ${k} SD` }] : [];
  const refLines = showBaseline && b ? [{ value: b.mean, label: "baseline mean", tone: "baseline" }] : [];
  const COMBO: Record<string, string[]> = { cardiorespiratory: ["heart_rate", "spo2", "respiratory_rate"], vision: [], behavioral: ["mood", "stress"] };
  const metricAlerts = (alerts || []).filter((a) => {
    const m = String(a.dedup_key || "").split("|")[2] || "";
    const base = m.split(":")[0];
    return base === metric || (COMBO[base] || []).includes(metric);
  });
  const markers = metricAlerts.map((a) => ({ t: a.created_at, label: `${a.severity}: ${a.title}`, tone: a.severity === "URGENT" ? "urgent" : a.severity === "MEDICAL_REVIEW" ? "review" : "attn" }));
  const series: any[] = [{ name: ind?.name || metric, points: pts }];
  if (compare && hist2) series.push({ name: indicators?.find((i) => i.code === compare)?.name || compare, points: toPts(hist2), axis: "right", dashed: true });
  const xd: [number, number] | undefined = pts.length ? [new Date(start).getTime(), Date.now()] : undefined;
  const choices = (indicators || []).filter((i) => NUMERIC_TYPES.has(i.value_type) && i.subject !== "environment");
  const quality = trend?.quality_counts || {};
  const nonValid = Object.entries(quality).filter(([q]) => q !== "valid").reduce((s, [, n]) => s + (n as number), 0);

  return (
    <div className="page analytics">
      <Panel title="Health analytics">
        <div className="controls">
          <label className="field"><span className="field-label">Indicator</span>
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              {choices.map((i) => <option key={i.code} value={i.code}>{i.name}{i.privacy === "private" ? " (private)" : ""}</option>)}
            </select></label>
          <label className="field"><span className="field-label">Compare with</span>
            <select value={compare} onChange={(e) => setCompare(e.target.value)}>
              <option value="">None</option>
              {choices.filter((i) => i.code !== metric).map((i) => <option key={i.code} value={i.code}>{i.name}</option>)}
            </select></label>
          <label className="field"><span className="field-label">Source</span>
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All sources</option>
              {["manual", "medical_device", "wearable", "clinician", "simulator"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </select></label>
          {metric === "heart_rate" && (
            <label className="field"><span className="field-label">Activity</span>
              <select value={hrCtx} onChange={(e) => setHrCtx(e.target.value)}>
                <option value="resting">Resting (compared with baseline)</option><option value="exercise">Exercise</option>
                <option value="sleep">Sleep</option><option value="">All activities</option>
              </select></label>
          )}
          <div className="field"><span className="field-label">Time range</span><Tabs tabs={RANGES} value={range} onChange={setRange} /></div>
          <label className="check"><input type="checkbox" checked={showBaseline} onChange={(e) => setShowBaseline(e.target.checked)} /> Baseline overlay</label>
        </div>
        {error && <ErrorBox error={error} />}
        {!hist ? <Loading /> : (
          <TimeSeriesChart series={series} bands={bands} refLines={refLines} markers={markers} unit={unit(hist.items[0]?.unit || ind?.canonical_unit)}
            rightUnit={compare ? unit(hist2?.items?.[0]?.unit) : undefined} height={320} xDomain={xd}
            onPointClick={(p) => p.id && setObs(p.id)}
            emptyText={hist.hidden_private ? "These records are private to the astronaut and flight surgeon." : "No measurements in this period"} />
        )}
        <p className="muted small">
          {bucket === "day" ? "Mission view shows daily means (hover for min/max/count). " : "Every point is one observation; click to inspect provenance. "}
          Shaded vertical marks are alerts for this indicator. Hollow-ringed points have questionable or unverified quality.
          {compare && " The comparison series uses the right-hand axis. Showing two indicators together does not mean one causes the other."}
        </p>
      </Panel>
      <div className="grid-2">
        <Panel title="Trend analysis">
          {trendErr && <ErrorBox error={trendErr} />}
          {!trend ? <Loading /> : (
            <>
              <KV items={[
                ["Period", `${fmtTime(trend.period.start)} → ${fmtTime(trend.period.end)}`],
                ["Approved baseline", b ? `${fmtValue(b.mean)} ± ${fmtValue(b.sd)} (v${b.version}, n=${b.n}, ${humanize(b.source)}, approved by ${b.approved_by})` : "None — comparison is informational only"],
                ["Earlier mean", trend.historical.n ? `${fmtValue(trend.historical.mean)} (n=${trend.historical.n})` : "no data"],
                ["Recent mean", trend.recent.n ? `${fmtValue(trend.recent.mean)} (n=${trend.recent.n})` : "no data"],
                ["Recent vs baseline", trend.recent_vs_baseline_sd !== undefined ? `${trend.recent_vs_baseline_sd > 0 ? "+" : ""}${trend.recent_vs_baseline_sd} SD` : "—"],
                ["Slope", trend.slope_per_day !== null ? `${trend.slope_per_day > 0 ? "+" : ""}${trend.slope_per_day} ${unit(ind?.canonical_unit)} per day` : "not enough data"],
                ["Consecutive beyond ±2.5 SD", trend.consecutive_beyond_baseline],
                ["Rapid changes", trend.rapid_changes.length],
                ["Gaps in expected measurements", trend.gaps.length ? trend.gaps.map((g: any) => `${g.hours} h from ${fmtTime(g.from)}`).join("; ") : "none"],
              ]} />
              {trend.findings.map((f: string, i: number) => <p key={i} className="note">{f}</p>)}
            </>
          )}
        </Panel>
        <Panel title="Data quality">
          {nonValid > 0 ? <div className="note warn">{nonValid} observation(s) in this period are not marked valid. They are excluded from baseline comparisons and never interpreted as normal or abnormal.</div>
            : <p>All observations in this period are marked valid.</p>}
          <KV items={Object.entries(quality).map(([q, n]) => [humanize(q), n as any])} />
          <h3>Alerts for this indicator</h3>
          {metricAlerts.length === 0 ? <Empty>No alerts for this indicator.</Empty> : metricAlerts.slice(0, 6).map((a) => (
            <div key={a.id} className="row-line"><Severity value={a.severity} /> {a.title} <span className="muted">{fmtTime(a.created_at)}</span></div>
          ))}
        </Panel>
      </div>
      <Panel title={`Observations (latest 60 of ${hist?.items?.length ?? 0})`}>
        {hist && hist.items.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Measured (UTC)</th><th>Value</th><th>As submitted</th><th>Source</th><th>Device</th><th>Quality</th><th>Context</th></tr></thead>
            <tbody>{[...hist.items].reverse().slice(0, 60).map((o: any) => (
              <tr key={o.id} onClick={() => setObs(o.id)} className="clickable" tabIndex={0} onKeyDown={(e: any) => e.key === "Enter" && setObs(o.id)}>
                <td>{fmtTime(o.measured_at)}</td><td>{fmtValue(o.value, o.unit, o.metric_code)} {o.metric_code === "sleep_duration" ? "" : unit(o.unit)}</td>
                <td className="muted">{JSON.stringify(o.original_value)} {o.original_unit}</td><td>{humanize(o.source_type)}</td>
                <td>{o.device_id || "—"}</td><td><Chip tone={o.quality === "valid" ? "ok" : "attn"}>{o.quality}</Chip></td>
                <td className="muted">{Object.entries(o.context || {}).filter(([k2]) => k2 !== "simulator_scenario").map(([k2, v]) => `${k2}: ${v}`).join(", ")} <Synthetic show={o.is_synthetic} /></td>
              </tr>))}</tbody>
          </table></div>
        ) : <Empty>No observations for this indicator in the selected period.</Empty>}
      </Panel>
      <ObservationDrawer id={obs} onClose={() => setObs(null)} />
    </div>
  );
}
