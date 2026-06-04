import type { Config, Decision, Fundamentals, Portfolio, RiskSnapshot, TradeRow } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_AIFOS_API || "http://localhost:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  config: () => j<Config>("/api/config"),
  universe: () => j<{ universe: { symbol: string; asset_class: string }[] }>("/api/market/universe"),
  candles: (symbol: string, interval = "1d", lookback = 240) =>
    j<{ symbol: string; interval: string; source: string; candles: any[] }>(
      `/api/market/candles?symbol=${encodeURIComponent(symbol)}&interval=${interval}&lookback=${lookback}`
    ),
  analyze: (symbol: string, interval = "1d") =>
    j<Decision>("/api/analyze", { method: "POST", body: JSON.stringify({ symbol, interval }) }),
  backtest: (symbol: string, strategy: string, interval = "1d") =>
    j<any>("/api/backtest", { method: "POST", body: JSON.stringify({ symbol, strategy, interval }) }),
  fundamentals: (symbol: string) =>
    j<Fundamentals>(`/api/research/fundamentals?symbol=${encodeURIComponent(symbol)}`),
  analytics: (symbol: string) =>
    j<{ live: Record<string, number | string>; strategies: any[] }>(
      `/api/analytics?symbol=${encodeURIComponent(symbol)}`
    ),
  correlation: () => j<{ symbols: string[]; matrix: number[][] }>("/api/analytics/correlation"),
  heatmap: () => j<{ tiles: any[] }>("/api/market/heatmap"),
  alertsStatus: () => j<{ enabled: boolean; channels: string[] }>("/api/alerts/status"),
  alertsTest: () => j<{ sent: string[]; channels: string[] }>("/api/alerts/test", { method: "POST" }),
  rlStatus: () => j<any>("/api/rl/status"),
  rlTrain: (symbol: string) =>
    j<any>("/api/rl/train", { method: "POST", body: JSON.stringify({ symbol }) }),
  learnVideo: (url: string) =>
    j<any>("/api/learn/video", { method: "POST", body: JSON.stringify({ url }) }),
  executionStatus: () => j<any>("/api/execution/status"),
  news: (symbol: string) => j<any>(`/api/news?symbol=${encodeURIComponent(symbol)}`),
  newsTicker: () => j<{ items: any[] }>("/api/news/ticker"),
  newsSimilar: (symbol: string, title: string) =>
    j<any>(`/api/news/similar?symbol=${encodeURIComponent(symbol)}&title=${encodeURIComponent(title)}`),
  assistantAsk: (question: string) =>
    j<{ answer: string; engine: string; symbol?: string }>("/api/assistant/ask", {
      method: "POST", body: JSON.stringify({ question }),
    }),
  assistantInfo: () => j<{ name: string; engine: string }>("/api/assistant/info"),
  tick: (symbol: string, execute = true, interval = "1d") =>
    j<{ decision: Decision; fill: any }>("/api/tick", {
      method: "POST",
      body: JSON.stringify({ symbol, execute, interval }),
    }),
  cycle: (execute = true) =>
    j<{ results: any[] }>("/api/cycle", { method: "POST", body: JSON.stringify({ execute }) }),
  portfolio: () => j<Portfolio>("/api/portfolio"),
  risk: () => j<RiskSnapshot>("/api/risk"),
  agents: () => j<{ agents: { name: string; weight: number; role: string }[] }>("/api/agents"),
  decisions: (limit = 30) => j<{ decisions: Decision[] }>(`/api/decisions?limit=${limit}`),
  trades: (limit = 50) => j<{ trades: TradeRow[] }>(`/api/trades?limit=${limit}`),
  journal: () => j<{ lessons: string[]; entries: any[] }>("/api/journal"),
  kill: (reason = "manual kill switch") =>
    j("/api/control/kill?reason=" + encodeURIComponent(reason), { method: "POST" }),
  resume: () => j("/api/control/resume", { method: "POST" }),
  autonomous: (on: boolean) =>
    j("/api/control/autonomous", { method: "POST", body: JSON.stringify({ on }) }),
};

export const WS_URL = API_BASE.replace(/^http/, "ws") + "/api/ws";
