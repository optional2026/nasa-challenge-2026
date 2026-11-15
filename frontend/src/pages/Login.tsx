// Sign-in screen. Every role — astronauts, the Crew Medical Officer, the ground flight surgeon and the mission
// administrator — signs in with a username and password. Passwords are verified by the server against a salted
// scrypt hash; no password is stored in or shipped with the frontend. Roles are always enforced by the server.
import { useEffect, useState } from "react";
import { LuEarth, LuLock, LuRocket } from "react-icons/lu";
import { auth, get, post } from "../lib/api";
import { ErrorBox } from "../components/ui";
import ThemeSwitch from "../components/ThemeSwitch";

// Demo account names only (not secrets). Passwords are documented in README.md, never in this bundle.
const DEMO_ACCOUNTS: [string, string, string][] = [
  ["vega", "Astronaut", "crew"], ["okafor", "Astronaut", "crew"], ["mori", "Crew Medical Officer", "crew"],
  ["ramirez", "Ground flight surgeon", "earth"], ["admin", "Mission administrator", "earth"],
];

export default function Login({ onLogin }: { onLogin: (u: any) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [cfg, setCfg] = useState<any>({ show_demo_password: false });

  const [unreachable, setUnreachable] = useState(false);
  useEffect(() => { get("/public-config").then((c) => { setCfg(c); setUnreachable(false); }).catch(() => setUnreachable(true)); }, []);

  const signIn = async (e: any) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await post("/auth/login", { username: username.trim().toLowerCase(), password });
      auth.set(r.token); onLogin(r.user);
    } catch (ex) { setErr(ex); setPassword(""); } finally { setBusy(false); }
  };

  return (
    <div className="login">
      <div className="login-theme"><ThemeSwitch /></div>
      <div className="login-card">
        <div className="login-title">
          <span className="brand-mark big" aria-hidden />
          <div>
            <h1>ASTRA</h1>
            <p>Astronaut Self-assessment, Tracking and Response Assistant</p>
          </div>
        </div>

        {cfg.deployment && cfg.deployment !== "standalone" && (
          <div className={`side-banner side-${cfg.deployment}`} role="note">
            {cfg.deployment === "onboard" ? <LuRocket aria-hidden /> : <LuEarth aria-hidden />}
            <div><strong>{cfg.side_label}</strong>
              <span>{cfg.deployment === "onboard"
                ? "Astronauts and the Crew Medical Officer sign in here. Works without any connection to Earth."
                : "Administrators and ground flight surgeons sign in here. Shows astronaut data received from the spacecraft."}</span></div>
          </div>
        )}
        <form onSubmit={signIn} className="stack" aria-labelledby="signin-h">
          <h2 id="signin-h" className="login-h"><LuLock aria-hidden /> Sign in</h2>
          <label className="field"><span className="field-label">Username</span>
            <input name="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
              autoCapitalize="none" spellCheck={false} required autoFocus /></label>
          <label className="field"><span className="field-label">Password</span>
            <input name="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" required /></label>
          <button className="btn btn-primary" disabled={busy || !username || !password}>{busy ? "Signing in…" : "Sign in"}</button>
          <ErrorBox error={err} />
          {unreachable && <div className="note warn" role="status">The ASTRA server cannot be reached. This page was opened from the browser's
            offline cache; sign-in and all health data need a connection to the server (on the spacecraft: the onboard server on the local network).</div>}
        </form>

        {cfg.show_demo_password && (
          <section className="stack demo-accounts" aria-labelledby="demo-h">
            <h2 id="demo-h" className="login-h small">Demonstration accounts</h2>
            <div className="btn-row">
              {DEMO_ACCOUNTS.filter(([, , side]) => !cfg.deployment || cfg.deployment === "standalone" || (cfg.deployment === "onboard") === (side === "crew")).map(([u, label, side]) => (
                <button key={u} type="button" data-username={u} className={`btn btn-quiet ${username === u ? "btn-primary" : ""}`}
                  onClick={() => { setUsername(u); setErr(null); }}>
                  {side === "crew" ? <LuRocket aria-hidden /> : <LuEarth aria-hidden />} {u} <small className="muted">· {label}</small>
                </button>
              ))}
            </div>
            <p className="muted small">Demo passwords are listed in the project README. They are shared demonstration passwords and must be changed before any real deployment.</p>
          </section>
        )}

        <p className="fineprint">Decision-support prototype for the NASA Space Apps Challenge 2026. Not an autonomous doctor and not a diagnostic device. All crew identities and data shown are fictional and synthetic.</p>
      </div>
    </div>
  );
}
