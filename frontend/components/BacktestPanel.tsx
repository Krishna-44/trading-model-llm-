"use client";
/**
 * BacktestPanel — surfaces a strategy's walk-forward backtest so YOU can vet
 * an edge before flipping the live gate.
 *
 * Shows:
 *   - Equity curve (line)
 *   - Drawdown band (area, red, mirrored beneath the curve)
 *   - Stats card: Sharpe, max DD %, win rate, profit factor, trade count
 *   - Last 20 trades table
 *
 * Expected API shape (GET /api/backtest?symbol=...&strategy=...):
 * {
 *   symbol: "RELIANCE.NS", strategy: "supertrend-2",
 *   equity:    [{ ts: "2025-06-01", value: 100000 }, ...],
 *   drawdown:  [{ ts: "...", value: 0 to -0.18 }, ...],     // negative fractions
 *   stats: {
 *     sharpe: 1.42, max_drawdown_pct: -0.182,
 *     win_rate: 0.58, profit_factor: 1.85, trades: 124,
 *     total_return_pct: 0.34, cagr: 0.21,
 *   },
 *   trades: [{ ts, side, entry, exit, pnl, pct, holding_bars }, ...]
 * }
 */
import { ColorType, createChart } from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

type EquityPoint   = { ts: string; value: number };
type DrawdownPoint = { ts: string; value: number };
type TradeRow      = {
  ts: string; side: "long" | "short"; entry: number; exit: number;
  pnl: number; pct: number; holding_bars: number;
};

export type BacktestResult = {
  symbol: string;
  strategy: string;
  equity:   EquityPoint[];
  drawdown: DrawdownPoint[];
  stats: {
    sharpe: number; max_drawdown_pct: number;
    win_rate: number; profit_factor: number; trades: number;
    total_return_pct: number; cagr: number;
  };
  trades: TradeRow[];
};

export function BacktestPanel({ data, loading, error }: {
  data?: BacktestResult; loading?: boolean; error?: string;
}) {
  const chartRef = useRef<HTMLDivElement>(null);
  const ddRef    = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!data || !chartRef.current || data.equity.length === 0) return;
    const chart = createChart(chartRef.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" },
                textColor: "#a1a1aa",
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11 },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" },
              horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale:       { borderColor: "rgba(255,255,255,0.08)", timeVisible: false },
      crosshair: { mode: 1 },
    });
    const eq = chart.addLineSeries({
      color: "#22d3ee", lineWidth: 2, priceLineVisible: false,
    });
    eq.setData(data.equity.map(p => ({ time: p.ts.slice(0, 10) as any, value: p.value })));
    return () => chart.remove();
  }, [data]);

  useEffect(() => {
    if (!data || !ddRef.current || data.drawdown.length === 0) return;
    const chart = createChart(ddRef.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" },
                textColor: "#a1a1aa",
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11 },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" },
              horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale:       { borderColor: "rgba(255,255,255,0.08)", timeVisible: false },
    });
    const dd = chart.addAreaSeries({
      topColor:    "rgba(244,63,94,0.45)",
      bottomColor: "rgba(244,63,94,0.05)",
      lineColor:   "#f43f5e",
      lineWidth: 1,
    });
    dd.setData(data.drawdown.map(p => ({ time: p.ts.slice(0, 10) as any, value: p.value * 100 })));
    return () => chart.remove();
  }, [data]);

  if (loading) return <div className="text-zinc-400 text-sm p-3">Running walk-forward backtest…</div>;
  if (error)   return <div className="text-rose-400 text-sm p-3">Backtest failed: {error}</div>;
  if (!data)   return <div className="text-zinc-500 text-sm p-3">No backtest yet. Pick a symbol + strategy.</div>;

  return (
    <div className="rounded-xl border border-white/5 bg-zinc-950/40 p-4 space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h3 className="text-sm font-semibold tracking-wider text-zinc-100">
            BACKTEST · <span className="text-cyan-400">{data.symbol}</span> · <span className="text-zinc-400">{data.strategy}</span>
          </h3>
          <p className="text-[10px] uppercase tracking-widest text-zinc-500 mt-0.5">
            Walk-forward · out-of-sample · with slippage + costs
          </p>
        </div>
        <StatsBadge label="Total return" value={`${(data.stats.total_return_pct * 100).toFixed(1)}%`}
                    sign={data.stats.total_return_pct} />
      </header>

      <div className="grid grid-cols-5 gap-2 text-[11px]">
        <Stat label="Sharpe"        value={data.stats.sharpe.toFixed(2)}
              tone={data.stats.sharpe >= 1 ? "good" : data.stats.sharpe >= 0.5 ? "ok" : "bad"} />
        <Stat label="Max DD"        value={`${(data.stats.max_drawdown_pct * 100).toFixed(1)}%`}
              tone={data.stats.max_drawdown_pct > -0.10 ? "good" : data.stats.max_drawdown_pct > -0.20 ? "ok" : "bad"} />
        <Stat label="Win rate"      value={`${(data.stats.win_rate * 100).toFixed(0)}%`}
              tone={data.stats.win_rate >= 0.55 ? "good" : data.stats.win_rate >= 0.45 ? "ok" : "bad"} />
        <Stat label="Profit factor" value={data.stats.profit_factor.toFixed(2)}
              tone={data.stats.profit_factor >= 1.5 ? "good" : data.stats.profit_factor >= 1.1 ? "ok" : "bad"} />
        <Stat label="Trades"        value={data.stats.trades.toString()} tone="info" />
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Equity curve</p>
        <div ref={chartRef} className="h-44 w-full" />
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Drawdown (%)</p>
        <div ref={ddRef} className="h-28 w-full" />
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Last 20 trades</p>
        <div className="max-h-48 overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="text-zinc-500 text-left sticky top-0 bg-zinc-950/80 backdrop-blur">
              <tr>
                <th className="py-1 pr-2">Date</th>
                <th className="py-1 pr-2">Side</th>
                <th className="py-1 pr-2 text-right">Entry</th>
                <th className="py-1 pr-2 text-right">Exit</th>
                <th className="py-1 pr-2 text-right">P&L</th>
                <th className="py-1 pr-2 text-right">%</th>
                <th className="py-1 text-right">Bars</th>
              </tr>
            </thead>
            <tbody>
              {data.trades.slice(-20).reverse().map((t, i) => (
                <tr key={i} className="border-t border-white/5 hover:bg-white/[0.02]">
                  <td className="py-1 pr-2 text-zinc-300">{t.ts.slice(0, 10)}</td>
                  <td className={"py-1 pr-2 " + (t.side === "long" ? "text-emerald-400" : "text-rose-400")}>
                    {t.side.toUpperCase()}
                  </td>
                  <td className="py-1 pr-2 text-right text-zinc-300">{t.entry.toFixed(2)}</td>
                  <td className="py-1 pr-2 text-right text-zinc-300">{t.exit.toFixed(2)}</td>
                  <td className={"py-1 pr-2 text-right " + (t.pnl >= 0 ? "text-emerald-400" : "text-rose-400")}>
                    {t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(2)}
                  </td>
                  <td className={"py-1 pr-2 text-right " + (t.pct >= 0 ? "text-emerald-400" : "text-rose-400")}>
                    {(t.pct * 100).toFixed(1)}%
                  </td>
                  <td className="py-1 text-right text-zinc-500">{t.holding_bars}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: "good" | "ok" | "bad" | "info" }) {
  const color =
    tone === "good" ? "text-emerald-400 border-emerald-400/30 bg-emerald-400/5"
    : tone === "ok"   ? "text-amber-300 border-amber-300/30 bg-amber-300/5"
    : tone === "bad"  ? "text-rose-400 border-rose-400/30 bg-rose-400/5"
    : "text-cyan-300 border-cyan-300/30 bg-cyan-300/5";
  return (
    <div className={`rounded-lg border px-2 py-1.5 ${color}`}>
      <div className="text-[9px] uppercase tracking-widest opacity-70">{label}</div>
      <div className="text-sm font-mono mt-0.5">{value}</div>
    </div>
  );
}

function StatsBadge({ label, value, sign }: { label: string; value: string; sign: number }) {
  const color = sign >= 0 ? "text-emerald-400 border-emerald-400/30 bg-emerald-400/5"
                          : "text-rose-400 border-rose-400/30 bg-rose-400/5";
  return (
    <div className={`rounded-md border px-3 py-1 ${color}`}>
      <div className="text-[9px] uppercase tracking-widest opacity-70">{label}</div>
      <div className="text-lg font-mono">{value}</div>
    </div>
  );
}

/**
 * Convenience hook — fetches /api/backtest and feeds the panel.
 *
 *   const { data, loading, error } = useBacktest("RELIANCE.NS", "supertrend-2");
 *   return <BacktestPanel data={data} loading={loading} error={error} />;
 */
export function useBacktest(symbol?: string, strategy?: string,
                            interval: string = "1d",
                            params: Record<string, unknown> = {}): {
  data?: BacktestResult; loading: boolean; error?: string;
} {
  const [data, setData] = useState<BacktestResult | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  // Stringify params for stable effect deps
  const paramsKey = JSON.stringify(params);

  useEffect(() => {
    if (!symbol || !strategy) return;
    const api = process.env.NEXT_PUBLIC_AIFOS_API || "http://localhost:8000";
    const ctrl = new AbortController();
    setLoading(true); setError(undefined);
    fetch(`${api}/api/backtest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, strategy, interval, params: JSON.parse(paramsKey) }),
      signal: ctrl.signal,
    })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((raw: Record<string, unknown>) => {
        // Normalise the BacktestEngine payload to what the panel expects.
        // The backend returns { trades, equity_curve, walk_forward, monte_carlo, stats... }
        // We unify into the BacktestResult shape used by the UI.
        const eq = (raw.equity_curve as Array<{ts?: string; date?: string; value: number}> | undefined) || [];
        const tr = (raw.trades as Array<Record<string, unknown>> | undefined) || [];
        const eqPoints: EquityPoint[] = eq.map(p => ({ ts: String(p.ts ?? p.date ?? ""), value: Number(p.value) }));
        // Derive drawdown from equity if backend didn't supply it.
        let peak = 0; const ddPoints: DrawdownPoint[] = [];
        for (const p of eqPoints) {
          peak = Math.max(peak, p.value);
          ddPoints.push({ ts: p.ts, value: peak > 0 ? p.value / peak - 1 : 0 });
        }
        const trades: TradeRow[] = tr.map(t => ({
          ts: String(t.exit_ts ?? t.ts ?? ""),
          side: ((t.side as string) || "long").toLowerCase() === "short" ? "short" : "long",
          entry: Number(t.entry_price ?? t.entry ?? 0),
          exit:  Number(t.exit_price  ?? t.exit  ?? 0),
          pnl:   Number(t.pnl ?? 0),
          pct:   Number(t.pct ?? t.pct_return ?? 0),
          holding_bars: Number(t.holding_bars ?? t.bars ?? 0),
        }));
        const stats = (raw.stats as Record<string, number> | undefined) || {};
        const result: BacktestResult = {
          symbol: symbol!, strategy: strategy!,
          equity: eqPoints, drawdown: ddPoints, trades,
          stats: {
            sharpe:           Number(stats.sharpe ?? 0),
            max_drawdown_pct: Number(stats.max_drawdown_pct ?? Math.min(...ddPoints.map(d => d.value), 0)),
            win_rate:         Number(stats.win_rate ?? 0),
            profit_factor:    Number(stats.profit_factor ?? 0),
            trades:           Number(stats.trades ?? trades.length),
            total_return_pct: Number(stats.total_return_pct ?? (eqPoints.length > 1 ? eqPoints[eqPoints.length - 1].value / eqPoints[0].value - 1 : 0)),
            cagr:             Number(stats.cagr ?? 0),
          },
        };
        setData(result);
      })
      .catch(e => { if ((e as Error).name !== "AbortError") setError(String(e)); })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [symbol, strategy, interval, paramsKey]);

  return useMemo(() => ({ data, loading, error }), [data, loading, error]);
}

export default BacktestPanel;
