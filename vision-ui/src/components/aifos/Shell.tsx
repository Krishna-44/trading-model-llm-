import { useEffect, useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { useWS } from "@/lib/aifos/ws";
import { api, fmt } from "@/lib/aifos/api";
import { Chip, Dot } from "./Panel";
import { Activity, Power, Zap, Brain, Bot } from "lucide-react";
import { motion } from "framer-motion";

export function Header({ symbol }: { symbol: string }) {
  const { connected, risk: wsRisk } = useWS();
  const { data: config } = useApi<any>("/api/config", { pollMs: 15000 });
  const { data: risk } = useApi<any>("/api/risk", { pollMs: 10000 });
  const r = wsRisk || risk;
  const mode = config?.mode || config?.broker?.mode || "paper";
  const live = mode === "live";
  const llmOn = config?.llm?.enabled ?? config?.llm_enabled ?? false;
  const autonomous = r?.autonomous ?? config?.autonomous ?? false;
  const killed = r?.kill_switch_active ?? false;

  const [busy, setBusy] = useState(false);
  const act = async (path: string, body?: any) => {
    setBusy(true);
    try { await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }); } catch {} finally { setBusy(false); }
  };

  return (
    <header className="sticky top-0 z-40 backdrop-blur-xl bg-background/70 border-b border-border">
      <div className="px-4 md:px-6 py-3 flex flex-wrap items-center gap-3">
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[color:var(--cyan)] to-[color:var(--indigo)] grid place-items-center shadow-lg shadow-[color:var(--indigo)]/30">
            <Brain className="w-5 h-5 text-background" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold tracking-tight leading-tight">AIFOS <span className="text-muted-foreground font-normal">/ Financial Operating System</span></div>
            <div className="text-[10px] text-muted-foreground leading-tight">Protect capital first · default action is HOLD · symbol <span className="num text-[color:var(--cyan)]">{symbol}</span></div>
          </div>
        </motion.div>

        <div className="ml-auto flex items-center gap-2 flex-wrap">
          <Chip tone={connected ? "up" : "down"}><Dot on={connected} color={connected ? "emerald" : "rose"} /> {connected ? "streaming" : "offline"}</Chip>
          <Chip tone={live ? "down" : "cyan"}><Zap className="w-3 h-3" /> {live ? "LIVE" : "PAPER"}</Chip>
          <Chip tone={llmOn ? "indigo" : "default"}><Bot className="w-3 h-3" /> LLM {llmOn ? "on" : "off"}</Chip>
          <button
            disabled={busy}
            onClick={() => act("/api/control/autonomous", { enabled: !autonomous })}
            className={`chip transition ${autonomous ? "text-[color:var(--up)] border-[color:var(--up)]/40 bg-[color:var(--up)]/10" : "text-muted-foreground hover:text-foreground"}`}
          >
            <Activity className="w-3 h-3" /> Autonomous {autonomous ? "ON" : "OFF"}
          </button>
          {killed ? (
            <button disabled={busy} onClick={() => act("/api/control/resume")} className="chip border-emerald-400/40 bg-emerald-400/10 text-emerald-300 hover:bg-emerald-400/20 transition">
              <Power className="w-3 h-3" /> Resume
            </button>
          ) : (
            <button disabled={busy} onClick={() => act("/api/control/kill")} className="chip border-rose-500/50 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20 transition">
              <Power className="w-3 h-3" /> Kill Switch
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

export function ControlBar({ symbol, setSymbol, interval, setInterval, onAnalyze, onBacktest, onCycle, analyzing }: {
  symbol: string; setSymbol: (s: string) => void;
  interval: string; setInterval: (s: string) => void;
  onAnalyze: () => void; onBacktest: () => void; onCycle: () => void; analyzing?: boolean;
}) {
  const { data: universe } = useApi<{ universe?: Array<{ symbol: string; asset_class: string }>; symbols?: any[] }>("/api/market/universe");
  const list = (universe as any)?.universe || (universe as any)?.symbols || [];
  const current = list.find?.((x: any) => x.symbol === symbol);
  const { data: heat } = useApi<any>("/api/market/heatmap", { pollMs: 5000 });
  const tile = heat?.tiles?.find?.((t: any) => t.symbol === symbol);

  return (
    <div className="px-4 md:px-6 py-3 flex flex-wrap items-center gap-3 border-b border-border bg-background/40 backdrop-blur-md">
      <select
        value={symbol} onChange={(e) => setSymbol(e.target.value)}
        className="num bg-secondary/60 border border-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[color:var(--cyan)]/50"
      >
        {list.length === 0 && <option>{symbol}</option>}
        {list.map((s: any) => <option key={s.symbol} value={s.symbol}>{s.symbol} · {s.asset_class}</option>)}
      </select>
      <select value={interval} onChange={(e) => setInterval(e.target.value)} className="num bg-secondary/60 border border-border rounded-lg px-2 py-1.5 text-xs">
        {["1m","5m","15m","1h","1d","1wk"].map((i) => <option key={i} value={i}>{i}</option>)}
      </select>
      {tile && (
        <div className="flex items-center gap-2">
          <span className="num text-lg font-semibold">{fmt.n(tile.price)}</span>
          <Chip tone={(tile.change_pct ?? 0) >= 0 ? "up" : "down"}>{fmt.pct(tile.change_pct)}</Chip>
          <Chip tone="indigo">{current?.asset_class || tile.asset_class}</Chip>
        </div>
      )}
      <div className="ml-auto flex items-center gap-2">
        <button onClick={onAnalyze} disabled={analyzing} className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-[color:var(--cyan)] to-[color:var(--indigo)] text-background hover:opacity-90 transition disabled:opacity-60">
          {analyzing ? "Analyzing…" : "Analyze"}
        </button>
        <button onClick={onBacktest} className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-border hover:bg-secondary/60 transition">Backtest</button>
        <button onClick={onCycle} className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-border hover:bg-secondary/60 transition">Run Cycle (paper)</button>
      </div>
    </div>
  );
}

export function NewsTicker() {
  const { data } = useApi<{ items: Array<{ symbol: string; title: string; sentiment: number; impact_score: number }> }>("/api/news/ticker", { pollMs: 30000 });
  const items = data?.items || [];
  if (!items.length) {
    return <div className="px-6 py-1.5 text-[11px] text-muted-foreground border-b border-border">News stream idle — connect backend for live headlines.</div>;
  }
  const loop = [...items, ...items];
  return (
    <div className="border-b border-border bg-background/30 overflow-hidden">
      <div className="marquee whitespace-nowrap py-1.5 flex gap-8">
        {loop.map((n, i) => (
          <span key={i} className="text-[11px] inline-flex items-center gap-2">
            <span className={`num font-semibold ${n.sentiment > 0.1 ? "text-[color:var(--up)]" : n.sentiment < -0.1 ? "text-[color:var(--down)]" : "text-muted-foreground"}`}>{n.symbol}</span>
            <span className="text-foreground/80">{n.title}</span>
            <span className="text-muted-foreground">· impact {fmt.n(n.impact_score, 1)}</span>
            <span className="text-border">|</span>
          </span>
        ))}
      </div>
    </div>
  );
}
