// Light / dark / system theme. The choice is stored per browser (localStorage) and applied as data-theme on <html>;
// "system" removes the attribute so the CSS follows prefers-color-scheme. public/theme-init.js applies the stored
// choice synchronously before the stylesheet paints (no flash of the wrong theme; CSP forbids inline scripts).
import { useEffect, useState } from "react";

export type ThemeChoice = "light" | "dark" | "system";
const KEY = "astra.theme";
const BG = { light: "#F4F8FF", dark: "#11131B" };

export function storedTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch { return "system"; }
}

function systemDark(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", choice);
  const effective = choice === "system" ? (systemDark() ? "dark" : "light") : choice;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BG[effective]);
}

export function useTheme(): [ThemeChoice, (t: ThemeChoice) => void] {
  const [theme, setThemeState] = useState<ThemeChoice>(storedTheme);
  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, [theme]);
  // keep several open tabs of the same server in sync
  useEffect(() => {
    const on = (e: StorageEvent) => { if (e.key === KEY) setThemeState(storedTheme()); };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);
  const setTheme = (t: ThemeChoice) => {
    try { t === "system" ? localStorage.removeItem(KEY) : localStorage.setItem(KEY, t); } catch { /* storage unavailable */ }
    setThemeState(t);
  };
  return [theme, setTheme];
}
