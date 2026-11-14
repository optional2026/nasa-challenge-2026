// HTTP client for the ASTRA backend. Session token lives in sessionStorage
// (issued by the server at login; no secrets are compiled into the frontend).
// Manual entries that fail because the onboard server is unreachable are kept in
// a local outbox and re-sent with the same client_submission_id (no duplicates).

export class ApiError extends Error {
  status: number;
  code: string;
  details: any;
  constructor(status: number, code: string, message: string, details?: any) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const TOKEN_KEY = "astra.token";
const OUTBOX_KEY = "astra.outbox";

function safeGet(store: Storage, key: string): string | null {
  try { return store.getItem(key); } catch { return null; }
}
function safeSet(store: Storage, key: string, value: string | null) {
  try { value === null ? store.removeItem(key) : store.setItem(key, value); } catch { /* storage unavailable */ }
}

export const auth = {
  get token(): string | null { return safeGet(sessionStorage, TOKEN_KEY); },
  set(token: string | null) { safeSet(sessionStorage, TOKEN_KEY, token); },
};

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

export async function api<T = any>(method: string, path: string, body?: any): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const t = auth.token;
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(`/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  let data: any = null;
  const text = await res.text();
  if (text) { try { data = JSON.parse(text); } catch { data = text; } }
  if (!res.ok) {
    const e = data?.error || {};
    if (res.status === 401 && path !== "/auth/login") onUnauthorized();
    throw new ApiError(res.status, e.code || "http_error", e.message || `Request failed (${res.status})`, e.details);
  }
  return data as T;
}

export const get = <T = any>(path: string) => api<T>("GET", path);
export const post = <T = any>(path: string, body: any = {}) => api<T>("POST", path, body);

export function qs(params: Record<string, any>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function newClientId(prefix = "C"): string {
  const rnd = (globalThis.crypto && "randomUUID" in globalThis.crypto)
    ? globalThis.crypto.randomUUID().replace(/-/g, "").slice(0, 16)
    : Math.random().toString(36).slice(2, 18);
  return `${prefix}-${Date.now().toString(36)}-${rnd}`;
}

// ---------------------------------------------------------------- offline outbox
export interface OutboxItem { id: string; path: string; body: any; created: string; lastError?: string }

export const outbox = {
  list(): OutboxItem[] {
    try { return JSON.parse(safeGet(localStorage, OUTBOX_KEY) || "[]"); } catch { return []; }
  },
  save(items: OutboxItem[]) { safeSet(localStorage, OUTBOX_KEY, JSON.stringify(items)); },
  add(item: OutboxItem) { this.save([...this.list().filter((i) => i.id !== item.id), item]); },
  remove(id: string) { this.save(this.list().filter((i) => i.id !== id)); },
};

/** POST a record; if the onboard server cannot be reached, keep it in the outbox. */
export async function submitWithOutbox(path: string, body: any): Promise<{ queued: boolean; result?: any }> {
  const id = body.client_submission_id || newClientId("SUB");
  const payload = { ...body, client_submission_id: id };
  try {
    const result = await post(path, payload);
    return { queued: false, result };
  } catch (e: any) {
    if (e instanceof ApiError) throw e; // validation errors are shown to the user, not queued
    outbox.add({ id, path, body: payload, created: new Date().toISOString(), lastError: String(e?.message || e) });
    window.dispatchEvent(new Event("astra-outbox"));
    return { queued: true };
  }
}

export async function flushOutbox(): Promise<number> {
  let sent = 0;
  for (const item of outbox.list()) {
    try {
      await post(item.path, item.body);
      outbox.remove(item.id);
      sent++;
    } catch (e: any) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 401) {
        outbox.remove(item.id); // server rejected it permanently; keep the reason in the console
        console.warn("outbox item rejected", item, e);
      } else break;
    }
  }
  window.dispatchEvent(new Event("astra-outbox"));
  return sent;
}
