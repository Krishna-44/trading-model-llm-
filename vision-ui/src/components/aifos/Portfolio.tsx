import { useWS } from "@/lib/aifos/ws";
import { useApi } from "@/lib/aifos/useFetch";
import { Panel, Chip, Empty } from "./Panel";
import { fmt } from "@/lib/aifos/api";

export function PortfolioPanel() {
  const { portfolio: ws } = useWS();
  const { data: api } = useApi<any>("/api/portfolio", { pollMs: 10000 });
  const p = ws || api;
  if (!p) return <Panel title="Portfolio"><Empty>backend offline</Empty></Panel>;
  const acc = p.account || {};
  const positions = p.positions || [];
  const curve = p.equity_curve || [];
  return (
    <Panel title="Portfolio" subtitle={`${p.mode || "paper"} · ${p.broker || "—"}`} right={<Chip tone="cyan">{positions.length} pos</Chip>}>
      <div className="flex items-end gap-3 mb-3">
        <div className="num text-3xl font-semibold">{fmt.usd(acc.equity)}</div>
        <div className="text-[10px] text-muted-foreground mb-1.5 num">{acc.currency || "USD"}</div>
      </div>
      <Sparkline points={curve.map((c: any) => c.equity)} />
      <div className="grid grid-cols-3 gap-2 mt-3 text-[11px]">
        <Stat k="Cash" v={fmt.usd(acc.cash)} />
        <Stat k="Realized" v={fmt.usd(acc.realized_pnl)} tone={acc.realized_pnl >= 0 ? "up" : "down"} />
        <Stat k="Unrealized" v={fmt.usd(p.unrealized_pnl)} tone={(p.unrealized_pnl ?? 0) >= 0 ? "up" : "down"} />
      </div>
      <div className="mt-3 max-h-40 overflow-auto">
        {positions.length === 0 && <Empty>No open positions.</Empty>}
        {positions.length > 0 && (
          <table className="w-full text-[11px]">
            <thead className="text-muted-foreground"><tr><th className="text-left font-normal py-1">Symbol</th><th className="text-right font-normal">Qty@Avg</th><th className="text-right font-normal">uPnL</th></tr></thead>
            <tbody>
              {positions.map((pos: any) => (
                <tr key={pos.symbol} className="border-t border-border/30">
                  <td className="py-1 num">{pos.symbol}</td>
                  <td className="text-right num">{fmt.n(pos.qty, 2)}@{fmt.n(pos.avg_price ?? pos.avg)}</td>
                  <td className={`text-right num ${(pos.unrealized_pnl ?? 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{fmt.usd(pos.unrealized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Panel>
  );
}

function Stat({ k, v, tone }: { k: string; v: string; tone?: "up" | "down" }) {
  return (
    <div className="bg-secondary/30 border border-border rounded-md px-2 py-1.5">
      <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
      <div className={`num text-xs ${tone === "up" ? "text-[color:var(--up)]" : tone === "down" ? "text-[color:var(--down)]" : ""}`}>{v}</div>
    </div>
  );
}

function Sparkline({ points }: { points: number[] }) {
  if (!points || points.length < 2) return <div className="h-12 text-[10px] text-muted-foreground italic">No equity history.</div>;
  const min = Math.min(...points), max = Math.max(...points), span = max - min || 1;
  const W = 300, H = 48;
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${(i / (points.length - 1)) * W},${H - ((p - min) / span) * H}`).join(" ");
  const up = points[points.length - 1] >= points[0];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-12" preserveAspectRatio="none">
      <path d={d} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth={1.5} />
      <path d={`${d} L${W},${H} L0,${H} Z`} fill={up ? "rgba(16,185,129,0.15)" : "rgba(244,63,94,0.15)"} />
    </svg>
  );
}

export function RiskEngine() {
  const { risk: ws } = useWS();
  const { data: api } = useApi<any>("/api/risk", { pollMs: 5000 });
  const r = ws || api;
  if (!r) return <Panel title="Adaptive Risk Engine"><Empty>backend offline</Empty></Panel>;
  const used = r.daily_loss_used_pct ?? 0;
  const usedPct = used > 1 ? used : used * 100;
  return (
    <Panel title="Adaptive Risk Engine" subtitle="Capital protection layer" right={<Chip tone={r.kill_switch_active ? "down" : "up"}>{r.kill_switch_active ? "HALTED" : "armed"}</Chip>}>
      <div>
        <div className="flex justify-between text-[10px] mb-1"><span className="text-muted-foreground uppercase">Daily Loss Budget</span><span className="num">{usedPct.toFixed(1)}% · {fmt.usd(r.daily_pnl)} / {fmt.usd(r.daily_loss_limit)}</span></div>
        <div className="h-2 bg-white/5 rounded-full overflow-hidden">
          <div className={`h-full ${usedPct > 80 ? "bg-[color:var(--down)]" : usedPct > 50 ? "bg-amber-400" : "bg-[color:var(--up)]"}`} style={{ width: `${Math.min(100, usedPct)}%` }} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
        <Stat k="Trades Today" v={String(r.trades_today ?? 0)} />
        <Stat k="Memory" v={String(r.memory?.count ?? 0)} />
        <Stat k="Conf Threshold" v={`${((r.limits?.confidence_threshold ?? 0) * (r.limits?.confidence_threshold > 1 ? 1 : 100)).toFixed(0)}%`} />
        <Stat k="Max Pos %" v={`${((r.limits?.max_position_pct ?? 0) * (r.limits?.max_position_pct > 1 ? 1 : 100)).toFixed(0)}%`} />
        <Stat k="Max Open" v={String(r.limits?.max_open_positions ?? "—")} />
        <Stat k="Min R:R" v={fmt.n(r.limits?.min_rr_ratio, 2)} />
      </div>
    </Panel>
  );
}
