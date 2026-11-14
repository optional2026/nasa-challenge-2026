// Inspect one observation: value, original unit, provenance, quality, linked assessments and alerts.
import { useEffect, useState } from "react";
import { get } from "../lib/api";
import { fmtTime, fmtValue, humanize, unit } from "../lib/format";
import { Chip, Drawer, ErrorBox, KV, Loading, Severity, Synthetic } from "./ui";

export function ObservationDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const [o, setO] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  useEffect(() => {
    setO(null); setErr(null);
    if (id) get(`/measurements/${encodeURIComponent(id)}`).then(setO).catch(setErr);
  }, [id]);
  return (
    <Drawer open={!!id} onClose={onClose} title="Observation">
      <ErrorBox error={err} />
      {!o && !err && <Loading />}
      {o && (
        <div className="stack">
          <div className="obs-head">
            <span className="big-value">{fmtValue(o.value, o.unit, o.metric_code)} <small>{unit(o.unit)}</small></span>
            <span>{o.indicator?.name || humanize(o.metric_code)}</span>
            <Synthetic show={o.is_synthetic} />
          </div>
          <KV items={[
            ["Observation ID", <code>{o.id}</code>],
            ["Measured", fmtTime(o.measured_at)],
            ["Received", fmtTime(o.received_at)],
            ["As submitted", `${JSON.stringify(o.original_value)} ${o.original_unit}`],
            ["Source", humanize(o.source_type)],
            ["Device", o.device ? `${o.device.id} · ${o.device.model}${o.device.is_simulated ? " (simulated)" : ""}` : "—"],
            ["Quality", <Chip tone={o.quality === "valid" ? "ok" : "attn"}>{o.quality}</Chip>],
            ["Context", Object.keys(o.context || {}).length ? Object.entries(o.context).map(([k, v]) => `${humanize(k)}: ${v}`).join("; ") : "—"],
            ["Location", o.location || "—"],
            ["Entered by", o.entered_by],
            ["Notes", o.notes || "—"],
          ]} />
          {o.symptoms?.length > 0 && <div><h3>Reported with</h3>{o.symptoms.map((s: any) => <Chip key={s.id}>{humanize(s.value)}</Chip>)}</div>}
          <div>
            <h3>Used in assessments</h3>
            {o.assessments.length ? o.assessments.slice(0, 8).map((a: any) => <div key={a.id} className="row-line"><code>{a.id}</code> {humanize(a.status)} · {fmtTime(a.created_at)}</div>) : <p className="muted">Not part of any assessment yet.</p>}
          </div>
          <div>
            <h3>Linked alerts</h3>
            {o.alerts.length ? o.alerts.map((a: any) => <div key={a.id} className="row-line"><Severity value={a.severity} /> {a.title}</div>) : <p className="muted">None.</p>}
          </div>
          {o.indicator?.limitations && <p className="note">{o.indicator.limitations}</p>}
        </div>
      )}
    </Drawer>
  );
}
