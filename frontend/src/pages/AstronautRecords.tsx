// Individual astronaut records for Earth-based personnel (administrator, ground flight surgeon).
// Ground staff have no personal health record; they select an astronaut under their responsibility and inspect
// that astronaut's real records. The existing astronaut components are reused unchanged, so the views are
// identical to what the crew sees (the server applies role and privacy filtering).
import { EarthFreshness, GroundNotes } from "../components/EarthLink";
import { Avatar, Empty, Tabs } from "../components/ui";
import { useApp } from "../lib/store";
import Analytics from "./Analytics";
import BodySystems from "./BodySystems";
import Overview from "./Overview";
import Routine from "./Routine";

// Sub-views keep their original route ids, so links inside the reused components (e.g. "Open in analytics")
// keep working: App renders this wrapper for these ids when the user is Earth-based.
export const RECORD_TABS: [string, string][] = [
  ["overview", "Summary"], ["body", "Body systems & measurements"], ["analytics", "Trends & history"], ["routine", "Logs & assessments"],
];
const VIEWS: Record<string, any> = { overview: Overview, body: BodySystems, analytics: Analytics, routine: Routine };

export default function AstronautRecords() {
  const { crew, astronautId, setAstronautId, route, navigate, user, side } = useApp();
  const tab = VIEWS[route.page] ? route.page : "overview";
  const viewable = crew.filter((c) => c.can_view_health);
  const View = VIEWS[tab];
  return (
    <div className="stack">
      <div className="page-head">
        <h1>{user?.role === "flight_surgeon" ? "Astronaut medical records" : "Astronaut records"}</h1>
        <p className="muted">{user?.role === "admin"
          ? "Read-only: administrators review non-private records but do not record data or take clinical actions. Private behavioral-health content is restricted to the astronaut and the flight surgeon."
          : "Medical oversight of your assigned mission. Measurements, logs, trends, assessments and alerts of the selected astronaut."}</p>
      </div>
      {viewable.length === 0 ? <Empty>No astronauts are assigned to your responsibility.</Empty> : <>
        <div className="record-picker" role="group" aria-label="Select astronaut">
          {viewable.map((c) => (
            <button key={c.id} className={`btn ${c.id === astronautId ? "btn-primary" : ""}`} aria-pressed={c.id === astronautId} onClick={() => setAstronautId(c.id)}>
              <Avatar name={c.name} seed={c.id} size={22} /> {c.name} <small>· {c.crew_role}</small>
            </button>
          ))}
        </div>
        {side === "earth" && astronautId && <EarthFreshness astronautId={astronautId} />}
        <Tabs tabs={RECORD_TABS} value={tab} onChange={(t) => navigate(t)} />
        {astronautId && <View key={tab + astronautId} />}
        {side === "earth" && astronautId && <GroundNotes key={"gn" + astronautId} astronautId={astronautId} />}
      </>}
    </div>
  );
}
