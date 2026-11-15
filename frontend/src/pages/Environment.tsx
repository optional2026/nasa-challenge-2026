import { useState } from "react";
import { TimeSeriesChart } from "../components/Charts";
import { ObservationDrawer } from "../components/ObservationDrawer";
import { Chip, Empty, ErrorBox, Loading, Panel, Synthetic, Tabs } from "../components/ui";
import { ago, fmtTime, fmtValue, humanize, unit } from "../lib/format";
import { useApp, useData } from "../lib/store";

const LOC_COLOR: Record<string, string> = { "HAB-A": "var(--series-1)", LAB: "var(--series-2)" };
const ENV_EVENTS = ["observations.created", "environment.warning", "environment.event_ended", "simulator.reset"];

function bySeries(points: any[], label = (l: string) => l) {
  const g: Record<string, any[]> = {};
  for (const p of points) (g[p.location || "—"] ||= []).push({ t: p.t, v: p.v, id: p.id });
  return Object.entries(g).map(([loc, pts]) => ({ name: label(loc), points: pts, color: LOC_COLOR[loc] }));
}

export default function Environment() {
  const { astronautId, user } = useApp();
  const [hours, setHours] = useState("240");
  const [obs, setObs] = useState<string | null>(null);
  const { data, error, reload } = useData<any>("/environment", ENV_EVENTS);
  const { data: hist } = useData<any>(`/environment/history?hours=${hours}`, ENV_EVENTS, [hours]);
  const { data: rad } = useData<any>(`/environment/radiation?hours=${hours}${astronautId ? `&astronaut_id=${astronautId}` : ""}`, ENV_EVENTS, [hours, astronautId]);
  const { data: events } = useData<any[]>(`/environment/events?hours=${Number(hours) * 4}`, ENV_EVENTS, [hours]);
  const { data: overlay } = useData<any>(astronautId ? `/environment/overlay?astronaut_id=${astronautId}&metric_code=heart_rate&env_metric=cabin_co2&hours=${hours}` : null, ENV_EVENTS, [hours, astronautId]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const s = hist?.series || {};
  const markers = (events || []).map((e) => ({ t: e.started_at, end: e.ended_at || new Date().toISOString(), label: e.description, tone: e.event_type === "radiation_event" ? "urgent" : "attn" }));
  const pt = (p: any) => p.id && setObs(p.id);
  return (
    <div className="page environment">
      <Panel title="Mission phase">
        <ol className="phase-track">
          {data.phases.map((p: any) => (
            <li key={p.id} className={data.phase?.id === p.id ? "now" : ""}>
              <strong>{p.phase}</strong><span>{p.location} · {p.gravity_g === 0 ? "microgravity" : `${p.gravity_g} g`}</span>
              <small>{fmtTime(p.start_utc)}{p.end_utc ? ` – ${fmtTime(p.end_utc)}` : " – ongoing"}</small>
            </li>
          ))}
        </ol>
        <p className="muted small">{data.note} Mission day {data.mission_day}.</p>
      </Panel>
      <Panel title="Current readings" actions={<Tabs tabs={[["24", "24 h"], ["72", "3 days"], ["240", "10 days"]]} value={hours} onChange={setHours} />}>
        {data.readings.length === 0 ? <Empty>No environmental sensor data yet. Start the simulator from Mission operations or connect a sensor through the telemetry API.</Empty> : (
          <div className="env-tiles">
            {data.readings.map((r: any) => (
              <button key={r.metric_code + r.location} className="env-tile" onClick={() => setObs(r.observation_id)}>
                <span>{r.name}{r.location ? ` · ${r.location}` : ""}</span>
                <strong>{fmtValue(r.value, r.unit)} <small>{unit(r.unit)}</small></strong>
                <small>{ago(r.measured_at)} · {r.device_id}</small>
                <Synthetic show={r.is_synthetic} />
              </button>
            ))}
          </div>
        )}
        {data.open_events.map((e: any) => <div key={e.id} className="note warn">Ongoing: {e.description}</div>)}
      </Panel>
      <div className="grid-2">
        <Panel title="Cabin CO₂">
          <TimeSeriesChart series={bySeries(s.cabin_co2?.points || [])} unit="mmHg" markers={markers.filter((m) => !m.label.includes("Radiation"))}
            refLines={[{ value: 3, label: "3 mmHg — NASA-STD-3001 V2 [6004] 1-hour average habitat limit", tone: "attn" }]} onPointClick={pt} />
          <p className="muted small">The 3 mmHg line is NASA's design limit for the 1-hour average in the habitable volume. Individual sensitivity to CO₂ varies; report headaches or other symptoms.</p>
        </Panel>
        <Panel title="Temperature and humidity">
          <TimeSeriesChart series={[...bySeries(s.cabin_temperature?.points || [], (l) => `Temperature ${l}`),
            ...bySeries(s.cabin_humidity?.points || [], (l) => `Humidity ${l}`).map((x) => ({ ...x, axis: "right" as const, dashed: true }))]}
            unit="°C" rightUnit="% RH" onPointClick={pt} />
        </Panel>
        <Panel title="Radiation dose rate (area monitor)">
          <TimeSeriesChart series={bySeries(rad?.area_dose_rate || [], (l) => `Dose rate ${l}`)} unit="µGy/h" markers={markers.filter((m) => m.label.includes("Radiation"))} onPointClick={pt} />
          <p className="muted small">Absorbed dose rate from the area monitor. Only dosimeters measure radiation; heart-rate or blood-pressure sensors cannot.</p>
        </Panel>
        <Panel title="Accumulated dose">
          {rad?.personal_cumulative?.length ? <TimeSeriesChart series={[{ name: "Personal dosimeter (cumulative)", points: rad.personal_cumulative }]} unit="mGy" onPointClick={pt} /> : null}
          <div className="table-wrap"><table>
            <thead><tr><th>Dosimeter</th><th>Mode</th><th>Accumulated</th><th>Last reading</th></tr></thead>
            <tbody>{(rad?.dosimeters || []).map((d: any) => (
              <tr key={d.device_id}><td>{d.device_id}</td><td>{d.astronaut_id ? `Personal (${d.astronaut_id})` : `Area (${d.location})`}</td>
                <td>{fmtValue(d.cumulative_mGy, "mGy")} mGy</td><td>{fmtTime(d.measured_at)}</td></tr>))}</tbody>
          </table></div>
          <p className="muted small">{rad?.note}</p>
        </Panel>
        <Panel title="Air quality">
          <TimeSeriesChart series={[...bySeries(s.air_tvoc?.points || [], (l) => `TVOC ${l}`), ...bySeries(s.air_pm25?.points || [], (l) => `PM2.5 ${l}`).map((x) => ({ ...x, axis: "right" as const, dashed: true }))]}
            unit="mg/m³" rightUnit="µg/m³" onPointClick={pt} />
          <p className="muted small">ASTRA defines no air-quality threshold of its own; trends are shown for review.</p>
        </Panel>
        <Panel title="Heart rate alongside cabin CO₂">
          {overlay ? <TimeSeriesChart series={[{ name: "Heart rate (bpm)", points: overlay.medical }, { name: "Cabin CO₂ (mmHg)", points: overlay.environment, axis: "right", dashed: true }]}
            unit="bpm" rightUnit="mmHg" markers={markers} onPointClick={pt} /> : <Empty>Select an astronaut to compare.</Empty>}
          <p className="note">{overlay?.disclaimer || "Shown together for context only. A temporal relationship does not establish causation."}</p>
        </Panel>
      </div>
      <Panel title="Environmental events">
        {!events?.length ? <Empty>No environmental events in this period.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Started</th><th>Ended</th><th>Type</th><th>Location</th><th>Peak</th><th>Description</th></tr></thead>
            <tbody>{events.map((e) => (
              <tr key={e.id}><td>{fmtTime(e.started_at)}</td><td>{e.ended_at ? fmtTime(e.ended_at) : <Chip tone="attn">Ongoing</Chip>}</td>
                <td>{humanize(e.event_type)}</td><td>{e.location}</td><td>{fmtValue(e.peak_value, e.unit)} {unit(e.unit)}</td>
                <td>{e.description} <Synthetic show={e.is_synthetic} /></td></tr>))}</tbody>
          </table></div>
        )}
      </Panel>
      <ObservationDrawer id={obs} onClose={() => setObs(null)} />
    </div>
  );
}
