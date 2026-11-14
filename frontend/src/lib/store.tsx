// Application state: session, selected astronaut, live WebSocket feed and data hooks.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { ApiError, auth, flushOutbox, get, outbox, setUnauthorizedHandler } from "./api";

export interface User { id: number; username: string; display_name: string; role: string; astronaut_id: string | null }
export interface LiveEvent { type: string; at: string; astronaut_id: string | null; private: boolean; payload: any }

interface Ctx {
  user: User | null;
  setUser: (u: User | null) => void;
  astronautId: string | null;
  setAstronautId: (a: string) => void;
  crew: any[];
  connected: boolean;
  serverReachable: boolean;
  events: LiveEvent[];
  version: Record<string, number>;
  outboxCount: number;
  toast: (msg: string, tone?: string) => void;
  toasts: { id: number; msg: string; tone: string }[];
  navigate: (page: string, params?: Record<string, string>) => void;
  route: { page: string; params: Record<string, string> };
}

const AppCtx = createContext<Ctx>(null as any);
export const useApp = () => useContext(AppCtx);

function parseHash(): { page: string; params: Record<string, string> } {
  const h = (location.hash || "#/overview").slice(2);
  const [page, query] = h.split("?");
  const params: Record<string, string> = {};
  new URLSearchParams(query || "").forEach((v, k) => (params[k] = v));
  return { page: page || "overview", params };
}

export function AppProvider({ children }: { children: any }) {
  const [user, setUser] = useState<User | null>(null);
  const [astronautId, setAstronautIdState] = useState<string | null>(null);
  const [crew, setCrew] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);
  const [serverReachable, setServerReachable] = useState(true);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [version, setVersion] = useState<Record<string, number>>({});
  const [outboxCount, setOutboxCount] = useState(outbox.list().length);
  const [toasts, setToasts] = useState<{ id: number; msg: string; tone: string }[]>([]);
  const [route, setRoute] = useState(parseHash());
  const wsRef = useRef<WebSocket | null>(null);

  const toast = useCallback((msg: string, tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, msg, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const navigate = useCallback((page: string, params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    location.hash = `#/${page}${q ? "?" + q : ""}`;
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => { auth.set(null); setUser(null); });
    if (auth.token) get<User>("/auth/me").then(setUser).catch(() => auth.set(null));
    const onOutbox = () => setOutboxCount(outbox.list().length);
    window.addEventListener("astra-outbox", onOutbox);
    return () => window.removeEventListener("astra-outbox", onOutbox);
  }, []);

  useEffect(() => {
    if (!user) return;
    get<any[]>("/astronauts").then((rows) => {
      setCrew(rows);
      let saved: string | null = null;
      try { saved = sessionStorage.getItem("astra.astronaut"); } catch { /* ignore */ }
      const viewable = rows.filter((r) => r.can_view_health);
      const pick = user.astronaut_id && user.role === "astronaut" ? user.astronaut_id
        : (saved && viewable.find((r) => r.id === saved) ? saved : viewable.find((r) => r.id === "AST-001")?.id || viewable[0]?.id || null);
      setAstronautIdState(pick);
    }).catch(() => {});
  }, [user]);

  const setAstronautId = useCallback((a: string) => {
    setAstronautIdState(a);
    try { sessionStorage.setItem("astra.astronaut", a); } catch { /* ignore */ }
  }, []);

  // ------------------------------------------------ WebSocket with reconnect
  useEffect(() => {
    if (!user || !auth.token) return;
    let stop = false;
    let retry = 0;
    let timer: any;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(auth.token || "")}`);
      wsRef.current = ws;
      ws.onopen = () => {
        retry = 0;
        setConnected(true);
        setServerReachable(true);
        flushOutbox().then((n) => { if (n) toast(`${n} saved entr${n === 1 ? "y was" : "ies were"} sent from the offline outbox`, "ok"); });
        setVersion((v) => ({ ...v, reconnect: (v.reconnect || 0) + 1 }));
      };
      ws.onmessage = (m) => {
        let ev: LiveEvent;
        try { ev = JSON.parse(m.data); } catch { return; }
        if (ev.type === "hello" || ev.type === "pong") return;
        setEvents((e) => [ev, ...e].slice(0, 200));
        setVersion((v) => ({ ...v, [ev.type]: (v[ev.type] || 0) + 1, any: (v.any || 0) + 1 }));
        if (ev.type === "alert.created" && ev.payload?.severity === "URGENT") toast(`Urgent: ${ev.payload.title || "open the Medical Response Center"}`, "urgent");
        if (ev.type === "environment.warning") toast(`Environment: ${ev.payload.description || ev.payload.event_type}`, "attn");
        if (ev.type === "notification") toast(ev.payload.title || "Medical personnel notified", "review");
      };
      ws.onclose = () => {
        setConnected(false);
        if (stop) return;
        retry = Math.min(retry + 1, 6);
        timer = setTimeout(connect, 500 * 2 ** retry);
        get("/health").then(() => setServerReachable(true)).catch(() => setServerReachable(false));
      };
    };
    connect();
    const ping = setInterval(() => { try { wsRef.current?.readyState === 1 && wsRef.current.send("ping"); } catch { /* ignore */ } }, 25000);
    return () => { stop = true; clearTimeout(timer); clearInterval(ping); wsRef.current?.close(); };
  }, [user, toast]);

  return (
    <AppCtx.Provider value={{ user, setUser, astronautId, setAstronautId, crew, connected, serverReachable, events, version,
      outboxCount, toast, toasts, navigate, route }}>
      {children}
    </AppCtx.Provider>
  );
}

/** Fetch data and refetch when any of the given live event types arrive (debounced). */
export function useData<T = any>(path: string | null, refreshOn: string[] = [], deps: any[] = []) {
  const { version, connected } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(false);
  const [nonce, setNonce] = useState(0);
  const key = refreshOn.map((t) => version[t] || 0).join(",") + "|" + (version.reconnect || 0);
  const [debouncedKey, setDebouncedKey] = useState(key);
  useEffect(() => { const t = setTimeout(() => setDebouncedKey(key), 700); return () => clearTimeout(t); }, [key]);
  useEffect(() => {
    if (!path) { setData(null); return; }
    let alive = true;
    setLoading(true);
    get<T>(path).then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(e); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [path, debouncedKey, nonce, ...deps]);
  // Fallback when the real-time channel is unavailable: poll live views every 10 s.
  useEffect(() => {
    if (connected || !path || refreshOn.length === 0) return;
    const t = setInterval(() => setNonce((n) => n + 1), 10000);
    return () => clearInterval(t);
  }, [connected, path, refreshOn.length]);
  return { data, error, loading, reload: () => setNonce((n) => n + 1), setData };
}

export const HEALTH_EVENTS = ["observations.created", "assessment.created", "alert.created", "alert.updated", "alert.acknowledged",
  "alert.resolved", "medical_event.created", "medical_event.updated", "simulator.reset", "baseline.updated"];
