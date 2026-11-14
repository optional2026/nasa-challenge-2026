// Sign-in screen. Crew members (astronauts and the Crew Medical Officer) select their profile — a simplified,
// credential-free simulation sign-in that does NOT verify identity. Earth-side accounts (administrator,
// ground flight surgeon) still sign in with a password. Roles are always enforced by the server.
import { useEffect, useState } from "react";
import { LuEarth, LuLock, LuRocket } from "react-icons/lu";
import { auth, get, post } from "../lib/api";
import { ROLE_LABEL } from "../lib/format";
import { Avatar, ErrorBox, Loading } from "../components/ui";

interface CrewProfile {
  user_id: number; username: string; display_name: string; role: string; astronaut_id: string; name: string;
  call_sign: string | null; crew_role: string | null; crew: string | null; mission_id: string | null; mission_name: string | null;
}
interface EarthAccount { username: string; display_name: string; role: string }

export default function Login({ onLogin }: { onLogin: (u: any) => void }) {
  const [profiles, setProfiles] = useState<{ crew: CrewProfile[]; earth: EarthAccount[]; notice: string } | null>(null);
  const [loadErr, setLoadErr] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [earthUser, setEarthUser] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [cfg, setCfg] = useState<any>({ show_demo_password: true });

  useEffect(() => {
    get("/public-config").then(setCfg).catch(() => {});
    get("/auth/profiles").then(setProfiles).catch(setLoadErr);
  }, []);

  const finish = (r: any) => { auth.set(r.token); onLogin(r.user); };

  const select = async (p: CrewProfile) => {
    setBusy(p.username); setErr(null);
    try { finish(await post("/auth/select-profile", { user_id: p.user_id })); }
    catch (ex) { setErr(ex); } finally { setBusy(null); }
  };

  const signIn = async (e: any) => {
    e.preventDefault();
    if (!earthUser) return;
    setBusy(earthUser); setErr(null);
    try { finish(await post("/auth/login", { username: earthUser, password })); }
    catch (ex) { setErr(ex); } finally { setBusy(null); }
  };

  // group crew profiles by mission + crew
  const groups: Record<string, CrewProfile[]> = {};
  (profiles?.crew || []).forEach((p) => {
    const k = `${p.mission_name || "Unassigned mission"}|${p.crew || "Unassigned crew"}`;
    (groups[k] = groups[k] || []).push(p);
  });

  return (
    <div className="login">
      <div className="login-card wide">
        <div className="login-title">
          <span className="brand-mark big" aria-hidden />
          <div>
            <h1>ASTRA</h1>
            <p>Astronaut Self-assessment, Tracking and Response Assistant</p>
          </div>
        </div>

        <section aria-labelledby="crew-h" className="stack">
          <h2 id="crew-h" className="login-h"><LuRocket aria-hidden /> Select your crew profile</h2>
          {loadErr && <ErrorBox error={loadErr} onRetry={() => { setLoadErr(null); get("/auth/profiles").then(setProfiles).catch(setLoadErr); }} />}
          {!profiles && !loadErr && <Loading label="Loading crew profiles" />}
          {profiles && profiles.crew.length === 0 && <p className="muted">No active crew profiles. Ask the mission administrator to register one.</p>}
          {Object.entries(groups).map(([k, list]) => {
            const [mission, crew] = k.split("|");
            return (
              <div key={k} className="profile-group">
                <p className="profile-group-h"><strong>{crew}</strong> · {mission}</p>
                <ul className="profile-grid">
                  {list.map((p) => (
                    <li key={p.user_id}>
                      <button type="button" className="profile-card" data-username={p.username} disabled={!!busy} onClick={() => select(p)}
                        aria-label={`Sign in as ${p.name}, ${ROLE_LABEL[p.role]}`}>
                        <Avatar name={p.name} seed={p.astronaut_id} size={52} />
                        <span className="profile-text">
                          <strong>{p.name}</strong>
                          <span className={`role-tag role-${p.role}`}>{ROLE_LABEL[p.role]}</span>
                          <small>{[p.crew_role, p.call_sign ? `“${p.call_sign}”` : null].filter(Boolean).join(" · ")}</small>
                        </span>
                        {busy === p.username && <span className="muted small">Entering…</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          <p className="note warn small" role="note">{profiles?.notice || "Crew profile selection is a simulation sign-in without credentials. It does not verify identity and is not suitable for an operational medical system."}</p>
        </section>

        <section aria-labelledby="earth-h" className="stack earth-signin">
          <h2 id="earth-h" className="login-h"><LuEarth aria-hidden /> Mission Control (Earth)</h2>
          <div className="btn-row">
            {(profiles?.earth || []).map((e) => (
              <button key={e.username} type="button" data-username={e.username} className={`btn earth-account ${earthUser === e.username ? "btn-primary" : ""}`}
                onClick={() => { setEarthUser(e.username); setErr(null); if (cfg.show_demo_password) setPassword("astra-demo"); }}>
                <LuLock aria-hidden /> {e.display_name} <small className="muted">· {ROLE_LABEL[e.role]}</small>
              </button>
            ))}
          </div>
          {earthUser && (
            <form onSubmit={signIn} className="inline-signin">
              <input type="hidden" name="username" value={earthUser} autoComplete="username" />
              <label className="field"><span className="field-label">Password for {earthUser}</span>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required autoFocus /></label>
              <button className="btn btn-primary" disabled={!!busy}>{busy === earthUser ? "Signing in…" : "Sign in"}</button>
            </form>
          )}
          <p className="muted small">Earth-side accounts manage users and missions and still require a password.
            {cfg.show_demo_password ? <> Demo password: <code>astra-demo</code></> : <> Use the password provided by the ASTRA team.</>}</p>
        </section>

        <ErrorBox error={err} />
        <p className="fineprint">Decision-support prototype for the NASA Space Apps Challenge 2026. Not an autonomous doctor and not a diagnostic device. All crew identities and data shown are fictional and synthetic.</p>
      </div>
    </div>
  );
}
