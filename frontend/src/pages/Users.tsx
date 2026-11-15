// User management for the Earth-based administrator: register crew accounts (with an initial password), assign
// mission and crew, reset crew passwords, assign the ground flight surgeon's mission, deactivate/re-activate.
// Existing passwords can never be viewed. Every action is authorized, validated and audited by the server.
import { useState } from "react";
import { LuUserPlus } from "react-icons/lu";
import { Avatar, Chip, Empty, ErrorBox, Field, Loading, Panel, useAsyncAction } from "../components/ui";
import { patch, post } from "../lib/api";
import { ROLE_LABEL, fmtTime } from "../lib/format";
import { useApp, useData } from "../lib/store";

const BLANK = { username: "", display_name: "", role: "astronaut", name: "", call_sign: "", crew_role: "", mission_id: "", crew: "Prime Crew",
  password: "", password2: "" };
const PW_MIN = 8;  // mirrors the server policy; the server is authoritative

function PasswordFields({ v, set }: { v: any; set: (k: string) => (e: any) => void }) {
  const mismatch = v.password2 !== "" && v.password !== v.password2;
  return <>
    <Field label="Password" hint={`At least ${PW_MIN} characters; not the username. Stored only as a hash.`}>
      <input type="password" value={v.password} onChange={set("password")} required minLength={PW_MIN} maxLength={128} autoComplete="new-password" />
    </Field>
    <Field label="Confirm password" hint={mismatch ? "Passwords do not match" : undefined}>
      <input type="password" value={v.password2} onChange={set("password2")} required minLength={PW_MIN} maxLength={128} autoComplete="new-password"
        aria-invalid={mismatch} />
    </Field>
  </>;
}

function PasswordReset({ u, onDone, onCancel, busy, run }:
  { u: any; onDone: () => void; onCancel: () => void; busy: boolean; run: (f: () => Promise<void>) => any }) {
  const [v, setV] = useState({ password: "", password2: "" });
  const set = (k: string) => (e: any) => setV({ ...v, [k]: e.target.value });
  return (
    <form className="form-grid" onSubmit={(e) => {
      e.preventDefault();
      if (v.password !== v.password2) return;
      run(async () => { await post(`/users/${u.id}/password`, { password: v.password }); onDone(); });
    }}>
      <p className="field wide muted small">Set a new password for <b>{u.display_name}</b> ({u.username}). The current password cannot be viewed; it is replaced.</p>
      <PasswordFields v={v} set={set} />
      <div className="btn-row field wide">
        <button className="btn btn-primary" disabled={busy || v.password !== v.password2}>Set new password</button>
        <button type="button" className="btn btn-quiet" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

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
      {!editing && <PasswordFields v={v} set={set} />}
      {editing && initial.role === "flight_surgeon" && (
        <Field label="Assigned mission" hint="The ground flight surgeon can access only this mission's crew records">
          <select value={v.mission_id} onChange={set("mission_id")}>
            <option value="">No mission (no record access)</option>
            {missions.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </Field>
      )}
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
        <button className="btn btn-primary" disabled={busy || (!editing && v.password !== v.password2)}>{editing ? "Save changes" : "Register account"}</button>
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
  const [pwId, setPwId] = useState<number | null>(null);
  const act = useAsyncAction();
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!users || !missions) return <Loading label="Loading users" />;
  const crews = Array.from(new Set(users.map((u) => u.astronaut?.crew).filter(Boolean))) as string[];

  const clean = (v: any) => {
    const out: any = {};
    Object.entries(v).forEach(([k, x]) => { out[k] = typeof x === "string" ? x.trim() : x; });
    ["call_sign", "crew_role"].forEach((k) => { if (out[k] === "") out[k] = null; });
    if (out.mission_id === "") delete out.mission_id;
    delete out.password2;
    return out;
  };
  const create = (v: any) => act.run(async () => {
    if (v.password !== v.password2) throw new Error("Passwords do not match");
    const r = await post("/users", { ...clean(v), password: v.password });
    toast(`Registered ${r.display_name} (${ROLE_LABEL[r.role]})`, "ok");
    setCreating(false); reload();
  });
  const save = (u: any, v: any) => act.run(async () => {
    const body: any = clean(v);
    const allowed = u.editable_role ? ["display_name", "role", "name", "call_sign", "crew_role", "mission_id", "crew"]
      : u.role === "flight_surgeon" ? ["display_name", "mission_id"] : ["display_name"];
    const payload: any = {};
    allowed.forEach((k) => { if (k in body) payload[k] = body[k]; });
    if (u.role === "flight_surgeon") payload.mission_id = v.mission_id || null;
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
        <p className="muted">Register crew accounts with an initial password, assign them to missions and crews, reset crew passwords and
          deactivate accounts. Every account signs in with a username and password; passwords are stored only as hashes and can never be
          viewed. Only Earth-side administrators can change accounts or roles.</p>
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
                pwId === u.id ? (
                  <tr key={u.id}><td colSpan={7}>
                    <PasswordReset u={u} busy={act.busy} run={act.run} onCancel={() => setPwId(null)}
                      onDone={() => { toast(`New password set for ${u.display_name}`, "ok"); setPwId(null); reload(); }} />
                  </td></tr>
                ) : editId === u.id ? (
                  <tr key={u.id}><td colSpan={7}>
                    <UserForm editing missions={missions} crews={crews} busy={act.busy} onCancel={() => setEditId(null)} onSubmit={(v) => save(u, v)}
                      initial={{ display_name: u.display_name, role: u.role, editable_role: u.editable_role, name: u.astronaut?.name || "",
                        call_sign: u.astronaut?.call_sign || "", crew_role: u.astronaut?.crew_role || "", mission_id: u.astronaut?.mission_id || "",
                        crew: u.astronaut?.crew || "Prime Crew", ...(u.role === "flight_surgeon" ? { mission_id: u.assigned_mission_id || "" } : {}) }} />
                  </td></tr>
                ) : (
                  <tr key={u.id} className={u.active ? "" : "inactive"}>
                    <td><span className="user-cell"><Avatar name={u.astronaut?.name || u.display_name} seed={u.astronaut_id || u.username} size={30} />
                      <span><strong>{u.display_name}</strong><small className="muted">{u.username}{u.astronaut_id ? ` · ${u.astronaut_id}` : ""}</small></span></span></td>
                    <td>{ROLE_LABEL[u.role] || u.role}</td>
                    <td>{u.astronaut ? <>{u.astronaut.mission_name || u.astronaut.mission_id}<br /><small className="muted">{u.astronaut.crew}{u.astronaut.crew_role ? ` · ${u.astronaut.crew_role}` : ""}</small></> : <span className="muted">Earth-based{u.role === "flight_surgeon" ? <><br /><small>{u.assigned_mission_id ? `Assigned: ${missions.find((m) => m.id === u.assigned_mission_id)?.name || u.assigned_mission_id}` : "No mission assigned"}</small></> : u.role === "admin" ? <><br /><small>All missions</small></> : null}</span>}</td>
                    <td>Password</td>
                    <td>{u.active ? <Chip tone="ok">Active</Chip> : <Chip tone="none">Deactivated</Chip>}</td>
                    <td className="small">{fmtTime(u.created_at)}</td>
                    <td className="btn-row">
                      <button className="btn btn-quiet" disabled={act.busy} onClick={() => { setEditId(u.id); setPwId(null); setCreating(false); }}>Edit</button>
                      {u.editable_role && <button className="btn btn-quiet" disabled={act.busy} onClick={() => { setPwId(u.id); setEditId(null); setCreating(false); }}>Reset password</button>}
                      {u.id !== user?.id && <button className="btn btn-quiet" disabled={act.busy} onClick={() => toggle(u)}>{u.active ? "Deactivate" : "Re-activate"}</button>}
                    </td>
                  </tr>
                )
              ))}
            </tbody>
          </table></div>
        )}
        <p className="muted small">Deactivating an account signs it out immediately and blocks sign-in; the astronaut's health records are kept.
          Administrator and flight-surgeon accounts are provisioned (and their passwords set) outside the application.</p>
      </Panel>
    </div>
  );
}
