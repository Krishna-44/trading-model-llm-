import { useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { apiFrom, PAPER_API_BASE } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const pct = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

/** Robustness · Monte Carlo enforcement — reads the forward instance (:8001).
 *  Shows which strategy edges survive resampling, the correlation limiter, and the
 *  adaptive confidence bar; the enforce button auto-demotes fragile strategies. */
export function Robustness({ symbol }: { symbol: string }) {
  const { data: mkt, refetch } = useApi<any>(`/api/strategies?symbol=${encodeURIComponent(symbol)}`, { deps: [symbol], pollMs: 60000, base: PAPER_API_BASE });
  const { data: risk } = useApi<any>("/api/risk", { pollMs: 30000, base: PAPER_API_BASE });
  const [enforcing, setEnforcing] = useState(false);
  const [result, setResult] = useState<any>(null);

  if (!mkt) return <Panel title="Robustness"><Empty>evaluating strategy robustness…</Empty></Panel>;
  const strats: any[] = (mkt.strategies || []).filter((s: any) => s.monte_carlo);
  const cl = risk?.correlation_limiter;
  const baseBar = risk?.limits?.confidence_threshold;

  const enforce = async () => {
    setEnforcing(true);
    try {
      const r = await apiFrom<any>(PAPER_API_BASE, "/api/strategies/enforce", { method: "POST", body: JSON.stringify({ apply: true }) });
      setResult(r); refetch();
    } catch { setResult({ error: true }); } finally { setEnforcing(false); }
  };

  return (
    <Panel
      title="Robustness · Monte Carlo enforcement"
      subtitle="forward instance · which edges survive resampling — fragile ones get demoted"
      right={
        <button onClick={enforce} disabled={enforcing}
          className="chip border-[color:var(--cyan)]/40 text-[color:var(--cyan)] bg-[color:var(--cyan)]/10 disabled:opacity-40 px-3">
          {enforcing ? "enforcing…" : "⚖ enforce"}
        </button>
      }
    >
      <div className="flex flex-wrap gap-2 mb-3">
        {cl && <Chip tone="indigo">corr limiter · ρ≥{cl.threshold} · max {cl.max_correlated_positions} aligned</Chip>}
        {risk?.limits?.confidence_threshold_adaptive && <Chip tone="cyan">adaptive confidence bar · base {baseBar}</Chip>}
        {risk?.kill_switch_active && <Chip tone="down">kill switch active</Chip>}
      </div>

      {strats.length === 0 ? (
        <Empty>no backtested strategies to score</Empty>
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="bg-secondary/30 text-muted-foreground text-[9px] uppercase tracking-wide">
                <th className="text-left font-medium px-2 py-1">Strategy</th>
                <th className="text-left font-medium px-2 py-1">Robustness</th>
                <th className="text-right font-medium px-2 py-1">Backtest</th>
                <th className="text-right font-medium px-2 py-1">w/o best</th>
              </tr>
            </thead>
            <tbody>
              {strats.map((s: any) => {
                const mc = s.monte_carlo || {};
                return (
                  <tr key={s.name} className="border-t border-border/50 align-top">
                    <td className="px-2 py-1">
                      <span className="font-medium">{s.label || s.name}</span>
                      {!s.enabled && <span className="text-[color:var(--down)] text-[10px]"> · disabled</span>}
                    </td>
                    <td className="px-2 py-1">
                      <Chip tone={mc.reliable ? "up" : "warn"}>{mc.reliable ? "reliable" : "fragile"}</Chip>
                      <span className="text-muted-foreground text-[10px] block mt-0.5 max-w-[260px] leading-tight">{mc.verdict}</span>
                    </td>
                    <td className={`px-2 py-1 text-right num ${(s.total_return || 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{pct(s.total_return)}</td>
                    <td className={`px-2 py-1 text-right num ${(mc.return_without_best_trade || 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{pct(mc.return_without_best_trade)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {result && (
        <p className="text-[11px] mt-2">
          {result.error ? "enforce failed (is :8001 up?)"
            : result.disabled?.length
              ? <>Disabled {result.disabled.length}: <span className="text-[color:var(--down)]">{result.disabled.map((d: any) => d.strategy).join(", ")}</span></>
              : "No strategy failed robustness — none disabled."}
        </p>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-3">
        Monte Carlo bootstraps each strategy's trades; <b>fragile</b> = too few trades, no losses to
        model, or an edge that vanishes without its single best trade. <b>Enforce</b> disables
        strategies that fail on every tested market — re-enable them in the marketplace.
      </p>
    </Panel>
  );
}
