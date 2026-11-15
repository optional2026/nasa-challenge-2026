// Mission overview for Earth-based personnel (administrator, ground flight surgeon): mission status, phases,
// crew roster with the server-computed crew status, and Earth-link / synchronization status. No personal health
// recording; individual records open in "Astronaut records".
import { LuSatelliteDish } from "react-icons/lu";
import { EarthFreshness } from "../components/EarthLink";
import { Avatar, Chip, Empty, ErrorBox, KV, Loading, Panel, StatusPill, Synthetic } from "../components/ui";
import { ago, fmtTime, humanize } from "../lib/format";
import { HEALTH_EVENTS, useApp, useData } from "../lib/store";

export default function MissionOverview() {
  const { setAstronautId, navigate, user, side } = useApp();
  const { data: missions, error, reload } = useData<any[]>("/missions", ["sync.link"]);
  const { data: crewView } = useData<any>("/crew/overview", HEALTH_EVENTS);
  const { data: sync } = useData<any>("/sync", ["sync.updated", "sync.link", "medical_report.created"]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!missions) return <Loading label="Loading mission overview" />;
  const status: Record<string, any> = {};
  (crewView?.crew || []).forEach((c: any) => { status[c.astronaut.id] = c; });
  const open = (id: string) => { setAstronautId(id); navigate("records"); };
  const s = crewView?.summary;

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Mission overview</h1>
        <p className="muted">{user?.role === "flight_surgeon" ? "Your assigned mission and crew. " : "Missions under mission-control responsibility. "}
          Select an astronaut to inspect their health records.</p>
      </div>
      {missions.length === 0 && <Empty>No missions configured.</Empty>}
      {missions.map((m) => {
        const crew = (m.crew || []).filter((a: any) => status[a.id]);
        return (
          <Panel key={m.id} title={<>{m.name} <Synthetic show={m.is_synthetic} /></>} actions={<Chip>{humanize(m.mission_type)}</Chip>}>
            <KV items={[
              ["Mission day", `Day ${m.mission_day}${m.planned_duration_days ? ` of ${m.planned_duration_days}` : ""}`],
              ["Current phase", m.current_phase ? `${m.current_phase.phase} · ${m.current_phase.location}` : "—"],
              ["Gravity", m.current_phase ? (m.current_phase.gravity_g === 0 ? "microgravity" : `${m.current_phase.gravity_g} g`) : "—"],
              ["Launch", fmtTime(m.start_utc)],
              side === "earth" ? ["Communication delay (configured)", `${Math.round(m.comm_delay_seconds)} s one-way`]
                : ["Earth link", <span className={`link link-${m.earth_link_status}`}><LuSatelliteDish aria-hidden /> {m.earth_link_status} · {Math.round(m.comm_delay_seconds)} s one-way delay</span>],
            ]} />
            <h3>Crew</h3>
            {crew.length === 0 ? <Empty>No crew members of this mission are within your responsibility.</Empty> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Astronaut</th><th>Crew</th><th>Status</th><th>Open alerts</th><th>Routine</th><th>Last measurement</th><th></th></tr></thead>
                <tbody>{crew.map((a: any) => {
                  const c = status[a.id];
                  return (
                    <tr key={a.id}>
                      <td><span className="user-cell"><Avatar name={a.name} seed={a.id} size={30} /><span><strong>{a.name}</strong><small className="muted">{a.crew_role}{a.call_sign ? ` · ${a.call_sign}` : ""}</small></span></span></td>
                      <td>{a.crew}</td>
                      <td>{c ? <StatusPill status={c.current_status} /> : "—"}</td>
                      <td>{c ? c.open_alerts.total : "—"}</td>
                      <td className={c?.routine.overdue ? "attn" : ""}>{c ? `${c.routine.overdue} overdue · ${c.routine.due} due` : "—"}</td>
                      <td className="small">{c?.last_measured_at ? ago(c.last_measured_at) : "none"}</td>
                      <td><button className="btn btn-quiet" onClick={() => open(a.id)}>Open records</button></td>
                    </tr>
                  );
                })}</tbody>
              </table></div>
            )}
            <details><summary className="small">Mission phases ({m.phases.length})</summary>
              <ul className="small">{m.phases.map((p: any) => <li key={p.id}>{p.phase} · {p.location} · {fmtTime(p.start_utc)} – {p.end_utc ? fmtTime(p.end_utc) : "ongoing"}</li>)}</ul>
            </details>
          </Panel>
        );
      })}
      <div className="grid-2">
        <Panel title="Crew status summary" actions={<button className="btn btn-quiet" onClick={() => navigate("crew")}>Crew overview</button>}>
          {!s ? <Loading /> : <KV items={[["Crew members", s.total], ["No current concern", s.no_concern], ["Need attention", s.attention],
            ["Need medical review", s.medical_review], ["Insufficient / no data", s.no_data], ["With active alerts", s.with_active_alerts],
            ["Last update", s.last_update_at ? ago(s.last_update_at) : "never"]]} />}
        </Panel>
        {side === "earth" ? <EarthFreshness /> : <Panel title="Communication and synchronization">
          {!sync ? <Loading /> : <>
            <KV items={[["Earth link", sync.earth_link_status], ["One-way delay", `${Math.round(sync.comm_delay_seconds)} s`],
              ...Object.entries(sync.counts).map(([k, v]) => [`Queue · ${humanize(k)}`, v as any] as [string, any])]} />
            <p className="muted small">{sync.ground_segment}. Reports from the spacecraft wait in the queue while the link is down.</p>
          </>}
        </Panel>}
      </div>
    </div>
  );
}
