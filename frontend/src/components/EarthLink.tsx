// Crew Side ↔ Earth Side synchronization UI.
//  * EarthLinkChip      — header indicator (onboard: Earth link + queue; Earth: freshness of spacecraft data)
//  * EarthLinkPanel     — onboard status panel; for the CMO it carries the DEMONSTRATION link-simulation control
//  * UnsyncedRecords    — crew records not yet acknowledged by Earth
//  * EarthFreshness     — Earth: what has arrived from the spacecraft and how old it is (never shown as live)
//  * GroundNotes        — ground follow-up notes (written on Earth by the flight surgeon, delivered to the crew)
// Every state shown here comes from the server; the buttons only call backend endpoints that enforce the CMO role.
import { useState } from "react";
import { LuCloudOff, LuMessageSquareText, LuRefreshCw, LuSatelliteDish, LuUnplug, LuPlug } from "react-icons/lu";
import { post } from "../lib/api";
import { ago, fmtTime, humanize } from "../lib/format";
import { useApp, useData } from "../lib/store";
import { Chip, Empty, ErrorBox, KV, Loading, Panel, useAsyncAction } from "./ui";

const LINK_EVENTS = ["replication.status", "sync.link", "replication.received", "observations.created"];

const LINK_TEXT: Record<string, [string, string]> = {
  available: ["Earth connection available", "online"],
  unavailable_simulated: ["Earth connection unavailable (simulated outage)", "offline"],
  unreachable: ["Earth connection unavailable (Earth server unreachable)", "offline"],
  checking: ["Checking Earth connection…", "degraded"],
  not_configured: ["Earth connection not configured", "degraded"],
};
const SYNC_TEXT: Record<string, [string, string]> = {
  complete: ["Synchronization complete", "ok"], pending: ["Synchronization pending", "attn"],
  in_progress: ["Synchronization in progress", "plain"], failed: ["Synchronization failed — retrying", "urgent"],
  rejected: ["Some records were rejected by Earth", "urgent"],
};

export function useLink() {
  const { side, user } = useApp();
  return useData<any>(user && side !== "standalone" ? "/link" : null, LINK_EVENTS);
}

export function EarthLinkChip() {
  const { side } = useApp();
  const { data } = useLink();
  if (!data) return null;
  if (side === "earth") {
    return (
      <span className="link link-degraded" title="Earth Side server: data is the latest received from the spacecraft, not live">
        <LuSatelliteDish aria-hidden /> Spacecraft data {data.last_received_at ? `received ${ago(data.last_received_at)}` : "not yet received"}
      </span>
    );
  }
  const [label, tone] = LINK_TEXT[data.link_state] || [humanize(data.link_state), "degraded"];
  return (
    <a href="#/crew" className={`link link-${tone}`} title={`${label}. ${data.unsynced} record(s) waiting for Earth. Last successful synchronization: ${data.last_success_at ? fmtTime(data.last_success_at) : "never"}`}>
      {tone === "offline" ? <LuCloudOff aria-hidden /> : <LuSatelliteDish aria-hidden />}
      {data.link_state === "available" ? "Earth link available" : data.link_state === "unavailable_simulated" ? "Earth link unavailable · simulated" : label}
      {data.unsynced > 0 && <b> · {data.unsynced} pending</b>}
    </a>
  );
}

export function EarthLinkPanel({ compact = false }: { compact?: boolean }) {
  const { user, toast } = useApp();
  const { data, error, reload } = useLink();
  const act = useAsyncAction();
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading Earth link status" />;
  const cmo = user?.role === "medical_officer";
  const [linkLabel, linkTone] = LINK_TEXT[data.link_state] || [humanize(data.link_state), "degraded"];
  const [syncLabel, syncTone] = SYNC_TEXT[data.sync_state] || [humanize(data.sync_state), "plain"];
  const call = (path: string, msg: string) => act.run(async () => { await post(path); toast(msg, "ok"); reload(); });
  return (
    <Panel title={<><LuSatelliteDish aria-hidden /> Earth connection &amp; synchronization</>}
      tone={data.link_state === "available" ? undefined : "attn"}
      actions={cmo && data.simulation_allowed && (data.simulated_outage
        ? <button className="btn btn-primary" disabled={act.busy} onClick={() => call("/link/simulation/restore", "Earth connection restored — pending records are being transmitted")}><LuPlug aria-hidden /> Restore Earth Connection</button>
        : <button className="btn btn-urgent" disabled={act.busy} onClick={() => call("/link/simulation/outage", "Simulated Earth connection loss — records stay queued onboard")}><LuUnplug aria-hidden /> Simulate Earth Connection Loss</button>)}>
      <div className="btn-row">
        <span className="live on" title="This page is served by the onboard ASTRA server on the spacecraft network">Connected to onboard server</span>
        <span className={`link link-${linkTone}`}>{linkTone === "offline" ? <LuCloudOff aria-hidden /> : <LuSatelliteDish aria-hidden />} {linkLabel}</span>
        <Chip tone={syncTone}>{syncLabel}</Chip>
      </div>
      {data.simulated_outage && (
        <div className="note warn" role="status">
          <b>Demonstration:</b> the onboard↔Earth link is held down by a simulated outage
          {data.simulated_outage_changed_by ? ` (set by ${data.simulated_outage_changed_by.replace("user:", "")} ${ago(data.simulated_outage_changed_at)})` : ""}.
          The onboard server, the spacecraft network, assessments, alerts and crew monitoring keep working; new records are saved
          onboard and wait in the synchronization queue. Nothing is sent to Earth until the connection is restored.
        </div>
      )}
      <KV items={[
        ["Waiting for Earth", <b className={data.unsynced ? "attn" : ""}>{data.unsynced} record{data.unsynced === 1 ? "" : "s"}</b>],
        ["Last successful synchronization", data.last_success_at ? `${fmtTime(data.last_success_at)} (${ago(data.last_success_at)})` : "never"],
        ["Acknowledged by Earth", data.counts.SYNCED],
        ...(!compact ? [["Sending now", data.counts.SENDING], ["Failed (will retry)", data.counts.FAILED],
          ["Rejected by Earth", data.counts.REJECTED], ["Earth server", `${data.earth_server || "not configured"}${data.encrypted_transport ? " · TLS" : " · local HTTP (demo)"}`]] as [string, any][] : []),
      ]} />
      {data.counts.REJECTED > 0 && <div className="note warn">{data.counts.REJECTED} record(s) were rejected by the Earth server and are kept onboard unchanged — see the list below and the audit log.</div>}
      {data.last_error && data.link_state !== "available" && !data.simulated_outage && <div className="note warn">{data.last_error}</div>}
      {cmo && data.simulation_allowed && <p className="muted small">The connection-loss button is a clearly identified <b>demonstration control</b>: it blocks only the server-to-server synchronization
        between this onboard server and the Earth server. It is not a network-management control and does not change or delete any record.</p>}
      {cmo && !data.simulation_allowed && <p className="muted small">The Earth-link demonstration control is disabled on this deployment.</p>}
      <UnsyncedRecords />
    </Panel>
  );
}

export function UnsyncedRecords() {
  const { user } = useApp();
  const { data } = useData<any>("/replication/unsynced", LINK_EVENTS);
  const act = useAsyncAction();
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const items: any[] = data.items;
  const byAst: Record<string, number> = {};
  items.forEach((i) => { const k = i.astronaut_name || "Cabin / environment"; byAst[k] = (byAst[k] || 0) + 1; });
  return (
    <details open={open} onToggle={(e: any) => setOpen(e.target.open)}>
      <summary>{user?.role === "medical_officer" ? "Crew records not yet synchronized with Earth" : "Your records not yet synchronized with Earth"} ({items.length}{items.length >= 100 ? "+" : ""})
        {Object.entries(byAst).map(([k, n]) => <Chip key={k}>{k}: {n}</Chip>)}</summary>
      {items.length === 0 ? <Empty>Every record has been acknowledged by the Earth server.</Empty> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Record</th><th>Astronaut</th><th>Original time</th><th>Status</th><th>Attempts</th></tr></thead>
          <tbody>{items.map((i) => (
            <tr key={i.record_type + i.record_id + i.status}>
              <td>{humanize(i.record_type)}{i.metric_code ? ` · ${humanize(i.metric_code)}` : ""}{i.is_private && <Chip tone="attn">Private</Chip>}</td>
              <td>{i.astronaut_name || "—"}</td>
              <td className="small">{i.original_time ? fmtTime(i.original_time) : "—"}</td>
              <td><Chip tone={i.status === "REJECTED" || i.status === "FAILED" ? "attn" : "plain"}>{i.status}</Chip>{i.last_error && <div className="muted small">{i.last_error}</div>}</td>
              <td>{i.attempts}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {user?.role === "medical_officer" && data.status?.link_state === "available" && items.length > 0 && (
        <button className="btn btn-quiet" disabled={act.busy} onClick={() => act.run(async () => { await post("/replication/run"); })}><LuRefreshCw aria-hidden /> Synchronize now</button>
      )}
    </details>
  );
}

export function EarthFreshness({ astronautId }: { astronautId?: string | null }) {
  const { crew } = useApp();
  const { data } = useData<any>("/link", ["replication.received", "observations.created"]);
  if (!data) return <Loading />;
  const name = (id: string) => crew.find((c) => c.id === id)?.name || id;
  const rows = (data.per_astronaut || []).filter((p: any) => !astronautId || p.astronaut_id === astronautId);
  if (astronautId) {
    const p = rows[0];
    return (
      <div className="note" role="status">
        <b>Synchronized data, not live.</b> {p
          ? <>Newest measurement taken aboard {p.latest_measured_at ? `${fmtTime(p.latest_measured_at)} (${ago(p.latest_measured_at)})` : "—"} · last record received on Earth {ago(p.last_received_at)}.</>
          : <>No records from this astronaut have reached the Earth server yet; only pre-flight reference data is shown.</>}
        {" "}Records recorded aboard since then appear only after the next successful synchronization.
      </div>
    );
  }
  return (
    <Panel title={<><LuSatelliteDish aria-hidden /> Data received from the spacecraft</>}>
      <p className="muted small">{data.freshness_note}</p>
      <KV items={[["Last synchronization received", data.last_received_at ? `${fmtTime(data.last_received_at)} (${ago(data.last_received_at)})` : "never"],
        ["Spacecraft server", data.peer], ["Records received", data.records_received],
        ["Ground notes awaiting delivery to the crew", data.notes_pending_delivery]]} />
      {rows.length > 0 && (
        <div className="table-wrap"><table>
          <thead><tr><th>Astronaut</th><th>Newest measurement (taken aboard)</th><th>Last received on Earth</th><th>Records</th></tr></thead>
          <tbody>{rows.map((p: any) => (
            <tr key={p.astronaut_id || "env"}><td>{p.astronaut_id ? name(p.astronaut_id) : "Cabin / environment"}</td>
              <td className="small">{p.latest_measured_at ? `${fmtTime(p.latest_measured_at)} (${ago(p.latest_measured_at)})` : "—"}</td>
              <td className="small">{ago(p.last_received_at)}</td><td>{p.records}</td></tr>))}</tbody>
        </table></div>
      )}
    </Panel>
  );
}

export function GroundNotes({ astronautId }: { astronautId?: string | null }) {
  const { user, side, toast } = useApp();
  const path = `/ground/annotations${astronautId ? `?astronaut_id=${astronautId}` : ""}`;
  const { data, reload } = useData<any>(user && side !== "standalone" ? path : null,
    ["ground_annotation.created", "ground_annotation.received"], [astronautId]);
  const [text, setText] = useState("");
  const [kind, setKind] = useState("follow_up");
  const act = useAsyncAction();
  if (side === "standalone" || !data) return null;
  const canWrite = side === "earth" && user?.role === "flight_surgeon" && astronautId;
  return (
    <Panel title={<><LuMessageSquareText aria-hidden /> Ground follow-up notes</>}>
      <p className="muted small">{side === "earth"
        ? "Written on Earth as separate, attributable notes — onboard records are never edited from Earth. Delivered to the Crew Medical Officer at the next synchronization."
        : "Notes from the ground medical team, received at the last synchronization with Earth."}</p>
      {canWrite && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); act.run(async () => {
          await post("/ground/annotations", { astronaut_id: astronautId, kind, text: text.trim() }); setText(""); toast("Note queued for delivery to the crew", "ok"); reload(); }); }}>
          <div className="btn-row">
            <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Note type">
              <option value="follow_up">Follow-up</option><option value="request">Request to the CMO</option><option value="note">Note</option>
            </select>
          </div>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={4000} placeholder="Follow-up for the Crew Medical Officer…" aria-label="Note text" />
          <div className="btn-row"><button className="btn btn-primary" disabled={act.busy || !text.trim()}>Send to crew</button></div>
          <ErrorBox error={act.error} />
        </form>
      )}
      {data.items.length === 0 ? <Empty>No ground notes.</Empty> : (
        <ul className="stack plain-list">{data.items.map((n: any) => (
          <li key={n.id} className="note">
            <div className="small muted"><Chip>{humanize(n.kind)}</Chip>{n.author.replace("user:", "")} · written {fmtTime(n.created_at)}{n.astronaut_name && !astronautId ? ` · re ${n.astronaut_name}` : ""}
              {side === "earth" && <> · {n.delivered_at ? `delivered to the spacecraft ${ago(n.delivered_at)}` : "awaiting delivery to the spacecraft"}</>}
              {side === "onboard" && n.received_onboard_at && <> · received aboard {ago(n.received_onboard_at)}</>}</div>
            <div>{n.text}</div>
          </li>))}</ul>
      )}
    </Panel>
  );
}
