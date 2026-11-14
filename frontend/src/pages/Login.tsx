import { useState } from "react";
import { auth, post } from "../lib/api";
import { ROLE_LABEL } from "../lib/format";
import { ErrorBox } from "../components/ui";

const DEMO = [
  ["vega", "astronaut", "Cmdr. Elena Vega — sees only her own data"],
  ["okafor", "astronaut", "Amara Okafor — flight engineer"],
  ["mori", "medical_officer", "Dr. Kenji Mori — Crew Medical Officer (private check-ins redacted)"],
  ["ramirez", "flight_surgeon", "Dr. Lucia Ramirez — ground flight surgeon"],
  ["admin", "admin", "Systems administrator — no medical data"],
];

export default function Login({ onLogin }: { onLogin: (u: any) => void }) {
  const [username, setUsername] = useState("vega");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: any) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await post("/auth/login", { username, password });
      auth.set(r.token);
      onLogin(r.user);
    } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  return (
    <div className="login">
      <div className="login-card">
        <div className="login-title">
          <span className="brand-mark big" aria-hidden />
          <div>
            <h1>ASTRA</h1>
            <p>Astronaut Self-assessment, Tracking and Response Assistant</p>
          </div>
        </div>
        <form onSubmit={submit} className="stack">
          <label className="field"><span className="field-label">Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></label>
          <label className="field"><span className="field-label">Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
          <ErrorBox error={err} />
          <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <div className="demo-accounts">
          <p>Demonstration accounts (synthetic crew). Password for all: <code>astra-demo</code></p>
          <ul>
            {DEMO.map(([u, role, desc]) => (
              <li key={u}><button type="button" className="linkish" onClick={() => { setUsername(u); setPassword("astra-demo"); }}>{u}</button>
                <span>{ROLE_LABEL[role]} · {desc}</span></li>
            ))}
          </ul>
        </div>
        <p className="fineprint">Decision-support prototype for the NASA Space Apps Challenge 2026. Not an autonomous doctor and not a diagnostic device. All crew data shown is synthetic.</p>
      </div>
    </div>
  );
}
