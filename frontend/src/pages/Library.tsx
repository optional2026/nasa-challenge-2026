import { useState } from "react";
import { Chip, Empty, Loading, Panel, Tabs } from "../components/ui";
import { humanize, unit } from "../lib/format";
import { useData } from "../lib/store";

function SourceList({ sources }: { sources: any[] }) {
  return (
    <ul className="sources">
      {sources.map((s) => (
        <li key={s.id}>
          {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> : <span>{s.title}</span>}
          {s.document_id && <span className="muted"> ({s.document_id})</span>}
          <Chip tone={s.verification_status === "VERIFIED_ONLINE" ? "ok" : s.verification_status === "SYNTHETIC_NOT_VALIDATED" ? "attn" : "plain"}>{humanize(s.verification_status)}</Chip>
        </li>
      ))}
    </ul>
  );
}

export default function Library() {
  const [tab, setTab] = useState("hazards");
  const [q, setQ] = useState("");
  const { data: hazards } = useData<any[]>("/hazards");
  const { data: risks } = useData<any[]>("/risks");
  const { data: indicators } = useData<any[]>("/indicators");
  const { data: cms } = useData<any[]>("/countermeasures");
  const { data: procs } = useData<any[]>("/medical-protocols");
  const { data: rules } = useData<any[]>("/rules");
  const { data: sources } = useData<any[]>("/sources");
  const match = (...xs: any[]) => !q || xs.join(" ").toLowerCase().includes(q.toLowerCase());
  const srcMap = Object.fromEntries((sources || []).map((s) => [s.id, s]));

  return (
    <div className="page library">
      <Panel title="Medical knowledge library" actions={<input className="search" placeholder="Search the library" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />}>
        <p className="muted">Reference information from NASA sources. Every entry shows its source and evidence status. Procedures marked synthetic are demonstrations, not mission-approved medical procedures.</p>
        <Tabs tabs={[["hazards", "Spaceflight hazards"], ["risks", "Medical risks"], ["indicators", "Health indicators"], ["countermeasures", "Countermeasures"],
          ["procedures", "Procedures"], ["rules", "Assessment rules"], ["sources", "Sources"]]} value={tab} onChange={setTab} />
      </Panel>
      {tab === "hazards" && (!hazards ? <Loading /> : hazards.filter((h) => match(h.name, h.description)).map((h) => (
        <Panel key={h.id} title={h.name}>
          <p>{h.description}</p>
          <p><b>How ASTRA monitors it:</b> {h.monitoring_role}</p>
          <p><b>Related risks:</b> {h.risks.map((r: any) => r.name).join(", ")}</p>
          <SourceList sources={h.sources} />
        </Panel>
      )))}
      {tab === "risks" && (!risks ? <Loading /> : risks.filter((r) => match(r.name, r.description, r.nasa_risk_title)).map((r) => (
        <Panel key={r.id} title={r.name} actions={<><Chip tone="ok">{humanize(r.evidence_status)}</Chip> <Chip>{humanize(r.approval_status)}</Chip></>}>
          <p className="muted">{r.nasa_risk_title}</p>
          <p>{r.description}</p>
          <div className="grid-2 tight">
            <div><h3>Hazards</h3><ul>{r.hazards.map((h: any) => <li key={h.hazard_id}><b>{h.name}:</b> {h.rationale}</li>)}</ul></div>
            <div><h3>Indicators and measurement</h3><p>{r.indicators.map(humanize).join(", ")}</p><ul>{r.measurement_methods.map((m: string) => <li key={m}>{m}</li>)}</ul></div>
            <div><h3>Symptoms</h3><p>{r.symptoms.length ? r.symptoms.map(humanize).join(", ") : "—"}</p><h3>Countermeasures</h3><ul>{r.countermeasures.map((c: any) => <li key={c.id}>{c.name}</li>)}</ul></div>
            <div className="limits"><h3>What ASTRA cannot do</h3><ul>{r.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul></div>
          </div>
          <SourceList sources={r.sources} />
        </Panel>
      )))}
      {tab === "indicators" && (!indicators ? <Loading /> : (
        <Panel title="Health indicators and measurement instructions">
          <div className="table-wrap"><table>
            <thead><tr><th>Indicator</th><th>Unit</th><th>How to measure</th><th>Limitations</th><th>Privacy</th></tr></thead>
            <tbody>{indicators.filter((i) => match(i.name, i.description)).map((i) => (
              <tr key={i.code}><td><strong>{i.name}</strong>{i.challenge_required && <Chip tone="ok">Challenge indicator</Chip>}{i.clinician_directed && <Chip>Clinician-directed</Chip>}<br /><span className="muted small">{i.description}</span></td>
                <td>{i.canonical_unit === "as_reported" ? "per test" : unit(i.canonical_unit) || i.canonical_unit}{i.allowed_units.length > 1 ? <div className="muted small">accepts {i.allowed_units.join(", ")}</div> : null}</td>
                <td>{i.measurement_instructions}</td><td className="muted">{i.limitations}</td><td>{i.privacy === "private" ? <Chip tone="attn">Private</Chip> : "Standard"}</td></tr>))}</tbody>
          </table></div>
          <p className="muted small">Accepted input ranges reject impossible or mistyped values only. They are not clinical thresholds.</p>
        </Panel>
      ))}
      {tab === "countermeasures" && (!cms ? <Loading /> : cms.filter((c) => match(c.name, c.description)).map((c) => (
        <Panel key={c.id} title={c.name} actions={<Chip>{humanize(c.approval_status)}</Chip>}>
          <p>{c.description}</p><p className="muted">Addresses: {c.risk_ids.join(", ")}</p><SourceList sources={c.sources} />
        </Panel>
      )))}
      {tab === "procedures" && (!procs ? <Loading /> : procs.filter((p) => match(p.title)).map((p) => (
        <Panel key={p.id + p.version} title={p.title} actions={<Chip tone="attn">{humanize(p.approval_status)}</Chip>}>
          <div className="disclaimer">{p.disclaimer}</div>
          <div className="grid-2 tight">
            <div><h3>Verification checklist</h3><ul>{p.verification_checklist.map((x: string) => <li key={x}>{x}</li>)}</ul></div>
            <div><h3>Steps</h3><ol>{p.steps.map((x: string) => <li key={x}>{x}</li>)}</ol></div>
          </div>
          <p className="muted small">Used by rules: {p.applies_to_rules.join(", ")}</p>
        </Panel>
      )))}
      {tab === "rules" && (!rules ? <Loading /> : (
        <Panel title="Centralized assessment rules">
          <p className="muted">No numeric medical threshold is hard-coded in ASTRA. Rules are versioned, carry their class and source, and only medical personnel can create new versions.</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Rule</th><th>Class</th><th>Severity</th><th>Status</th><th>Parameters</th><th>Source</th></tr></thead>
            <tbody>{rules.filter((r) => match(r.name, r.description)).map((r) => (
              <tr key={r.id + r.version}><td><strong>{r.name}</strong> <span className="muted">({r.id} v{r.version})</span><br /><span className="small muted">{r.description}</span></td>
                <td><Chip tone={r.rule_class === "DEMONSTRATION_ONLY" ? "attn" : r.rule_class === "NASA_OPERATIONAL_REFERENCE" ? "ok" : "plain"}>{humanize(r.rule_class)}</Chip></td>
                <td>{humanize(r.severity)}</td><td>{r.active ? "Active" : "Inactive"} · {humanize(r.approval_status)}</td>
                <td><code className="small">{JSON.stringify(r.params)}</code></td><td>{srcMap[r.source_id]?.title || "—"}</td></tr>))}</tbody>
          </table></div>
        </Panel>
      ))}
      {tab === "sources" && (!sources ? <Loading /> : (
        <Panel title="Evidence sources">
          {sources.filter((s) => match(s.title, s.notes)).map((s) => (
            <div key={s.id} className="source-entry">
              <SourceList sources={[s]} />
              <p className="small">{s.notes}</p>
              <p className="muted small">{humanize(s.source_type)} · {s.publisher} · {s.year} · checked {s.accessed_date}</p>
            </div>
          ))}
          {sources.length === 0 && <Empty>No sources.</Empty>}
        </Panel>
      ))}
    </div>
  );
}
