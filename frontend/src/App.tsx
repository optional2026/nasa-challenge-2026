import { useEffect, useState } from "react";
import {
  LuBookOpen, LuChartLine, LuClipboardList, LuCloudOff, LuLayoutDashboard, LuLogOut, LuOrbit, LuPersonStanding,
  LuSatelliteDish, LuSettings2, LuSiren, LuUserPlus, LuUsers,
} from "react-icons/lu";
import { DemoDataButton } from "./components/DemoData";
import { Avatar } from "./components/ui";
import { auth } from "./lib/api";
import { ROLE_LABEL, humanize } from "./lib/format";
import { HEALTH_EVENTS, useApp, useData } from "./lib/store";
import Analytics from "./pages/Analytics";
import BodySystems from "./pages/BodySystems";
import CrewOverview from "./pages/CrewOverview";
import Environment from "./pages/Environment";
import Library from "./pages/Library";
import Login from "./pages/Login";
import MedicalResponse from "./pages/MedicalResponse";
import Operations from "./pages/Operations";
import Overview from "./pages/Overview";
import Routine from "./pages/Routine";
import Users from "./pages/Users";

const PAGES = [
  { id: "crew", label: "Crew overview", icon: LuUsers, el: CrewOverview },
  { id: "overview", label: "Mission overview", icon: LuLayoutDashboard, el: Overview },
  { id: "body", label: "Body systems", icon: LuPersonStanding, el: BodySystems },
  { id: "analytics", label: "Health analytics", icon: LuChartLine, el: Analytics },
  { id: "response", label: "Medical response", icon: LuSiren, el: MedicalResponse },
  { id: "routine", label: "Daily routine", icon: LuClipboardList, el: Routine },
  { id: "environment", label: "Mission environment", icon: LuOrbit, el: Environment },
  { id: "library", label: "Knowledge library", icon: LuBookOpen, el: Library },
  { id: "ops", label: "Mission operations", icon: LuSettings2, el: Operations },
  { id: "users", label: "User management", icon: LuUserPlus, el: Users },
];
const HEALTH_PAGES = new Set(["overview", "body", "analytics", "response", "routine"]);
// Navigation mirrors the server-side permissions (the server enforces them regardless of what is shown).
//  astronaut: own dashboard, routine, analytics, alerts/response, health records (+ shared environment & library)
//  CMO: astronaut pages + crew overview + mission operations (baselines, sync)
//  administrator: crew overview, user management, read-only health records, mission operations
function pageAllowed(id: string, role: string): boolean {
  if (id === "crew") return role === "medical_officer" || role === "flight_surgeon" || role === "admin";
  if (id === "users") return role === "admin";
  if (id === "ops") return role !== "astronaut";
  return true;
}
function pageLabel(id: string, label: string, role: string): string {
  if (id === "overview") return role === "astronaut" ? "My dashboard" : "Astronaut dashboard";
  if (id === "body") return "Health records";
  if (id === "response") return role === "astronaut" ? "Alerts & response" : label;
  return label;
}

function MissionClock({ start }: { start?: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  if (!start) return null;
  const s = Math.max(0, (now - new Date(start).getTime()) / 1000);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    <div className="clock" title="Mission elapsed time (days/hours:minutes:seconds) and UTC">
      <span className="met">MET {d}/{pad(h)}:{pad(m)}:{pad(sec)}</span>
      <span className="utc">{new Date(now).toISOString().slice(11, 19)} UTC</span>
    </div>
  );
}

export default function App() {
  const { user, setUser, route, navigate, crew, astronautId, setAstronautId, connected, serverReachable, outboxCount, toasts, version } = useApp();
  const { data: mission } = useData<any[]>(user ? "/missions" : null, ["sync.link"]);
  const { data: sim } = useData<any>(user ? "/simulator" : null, ["simulator.status", "simulator.reset"]);
  const { data: openAlerts } = useData<any[]>(user && astronautId ? `/alerts?status=open&astronaut_id=${astronautId}` : null, HEALTH_EVENTS, [astronautId]);
  if (!user) return <Login onLogin={setUser} />;
  const m = mission?.[0];
  const isAdmin = user.role === "admin";
  let pageId = route.page;
  if (!PAGES.find((p) => p.id === pageId) || !pageAllowed(pageId, user.role)) pageId = isAdmin || user.role === "flight_surgeon" ? "crew" : "overview";
  const viewed = crew.find((c) => c.id === astronautId);
  const viewingSelf = !!user.astronaut_id && user.astronaut_id === astronautId;
  const Page = PAGES.find((p) => p.id === pageId)!.el;
  const urgent = (openAlerts || []).filter((a) => a.severity === "URGENT").length;
  const simState = sim?.state;

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="rail">
        <div className="brand"><span className="brand-mark" aria-hidden /> <span>ASTRA</span></div>
        <nav aria-label="Main">
          {PAGES.filter((p) => pageAllowed(p.id, user.role)).map((p) => (
            <a key={p.id} href={`#/${p.id}`} className={pageId === p.id ? "active" : ""} aria-current={pageId === p.id ? "page" : undefined}>
              <p.icon aria-hidden /> <span>{pageLabel(p.id, p.label, user.role)}</span>
              {p.id === "response" && urgent > 0 && <b className="badge-urgent" aria-label={`${urgent} urgent`}>{urgent}</b>}
            </a>
          ))}
        </nav>
        <div className="rail-foot">
          <div className="who"><strong>{user.display_name}</strong><span>{ROLE_LABEL[user.role]}</span></div>
          <button className="btn btn-quiet" onClick={() => { auth.set(null); setUser(null); }}><LuLogOut aria-hidden /> Sign out</button>
        </div>
      </aside>
      <div className="main-col">
        <header className="strip">
          <div className="strip-mission">
            <strong>{m?.name || "Mission"}</strong>
            {m && <span>Day {m.mission_day} · {m.current_phase?.phase} · {m.current_phase?.gravity_g === 0 ? "microgravity" : `${m.current_phase?.gravity_g} g`}</span>}
          </div>
          <MissionClock start={m?.start_utc} />
          <div className="strip-status">
            <span className={`link link-${m?.earth_link_status}`} title="Earth link (store-and-forward)">
              <LuSatelliteDish aria-hidden /> Earth link {m?.earth_link_status}{m ? ` · ${Math.round(m.comm_delay_seconds / 60 * 10) / 10} min delay` : ""}
            </span>
            <span className={`live ${connected ? "on" : "off"}`} title="Real-time connection to the onboard ASTRA server">
              {connected ? "Live" : serverReachable ? "Reconnecting" : <><LuCloudOff aria-hidden /> Onboard server unreachable</>}
            </span>
            {outboxCount > 0 && <span className="chip chip-attn">{outboxCount} unsent</span>}
            {user.astronaut_id && (user.role === "astronaut" || user.role === "medical_officer") && <DemoDataButton />}
            {simState && simState !== "idle" && (
              <a href="#/ops" className={`chip chip-sim sim-${simState}`}>Simulator {humanize(simState)}{sim?.scenario ? ` · ${humanize(sim.scenario)}` : ""}</a>
            )}
          </div>
          {crew.length > 0 && (
            <label className="ast-select">
              <span>Viewing records of</span>
              <select value={astronautId || ""} onChange={(e) => setAstronautId(e.target.value)} disabled={user.role === "astronaut"}>
                {crew.filter((c) => c.can_view_health).map((c) => <option key={c.id} value={c.id}>{c.name} · {c.crew_role}</option>)}
              </select>
            </label>
          )}
        </header>
        {urgent > 0 && pageId !== "response" && (
          <button className="urgent-banner" onClick={() => navigate("response")}>
            <LuSiren aria-hidden /> {urgent} urgent finding{urgent > 1 ? "s" : ""} — open the Medical Response Center
          </button>
        )}
        {HEALTH_PAGES.has(pageId) && viewed && (
          <div className={`viewing-banner ${viewingSelf ? "self" : "other"}`} role="status">
            <Avatar name={viewed.name} seed={viewed.id} size={28} />
            <span>{viewingSelf ? <>Your own health records · <b>{viewed.name}</b></>
              : <>Viewing the health records of <b>{viewed.name}</b> · {viewed.crew_role}{viewed.crew ? ` · ${viewed.crew}` : ""}</>}</span>
            {isAdmin && <span className="chip chip-plain" title="Administrators can view non-private records but cannot record data or take clinical actions">Read-only · administrator</span>}
            {!viewingSelf && (user.role === "medical_officer" || user.role === "flight_surgeon" || isAdmin) && <a className="linkish small" href="#/crew">Back to crew overview</a>}
          </div>
        )}
        <main id="main" tabIndex={-1}>
          <Page key={pageId + (astronautId || "")} />
        </main>
      </div>
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast toast-${t.tone}`}>{t.msg}</div>)}
      </div>
    </div>
  );
}
