import { useApi } from "@/lib/aifos/useFetch";
import { api, fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const pct = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
const biasTone = (b?: string) =>
  b === "trend" ? "up" : b === "range" ? "indigo" : b === "breakout" ? "warn" : "cyan";

/** Strategy Marketplace — every strategy backtested on the symbol, ranked by
 *  Sharpe, with enable/disable. The AI selects the best ENABLED one to trade. */
export function StrategyMarket({ symbol }: { symbol: string }) {
  const { data: d, refetch } = useApi<any>(`/api/strategies?symbol=${encodeURIComponent(symbol)}`, { deps: [symbol], pollMs: 60000 });
  if (!d) return <Panel title="Strategy Marketplace"><Empty>backtesting strategies…</Empty></Panel>;

  const strats = [...(d.strategies || [])].sort((a, b) => (b.sharpe ?? -9) - (a.sharpe ?? -9));
  const toggle = async (name: string, enabled: boolean) => {
    try { await api("/api/strategies/toggle", { method: "POST", body: JSON.stringify({ name, enabled }) }); refetch(); } catch {}
  };

  return (
    <Panel
      title="Strategy Marketplace"
      subtitle={`${symbol} · ${d.interval} · backtested & ranked by Sharpe`}
      right={d.best ? <Chip tone="cyan">★ best: {d.best}</Chip> : null}
    >
      <div className="space-y-1.5">
        {strats.map((s: any) => {
          const isBest = s.name === d.best;
          return (
            <div key={s.name} className={`border rounded-md p-2 ${isBest ? "border-[color:var(--cyan)]/50 bg-[color:var(--cyan)]/5" : "border-border bg-secondary/20"}`}>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-medium">{s.label || s.name}</span>
                {s.bias && <Chip tone={biasTone(s.bias)}>{s.bias}</Chip>}
                {isBest && <Chip tone="up">★ best</Chip>}
                <button
                  onClick={() => toggle(s.name, !s.enabled)}
                  className={`ml-auto chip ${s.enabled ? "border-[color:var(--up)]/40 text-[color:var(--up)] bg-[color:var(--up)]/10" : "border-border text-muted-foreground"}`}
                >
                  {s.enabled ? "● enabled" : "disabled"}
                </button>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{s.desc}</p>
              {"sharpe" in s ? (
                <div className="grid grid-cols-5 gap-1.5 mt-1.5 text-[10px]">
                  <M k="Return" v={pct(s.total_return)} tone={s.total_return >= 0 ? "up" : "down"} />
                  <M k="Sharpe" v={fmt.n(s.sharpe, 2)} tone={s.sharpe >= 0 ? "up" : "down"} />
                  <M k="Max DD" v={pct(s.max_drawdown)} tone="down" />
                  <M k="Win" v={`${Math.round((s.win_rate || 0) * 100)}%`} />
                  <M k="Trades" v={String(s.num_trades ?? 0)} />
                </div>
              ) : (
                <p className="text-[10px] text-[color:var(--down)] mt-1">backtest unavailable</p>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-muted-foreground/70 italic mt-3">{d.note}</p>
    </Panel>
  );
}

function M({ k, v, tone }: { k: string; v: string; tone?: "up" | "down" }) {
  return (
    <div className="bg-background/40 rounded px-1.5 py-1">
      <div className="text-[8px] uppercase text-muted-foreground">{k}</div>
      <div className={`num ${tone === "up" ? "text-[color:var(--up)]" : tone === "down" ? "text-[color:var(--down)]" : ""}`}>{v}</div>
    </div>
  );
}
