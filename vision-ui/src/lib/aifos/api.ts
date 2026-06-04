export const API_BASE =
  (import.meta.env.VITE_AIFOS_API as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:8000";

export const WS_URL = API_BASE.replace(/^http/, "ws") + "/api/ws";

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const fmt = {
  n: (v: number | null | undefined, d = 2) =>
    v == null || !Number.isFinite(v) ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }),
  pct: (v: number | null | undefined, d = 2) =>
    v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`,
  usd: (v: number | null | undefined, d = 2) =>
    v == null || !Number.isFinite(v) ? "—" : `$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d })}`.replace("$", v < 0 ? "-$" : "$"),
  compact: (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? "—" : Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(v),
  time: (ts: number | string | undefined) => {
    if (!ts) return "—";
    const d = typeof ts === "number" ? new Date(ts * (ts < 1e12 ? 1000 : 1)) : new Date(ts);
    return d.toLocaleTimeString();
  },
};
