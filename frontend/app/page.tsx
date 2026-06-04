"use client";
import { useCallback, useEffect, useState } from "react";

import { ActivityFeed, TradeLog } from "@/components/ActivityFeed";
import { AgentPanel } from "@/components/AgentPanel";
import { AnalyticsPanel } from "@/components/AnalyticsPanel";
import { AssistantDock } from "@/components/AssistantDock";
import { Chart } from "@/components/Chart";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { ExecutionPanel } from "@/components/ExecutionPanel";
import { Header } from "@/components/Header";
import { LabPanel } from "@/components/LabPanel";
import { NewsPanel } from "@/components/NewsPanel";
import { NewsTicker } from "@/components/NewsTicker";
import { PortfolioOverview } from "@/components/PortfolioOverview";
import { ResearchPanel } from "@/components/ResearchPanel";
import { RiskDashboard } from "@/components/RiskDashboard";
import { AllocationDonut, CorrelationMatrix, Heatmap } from "@/components/Visuals";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { Candle, Config, Decision, Fundamentals, TradeRow } from "@/lib/types";
import { useAifosSocket } from "@/lib/ws";

export default function Dashboard() {
  const ws = useAifosSocket();
  const [config, setConfig] = useState<Config>();
  const [universe, setUniverse] = useState<{ symbol: string; asset_class: string }[]>([]);
  const [symbol, setSymbol] = useState("");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [source, setSource] = useState("");
  const [decision, setDecision] = useState<Decision>();
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [backtest, setBacktest] = useState<any>();
  const [fundamentals, setFundamentals] = useState<Fundamentals>();
  const [analytics, setAnalytics] = useState<any>();
  const [heat, setHeat] = useState<any[]>([]);
  const [corr, setCorr] = useState<any>();
  const [news, setNews] = useState<any>();
  const [ticker, setTicker] = useState<any[]>([]);
  const [exec, setExec] = useState<any>();
  const [busy, setBusy] = useState(false);

  const assetClass = universe.find((u) => u.symbol === symbol)?.asset_class ?? "";

  const loadSymbol = useCallback(async (sym: string) => {
    if (!sym) return;
    setBusy(true);
    setBacktest(undefined);
    setFundamentals(undefined);
    setAnalytics(undefined);
    setNews(undefined);
    try {
      const [c, d] = await Promise.all([api.candles(sym), api.analyze(sym)]);
      setCandles(c.candles);
      setSource(c.source);
      setDecision(d);
      api.trades().then((t) => setTrades(t.trades)).catch(() => {});
      api.fundamentals(sym).then(setFundamentals).catch(() => {});
      api.analytics(sym).then(setAnalytics).catch(() => {});
      api.news(sym).then(setNews).catch(() => {});
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    api.config().then((cfg) => {
      setConfig(cfg);
      setSymbol(cfg.default_symbol);
      loadSymbol(cfg.default_symbol);
    });
    api.universe().then((u) => setUniverse(u.universe));
    api.trades().then((t) => setTrades(t.trades)).catch(() => {});
    api.heatmap().then((r) => setHeat(r.tiles)).catch(() => {});
    api.correlation().then(setCorr).catch(() => {});
    api.newsTicker().then((r) => setTicker(r.items)).catch(() => {});
    api.executionStatus().then(setExec).catch(() => {});
  }, [loadSymbol]);

  // refresh trade log whenever a fill streams in
  useEffect(() => {
    if (ws.events[0]?.kind === "fill") api.trades().then((t) => setTrades(t.trades)).catch(() => {});
  }, [ws.events]);

  const onSelect = (sym: string) => { setSymbol(sym); loadSymbol(sym); };

  const runCycle = async () => {
    setBusy(true);
    try { await api.cycle(true); await api.trades().then((t) => setTrades(t.trades)); }
    finally { setBusy(false); }
  };

  const runBacktest = async () => {
    if (!symbol) return;
    setBusy(true);
    try { setBacktest(await api.backtest(symbol, "momentum")); }
    finally { setBusy(false); }
  };

  const risk = ws.risk;
  const portfolio = ws.portfolio;
  const lastPx = candles.length ? candles[candles.length - 1].close : 0;

  return (
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col">
      <Header
        config={config}
        risk={risk}
        connected={ws.connected}
        onKill={() => api.kill().catch(() => {})}
        onResume={() => api.resume().catch(() => {})}
        onToggleAuto={() => api.autonomous(!risk?.autonomous).catch(() => {})}
      />

      {/* control bar */}
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        <select
          value={symbol}
          onChange={(e) => onSelect(e.target.value)}
          className="num rounded-lg border border-white/10 bg-ink-800 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-accent/40"
        >
          {universe.map((u) => (
            <option key={u.symbol} value={u.symbol} className="bg-ink-800">
              {u.symbol} · {u.asset_class}
            </option>
          ))}
        </select>

        <div className="flex items-baseline gap-2">
          <span className="num text-lg font-semibold text-zinc-100">{lastPx ? num(lastPx) : "—"}</span>
          <span className="chip border-white/10 text-zinc-400">{assetClass || "—"}</span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button className="btn btn-accent" disabled={busy} onClick={() => loadSymbol(symbol)}>
            {busy ? "Analyzing…" : "↻ Analyze"}
          </button>
          <button className="btn" disabled={busy} onClick={runBacktest}>Backtest</button>
          <button className="btn" disabled={busy} onClick={runCycle}>Run Cycle (paper)</button>
        </div>
      </div>

      <NewsTicker items={ticker} />

      {backtest && (
        <div className="mx-5 mb-1 flex flex-wrap items-center gap-4 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-2 text-xs">
          <span className="label">Backtest · momentum</span>
          <Metric k="return" v={`${(backtest.metrics.total_return * 100).toFixed(1)}%`} />
          <Metric k="sharpe" v={num(backtest.metrics.sharpe, 2)} />
          <Metric k="max DD" v={`${(backtest.metrics.max_drawdown * 100).toFixed(1)}%`} />
          <Metric k="win rate" v={`${(backtest.metrics.win_rate * 100).toFixed(0)}%`} />
          <Metric k="trades" v={`${backtest.metrics.num_trades}`} />
          <Metric k="OOS sharpe" v={num(backtest.walk_forward?.oos?.sharpe ?? 0, 2)} />
        </div>
      )}

      <main className="flex flex-col gap-3 p-5 pt-2">
        {/* top: chart + meter (left) | committee (right) */}
        <div className="flex flex-col gap-3 xl:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-3">
            <div className="panel h-[400px] p-2">
              <Chart candles={candles} source={source} />
            </div>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <ConfidenceMeter decision={decision} threshold={config?.risk_limits?.confidence_threshold ?? 0.62} />
              <div className="panel-pad flex flex-col gap-2">
                <span className="label">Decision Rationale</span>
                <p className="text-sm leading-relaxed text-zinc-300">
                  {decision?.reasoning ?? "Run analysis to see the desk's reasoning."}
                </p>
                <div className="mt-auto flex flex-wrap gap-1.5 pt-2 text-[11px] text-zinc-500">
                  <span className="chip border-white/10">side: {decision?.side ?? "—"}</span>
                  <span className="chip border-white/10">data: {source || "—"}</span>
                  {decision?.executed && <span className="chip border-long/30 text-long-soft">executed</span>}
                </div>
              </div>
            </div>
            <ResearchPanel f={fundamentals} symbol={symbol} />
          </div>
          <div className="xl:w-[360px]">
            <AgentPanel decision={decision} />
          </div>
        </div>

        {/* markets: heatmap · correlation · allocation */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <Heatmap tiles={heat} />
          <CorrelationMatrix data={corr} />
          <AllocationDonut pf={portfolio} />
        </div>

        {/* news intelligence · execution engine */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="lg:col-span-2"><NewsPanel data={news} symbol={symbol} /></div>
          <ExecutionPanel data={exec} />
        </div>

        {/* bottom: portfolio · risk · activity · trades */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <PortfolioOverview pf={portfolio} ccy={config?.base_currency ?? "INR"} />
          <RiskDashboard risk={risk} />
          <div className="h-[320px]"><ActivityFeed events={ws.events} /></div>
          <div className="h-[320px]"><TradeLog trades={trades} /></div>
        </div>

        <LabPanel symbol={symbol} />

        <AnalyticsPanel data={analytics} ccy={config?.base_currency ?? "INR"} />

        <footer className="pt-2 text-center text-[11px] text-zinc-600">
          AIFOS reasons in probabilities and does not guarantee profit. Paper-first; live execution is gated.
        </footer>
      </main>
      <AssistantDock events={ws.events} />
    </div>
  );
}

function Metric({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-zinc-500">{k}</span>
      <span className="num text-zinc-200">{v}</span>
    </div>
  );
}
