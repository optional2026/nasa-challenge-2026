// Light / Dark / System theme switcher (rail footer and sign-in page).
import { LuMonitor, LuMoon, LuSun } from "react-icons/lu";
import { ThemeChoice, useTheme } from "../lib/theme";

const OPTIONS: [ThemeChoice, string, any][] = [["light", "Light", LuSun], ["dark", "Dark", LuMoon], ["system", "System", LuMonitor]];

export default function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  return (
    <div className="theme-switch" role="group" aria-label="Colour theme">
      {OPTIONS.map(([v, label, Icon]) => (
        <button key={v} type="button" aria-pressed={theme === v} title={v === "system" ? "Follow the operating system setting" : `${label} theme`}
          onClick={() => setTheme(v)}>
          <Icon aria-hidden /> {label}
        </button>
      ))}
    </div>
  );
}
