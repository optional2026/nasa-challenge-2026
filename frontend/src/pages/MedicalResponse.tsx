import { useEffect, useState } from "react";
import { LuCircleCheck, LuCircle, LuFileText, LuSend, LuShieldCheck } from "react-icons/lu";
import { ObservationDrawer } from "../components/ObservationDrawer";
import { Chip, Drawer, Empty, ErrorBox, Field, KV, Loading, Panel, Severity, Synthetic, Tabs, useAsyncAction } from "../components/ui";
import { get, post } from "../lib/api";
import { ROLE_LABEL, fmtTime, fmtValue, humanize, unit } from "../lib/format";
import { HEALTH_EVENTS, useApp, useData } from "../lib/store";

const STATE_ORDER = ["DETECTED", "VERIFYING", "ACTIVE", "ESCALATED", "MONITORING", "RESOLVED"];
const STATE_HELP: Record<string, string> = {
  DETECTED: "Found by the assessment engine. Next: verify the measurements.",
  VERIFYING: "Checking measurement quality and repeating measurements.",
  ACTIVE: "Confirmed finding; the procedure is being followed.",
  ESCALATED: "Medical personnel notified; report queued for ground.",
  MONITORING: "Follow-up observations are being collected.",
  RESOLVED: "Closed by medical personnel with a documented reason.",
};

export default function MedicalResponse() {
  const { astronautId, route, user, toast } = useApp();
  const [filter, setFilter] = useState("open");
  const [selEvent, setSelEvent] = useState<string | null>(route.params.event || null);
  const [selAlert, setSelAlert] = useState<string | null>(route.params.alert || null);
  const { data: alerts, error: aErr } = useData<any[]>(astronautId ? `/alerts?astronaut_id=${astronautId}${filter === "open" ? "&status=open" : ""}&limit=200` : null, HEALTH_EVENTS, [astronautId, filter]);
  const { data: events } = useData<any[]>(astronautId ? `/medical-events?astronaut_id=${astronautId}${filter === "open" ? "&status=open" : ""}` : null, HEALTH_EVENTS, [astronautId, filter]);

  useEffect(() => {
    if (selAlert && alerts) {
      const a = alerts.find((x) => x.id === selAlert);
      if (a?.medical_event_id && !selEvent) setSelEvent(a.medical_event_id);
    }
  }, [selAlert, alerts]);
  useEffect(() => {
    if (!selEvent && !selAlert && events?.length) {
      const first = events.find((e) => !e.redacted && e.state !== "RESOLVED");
      if (first) setSelEvent(first.id);
    }
  }, [events]);

  return (
    <div className="page response">
      <div className="response-layout">
        <div className="stack">
          <Panel title="Medical events" actions={<Tabs tabs={[["open", "Open"], ["all", "All"]]} value={filter} onChange={setFilter} />}>
            {!events ? <Loading /> : events.length === 0 ? <Empty>No {filter === "open" ? "open " : ""}medical events.</Empty> : (
              <ul className="event-list">
                {events.map((e) => (
                  <li key={e.id} className={`sevbar-${e.severity} ${selEvent === e.id ? "selected" : ""}`}>
                    <button disabled={e.redacted} onClick={() => { setSelEvent(e.id); setSelAlert(null); }}>
                      <Severity value={e.severity} /> <strong>{e.title}</strong>
                      <span className="muted">{humanize(e.state)} · {fmtTime(e.opened_at)}</span>
                      {e.redacted && <span className="muted">Private — content restricted to the astronaut and flight surgeon</span>}
                      <Synthetic show={e.is_synthetic} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Alerts">
            {aErr && <ErrorBox error={aErr} />}
            {!alerts ? <Loading /> : alerts.length === 0 ? <Empty>No alerts.</Empty> : (
              <ul className="alert-list">
                {alerts.map((a) => (
                  <li key={a.id} className={`sevbar-${a.severity} ${selAlert === a.id ? "selected" : ""}`}>
                    <button onClick={() => { setSelAlert(a.id); }}>
                      <Severity value={a.severity} /> <strong>{a.title}</strong>
                      <span className="muted">{a.category === "environment" ? "Environment · " : ""}{humanize(a.ack_status)} · {humanize(a.resolution_status)} · {fmtTime(a.updated_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
        <div className="stack">
          {selEvent ? <EventDetail id={selEvent} key={selEvent} /> : <Panel><Empty>Select a medical event to see its timeline, procedure and actions.</Empty></Panel>}
        </div>
      </div>
      <AlertDrawer id={selAlert} onClose={() => setSelAlert(null)} openEvent={(id) => { setSelEvent(id); setSelAlert(null); }} />
    </div>
  );
}

function AlertDrawer({ id, onClose, openEvent }: { id: string | null; onClose: () => void; openEvent: (id: string) => void }) {
  const { user, toast } = useApp();
  const { data: a, reload } = useData<any>(id ? `/alerts/${id}` : null, ["alert.updated", "alert.acknowledged", "alert.resolved"], [id]);
  const [note, setNote] = useState("");
  const [obs, setObs] = useState<string | null>(null);
  const act = useAsyncAction();
  const medical = user?.role === "medical_officer" || user?.role === "flight_surgeon";
  return (
    <Drawer open={!!id} onClose={onClose} title="Alert">
      {!a ? <Loading /> : (
        <div className="stack">
          <div><Severity value={a.severity} /> <strong>{a.title}</strong> <Synthetic show={a.is_synthetic} /></div>
          <p>{a.explanation}</p>
          <div className="note"><b>Required next step:</b> {a.next_step}</div>
          <KV items={[
            ["Triggering rule", a.rule ? `${a.rule.name} (${a.rule_id} v${a.rule_version})` : a.rule_id],
            ["Rule class", humanize(a.rule_class)],
            ["Rule source", a.rule_source ? a.rule_source.title : a.rule_class === "DEMONSTRATION_ONLY" ? "Synthetic demonstration rule — not a clinical threshold" : "—"],
            ["Related symptoms", a.related_symptoms.length ? a.related_symptoms.map(humanize).join(", ") : "none"],
            ["Created", fmtTime(a.created_at)], ["Updated", `${fmtTime(a.updated_at)} (${a.occurrence_count} evaluation${a.occurrence_count > 1 ? "s" : ""})`],
            ["Acknowledgement", a.ack_by ? `${humanize(a.ack_status)} by ${a.ack_by}` : humanize(a.ack_status)],
            ["Escalation", humanize(a.escalation_status)], ["Resolution", humanize(a.resolution_status)],
          ]} />
          {a.baseline_context && Object.keys(a.baseline_context).length > 0 && (
            <details><summary>Baseline context</summary><pre className="json">{JSON.stringify(a.baseline_context, null, 2)}</pre></details>
          )}
          <div><h3>Triggering measurements</h3>
            {(a.observation_ids || []).length ? a.observation_ids.map((o: string) => <button key={o} className="chip chip-plain linkish" onClick={() => setObs(o)}>{o}</button>) : <p className="muted">None linked.</p>}
          </div>
          {a.medical_event_id && <button className="btn" onClick={() => openEvent(a.medical_event_id)}>Open linked medical event</button>}
          {user?.role === "admin" && <p className="muted small">Read-only: acknowledging and resolving alerts is reserved for the crew and medical personnel.</p>}
          {a.resolution_status === "open" && !a.redacted && user?.role !== "admin" && (
            <>
              <Field label="Note (optional for acknowledgement, required to resolve)"><textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} /></Field>
              <ErrorBox error={act.error} />
              <div className="btn-row">
                {a.ack_status !== "acknowledged" && <button className="btn" disabled={act.busy} onClick={() => act.run(async () => { await post(`/alerts/${a.id}/acknowledge`, { note: note || null }); toast("Alert acknowledged", "ok"); reload(); })}>Acknowledge</button>}
                {(medical || ["INFORMATION", "REASSESSMENT"].includes(a.severity)) && (
                  <button className="btn btn-quiet" disabled={act.busy} onClick={() => act.run(async () => { await post(`/alerts/${a.id}/resolve`, { note: note || null }); toast("Alert resolved", "ok"); reload(); })}>Resolve</button>
                )}
              </div>
              <p className="muted small">Acknowledging an alert never closes its medical event. Medical-review and urgent alerts are resolved by medical personnel after the event is resolved.</p>
            </>
          )}
        </div>
      )}
      <ObservationDrawer id={obs} onClose={() => setObs(null)} />
    </Drawer>
  );
}

function EventDetail({ id }: { id: string }) {
  const { user, toast } = useApp();
  const { data: e, error, reload } = useData<any>(`/medical-events/${id}`, ["medical_event.updated", "medical_event.created", "medical_report.created", "sync.updated", "alert.updated"], [id]);
  const [obsRows, setObsRows] = useState<any[]>([]);
  const [obs, setObs] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [questions, setQuestions] = useState("");
  const [report, setReport] = useState<any>(null);
  const act = useAsyncAction();
  const medical = user?.role === "medical_officer" || user?.role === "flight_surgeon";
  const readOnly = user?.role === "admin";  // administrators are not medical personnel: view only

  useEffect(() => {
    if (!e) return;
    Promise.all(e.observation_ids.slice(0, 30).map((o: string) => get(`/measurements/${o}`).catch(() => null)))
      .then((rows) => setObsRows(rows.filter(Boolean)));
  }, [e?.observation_ids?.join(",")]);

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!e) return <Loading />;
  const urgent = e.severity === "URGENT" && e.state !== "RESOLVED";
  const checklist = e.checklist_status || [];
  const doTransition = (to: string) => act.run(async () => {
    await post(`/medical-events/${e.id}/transition`, { to_state: to, reason: reason || null });
    setReason(""); toast(`Event moved to ${humanize(to)}`, "ok"); reload();
  });
  const timeline = [
    ...e.transitions.map((t: any) => ({ at: t.at, who: t.actor, text: `${t.from_state ? humanize(t.from_state) + " → " : ""}${humanize(t.to_state)}${t.reason ? ` — ${t.reason}` : ""}`, kind: "state" })),
    ...e.actions.map((a: any) => ({ at: a.performed_at, who: a.performed_by, text: `${humanize(a.action_type)}: ${a.description}`, kind: a.action_type })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <>
      <section className={`event-hero ${urgent ? "is-urgent" : ""}`}>
        <div>
          <Severity value={e.severity} /> <Synthetic show={e.is_synthetic} />
          <h1>{e.title}</h1>
          <p className="muted">Event {e.id} · opened {fmtTime(e.opened_at)}{e.risk_id ? ` · ${e.risk_id}` : ""}</p>
        </div>
        <ol className="state-track" aria-label="Event state">
          {STATE_ORDER.map((s) => <li key={s} className={s === e.state ? "now" : STATE_ORDER.indexOf(s) < STATE_ORDER.indexOf(e.state) ? "past" : ""}>{humanize(s)}</li>)}
        </ol>
        <p>{STATE_HELP[e.state]}</p>
      </section>

      <Panel title="What triggered this">
        {e.alerts.map((a: any) => <div key={a.id} className="row-line"><Severity value={a.severity} /> {a.title} <span className="muted">rule {a.rule_id}</span></div>)}
        {obsRows.length > 0 && (
          <div className="table-wrap"><table>
            <thead><tr><th>Measured</th><th>Indicator</th><th>Value</th><th>Source / device</th><th>Quality</th></tr></thead>
            <tbody>{obsRows.map((o) => (
              <tr key={o.id} className="clickable" onClick={() => setObs(o.id)}>
                <td>{fmtTime(o.measured_at)}</td><td>{humanize(o.metric_code)}</td><td>{fmtValue(o.value, o.unit, o.metric_code)} {unit(o.unit)}</td>
                <td>{humanize(o.source_type)} {o.device_id ? `· ${o.device_id}` : ""}</td><td><Chip tone={o.quality === "valid" ? "ok" : "attn"}>{o.quality}</Chip></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Panel>

      <div className="grid-2">
        <Panel title={<><LuShieldCheck aria-hidden /> Procedure</>} className="procedure">
          {e.protocol ? (
            <>
              <div className="disclaimer">{e.protocol.disclaimer}</div>
              <h3>{e.protocol.title}</h3>
              <ol className="steps">{e.protocol.steps.map((s: string, i: number) => <li key={i}>{s}</li>)}</ol>
              <p className="muted small">Procedure {e.protocol.id} v{e.protocol.version} · approval status: {humanize(e.protocol.approval_status)}</p>
            </>
          ) : (
            <div className="disclaimer">No approved procedure is loaded for this finding. Consult the relevant mission procedure and escalate to authorized medical personnel. ASTRA does not generate treatment instructions.</div>
          )}
        </Panel>
        <Panel title="Verification checklist">
          {checklist.length === 0 ? <Empty>No checklist for this event.</Empty> : (
            <ul className="checklist">
              {checklist.map((c: any) => (
                <li key={c.item}>
                  <button disabled={c.checked || act.busy || e.state === "RESOLVED" || readOnly} onClick={() => act.run(async () => {
                    await post(`/medical-events/${e.id}/actions`, { action_type: "checklist_item", description: c.item, data: { item: c.item, checked: true } });
                    reload();
                  })}>{c.checked ? <LuCircleCheck className="ok" aria-hidden /> : <LuCircle aria-hidden />} {c.item}</button>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">Each confirmation is recorded with your name and the time.</p>
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="Actions">
          <ErrorBox error={act.error} />
          {readOnly ? <div className="note">Read-only: escalation, state changes, notes and reports are reserved for the crew and medical personnel. The timeline shows every action taken.</div> : <>
          {e.state !== "RESOLVED" && (
            <>
              <Field label="Escalation note"><textarea rows={2} value={note} onChange={(x) => setNote(x.target.value)} placeholder="What the crew member reports, what was checked" /></Field>
              <Field label="Outstanding questions for medical personnel (one per line)"><textarea rows={2} value={questions} onChange={(x) => setQuestions(x.target.value)} /></Field>
              <button className="btn btn-urgent" disabled={act.busy} onClick={() => act.run(async () => {
                const r = await post(`/medical-events/${e.id}/escalate`, { note: note || null, outstanding_questions: questions.split("\n").map((q) => q.trim()).filter(Boolean) });
                setNote(""); setQuestions(""); toast(`Escalated. Report ${r.report.id} is ${r.report.sync_status} for ground.`, "review"); reload();
              })}><LuSend aria-hidden /> Escalate to medical personnel</button>
              <p className="muted small">Notifies the Crew Medical Officer and queues a structured report for the ground flight surgeon (sent automatically when the Earth link is available).</p>
            </>
          )}
          <h3>Change state</h3>
          <Field label={`Reason ${e.allowed_transitions.some((t: string) => t === "RESOLVED" || t === "ESCALATED") ? "(required to escalate or resolve)" : ""}`}>
            <input value={reason} onChange={(x) => setReason(x.target.value)} />
          </Field>
          <div className="btn-row">
            {e.allowed_transitions.map((t: string) => (
              <button key={t} className="btn" disabled={act.busy || (t === "RESOLVED" && !medical)} title={t === "RESOLVED" && !medical ? "Only medical personnel can resolve" : ""}
                onClick={() => doTransition(t)}>{t === "RESOLVED" ? "Resolve" : `Move to ${humanize(t)}`}</button>
            ))}
          </div>
          <Field label="Add a note to the record"><div className="inline-form"><input id="evnote" placeholder="e.g. Repeat SpO2 on second oximeter: 90 %" />
            <button className="btn" onClick={() => {
              const el = document.getElementById("evnote") as HTMLInputElement;
              if (!el.value.trim()) return;
              act.run(async () => { await post(`/medical-events/${e.id}/actions`, { action_type: "note", description: el.value.trim() }); el.value = ""; reload(); });
            }}>Add note</button></div></Field>
          </>}
        </Panel>
        <Panel title={<><LuFileText aria-hidden /> Medical reports</>} actions={!readOnly &&
          <button className="btn btn-quiet" disabled={act.busy} onClick={() => act.run(async () => { const r = await post(`/medical-events/${e.id}/reports`, { queue_for_transmission: true }); setReport(r); reload(); })}>Generate report</button>}>
          {e.reports.length === 0 ? <Empty>No reports yet. Escalating creates one automatically.</Empty> : (
            <ul className="plain-list">
              {e.reports.map((r: any) => (
                <li key={r.id}><button className="linkish" onClick={() => get(`/medical-reports/${r.id}`).then(setReport)}>{r.id}</button>
                  <span className="muted"> · {fmtTime(r.created_at)} · {humanize(r.sync_status)}</span></li>
              ))}
            </ul>
          )}
          <p className="muted small">Reports are private medical communication. Transmission status: local → queued → transmitted → acknowledged.</p>
        </Panel>
      </div>

      <Panel title="Event timeline">
        <ol className="timeline">
          {timeline.map((t, i) => <li key={i} className={`tl-${t.kind}`}><time>{fmtTime(t.at)}</time><span>{t.text}</span><small>{t.who}</small></li>)}
        </ol>
      </Panel>
      <Drawer open={!!report} onClose={() => setReport(null)} title={`Medical report ${report?.id || ""}`}>
        {report && <>
          <KV items={[["Transmission", report.transmission ? `${humanize(report.transmission.status)}${report.transmission.acknowledged_by ? ` by ${report.transmission.acknowledged_by}` : ""}` : "local only"]]} />
          <pre className="report">{report.rendered_text}</pre>
        </>}
      </Drawer>
      <ObservationDrawer id={obs} onClose={() => setObs(null)} />
    </>
  );
}
