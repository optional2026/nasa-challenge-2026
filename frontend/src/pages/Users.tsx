// User management for the Earth-based administrator: register crew accounts, assign mission and crew,
// edit details, deactivate/re-activate. Every action is authorized and audited by the server.
import { useState } from "react";
import { LuUserPlus } from "react-icons/lu";
import { Avatar, Chip, Empty, ErrorBox, Field, Loading, Panel, useAsyncAction } from "../components/ui";
import { patch, post } from "../lib/api";
import { ROLE_LABEL, fmtTime } from "../lib/format";
import { useApp, useData } from "../lib/store";

const BLANK = { username: "", display_name: "", role: "astronaut", name: "", call_sign: "", crew_role: "", mission_id: "", crew: "Prime Crew" };

function UserForm({ initial, missions, crews, editing, onSubmit, onCancel, busy }:
  { initial: any; missions: any[]; crews: string[]; editing: boolean; onSubmit: (v: any) => void; onCancel?: () => void; busy: boolean }) {
  const [v, setV] = useState<any>(initial);
  const set = (k: string) => (e: any) => setV({ ...v, [k]: e.target.value });
  const crewEditable = editing ? initial.editable_role !== false : true;
  return (
    <form className="form-grid" onSubmit={(e) => { e.preventDefault(); onSubmit(v); }}>
      {!editing && (
        <Field label="Username (lower-case)" hint="2–32 characters: a–z, 0–9, . _ -">
          <input value={v.username} onChange={set("username")} required pattern="[a-z][a-z0-9._\-]{1,31}" autoComplete="off" />
        </Field>
      )}
      <Field label="Display name"><input value={v.display_name} onChange={set("display_name")} required maxLength={80} /></Field>
      {crewEditable && <>
        <Field label="Role">
          <select value={v.role} onChange={set("role")}>
            <option value="astronaut">{ROLE_LABEL.astronaut}</option>
            <option value="medical_officer">{ROLE_LABEL.medical_officer}</option>
          </select>
        </Field>
        <Field label="Astronaut full name"><input value={v.name} onChange={set("name")} required maxLength={80} /></Field>
        <Field label="Call sign"><input value={v.call_sign} onChange={set("call_sign")} maxLength={24} /></Field>
        <Field label="Position"><input value={v.crew_role} onChange={set("crew_role")} maxLength={60} placeholder="e.g. Flight Engineer" /></Field>
        <Field label="Mission">
          <select value={v.mission_id} onChange={set("mission_id")}>
            {!editing && <option value="">Current mission</option>}
            {missions.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </Field>
        <Field label="Crew" hint="A Crew Medical Officer oversees astronauts in the same mission and crew">
          <input value={v.crew} onChange={set("crew")} required maxLength={40} list="crew-names" />
          <datalist id="crew-names">{crews.map((c) => <option key={c} value={c} />)}</datalist>
        </Field>
      </>}
      <div className="btn-row field wide">
        <button className="btn btn-primary" disabled={busy}>{editing ? "Save changes" : "Register account"}</button>
        {onCancel && <button type="button" className="btn btn-quiet" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}

export default function Users() {
  const { user, toast } = useApp();
  const { data: users, error, reload } = useData<any[]>("/users");
  const { data: missions } = useData<any[]>("/missions");
  const [creating, setCreating] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const act = useAsyncAction();
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!users || !missions) return <Loading label="Loading users" />;
  const crews = Array.from(new Set(users.map((u) => u.astronaut?.crew).filter(Boolean))) as string[];

  const clean = (v: any) => {
    const out: any = {};
    Object.entries(v).forEach(([k, x]) => { out[k] = typeof x === "string" ? x.trim() : x; });
    ["call_sign", "crew_role"].forEach((k) => { if (out[k] === "") out[k] = null; });
    if (out.mission_id === "") delete out.mission_id;
    return out;
  };
  const create = (v: any) => act.run(async () => {
    const r = await post("/users", clean(v));
    toast(`Registered ${r.display_name} (${ROLE_LABEL[r.role]})`, "ok");
    setCreating(false); reload();
  });
  const save = (u: any, v: any) => act.run(async () => {
    const body: any = clean(v);
    const allowed = u.editable_role ? ["display_name", "role", "name", "call_sign", "crew_role", "mission_id", "crew"] : ["display_name"];
    const payload: any = {};
    allowed.forEach((k) => { if (k in body) payload[k] = body[k]; });
    await patch(`/users/${u.id}`, payload);
    toast(`Saved ${payload.display_name || u.display_name}`, "ok");
    setEditId(null); reload();
  });
  const toggle = (u: any) => act.run(async () => {
    await post(`/users/${u.id}/${u.active ? "deactivate" : "activate"}`);
    toast(`${u.display_name} ${u.active ? "deactivated" : "re-activated"}`, "ok");
    reload();
  });

  return (
    <div className="stack">
      <div className="page-head">
        <h1>User management</h1>
        <p className="muted">Register crew accounts, assign them to missions and crews, and deactivate accounts. Crew members sign in by
          selecting their profile (simulation only — no identity verification). Only Earth-side administrators can change accounts or roles.</p>
      </div>
      <Panel title="Registered users" actions={!creating && <button className="btn btn-primary" onClick={() => { setCreating(true); setEditId(null); }}><LuUserPlus aria-hidden /> Register crew account</button>}>
        {creating && (
          <div className="note">
            <UserForm initial={BLANK} missions={missions} crews={crews} editing={false} onSubmit={create} onCancel={() => setCreating(false)} busy={act.busy} />
          </div>
        )}
        <ErrorBox error={act.error} />
        {users.length === 0 ? <Empty>No users.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>User</th><th>Role</th><th>Mission · crew</th><th>Sign-in</th><th>Status</th><th>Registered</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                editId === u.id ? (
                  <tr key={u.id}><td colSpan={7}>
                    <UserForm editing missions={missions} crews={crews} busy={act.busy} onCancel={() => setEditId(null)} onSubmit={(v) => save(u, v)}
                      initial={{ display_name: u.display_name, role: u.role, editable_role: u.editable_role, name: u.astronaut?.name || "",
                        call_sign: u.astronaut?.call_sign || "", crew_role: u.astronaut?.crew_role || "", mission_id: u.astronaut?.mission_id || "",
                        crew: u.astronaut?.crew || "Prime Crew" }} />
                  </td></tr>
                ) : (
                  <tr key={u.id} className={u.active ? "" : "inactive"}>
                    <td><span className="user-cell"><Avatar name={u.astronaut?.name || u.display_name} seed={u.astronaut_id || u.username} size={30} />
                      <span><strong>{u.display_name}</strong><small className="muted">{u.username}{u.astronaut_id ? ` · ${u.astronaut_id}` : ""}</small></span></span></td>
                    <td>{ROLE_LABEL[u.role] || u.role}</td>
                    <td>{u.astronaut ? <>{u.astronaut.mission_name || u.astronaut.mission_id}<br /><small className="muted">{u.astronaut.crew}{u.astronaut.crew_role ? ` · ${u.astronaut.crew_role}` : ""}</small></> : <span className="muted">Earth-based</span>}</td>
                    <td>{u.sign_in === "profile" ? "Profile selection" : "Password"}</td>
                    <td>{u.active ? <Chip tone="ok">Active</Chip> : <Chip tone="none">Deactivated</Chip>}</td>
                    <td className="small">{fmtTime(u.created_at)}</td>
                    <td className="btn-row">
                      <button className="btn btn-quiet" disabled={act.busy} onClick={() => { setEditId(u.id); setCreating(false); }}>Edit</button>
                      {u.id !== user?.id && <button className="btn btn-quiet" disabled={act.busy} onClick={() => toggle(u)}>{u.active ? "Deactivate" : "Re-activate"}</button>}
                    </td>
                  </tr>
                )
              ))}
            </tbody>
          </table></div>
        )}
        <p className="muted small">Deactivating an account signs it out immediately and removes it from the sign-in screen; the astronaut's health records are kept.
          Administrator and flight-surgeon accounts are provisioned outside the application.</p>
      </Panel>
    </div>
  );
}
