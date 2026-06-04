import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const inr = (v: number | null | undefined, d = 0) =>
  v == null || !Number.isFinite(v) ? "—" : `₹${fmt.n(v, d)}`;
const pnl = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : "−"}₹${fmt.n(Math.abs(v))}`;

const CLS_COLOR: Record<string, string> = {
  equity: "var(--cyan)", forex: "var(--indigo)", crypto: "#f59e0b", index: "#8b5cf6", options: "#6b7280",
};

/** Holdings & allocation — what's been bought and how much is invested per asset
 *  class (stocks / forex / crypto / options). Real positions, real numbers. */
export function HoldingsPanel() {
  const { data: h } = useApi<any>("/api/holdings", { pollMs: 6000 });
  if (!h) return <Panel title="Holdings & Allocation"><Empty>backend offline</Empty></Panel>;

  const positions: any[] = h.positions || [];
  const byClass: any[] = h.by_class || [];
  const total = h.total_invested || 0;

  return (
    <Panel
      title="Holdings & Allocation"
      subtitle={`${h.mode} · what's invested, by asset class`}
      right={<Chip tone="cyan">{inr(total)} invested</Chip>}
    >
      <div className="grid grid-cols-3 gap-2 text-[11px] mb-3">
        <Stat k="Equity" v={inr(h.equity)} />
        <Stat k="Invested" v={inr(total)} />
        <Stat k="Idle cash" v={inr(h.cash)} />
      </div>

      {/* allocation bar */}
      <div className="h-2 rounded-full overflow-hidden flex bg-white/5 mb-2">
        {byClass.filter((c) => c.invested > 0).map((c) => (
          <div key={c.key} style={{ width: `${c.pct}%`, background: CLS_COLOR[c.key] }} title={`${c.label} ${c.pct}%`} />
        ))}
      </div>

      {/* per asset class */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 mb-3">
        {byClass.map((c) => (
          <div key={c.key} className="bg-secondary/20 border border-border rounded px-2 py-1.5">
            <div className="flex items-center gap-1.5 text-[10px] uppercase text-muted-foreground">
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: CLS_COLOR[c.key] }} />{c.label}
            </div>
            <div className="num text-xs">{inr(c.invested)} <span className="text-muted-foreground text-[10px]">· {c.count}</span></div>
            {c.count > 0 && (
              <div className={`num text-[10px] ${c.unrealized_pnl >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{pnl(c.unrealized_pnl)}</div>
            )}
          </div>
        ))}
      </div>

      {/* open positions = what's been bought */}
      <div className="text-[10px] uppercase text-muted-foreground mb-1">Open positions · what's bought</div>
      {positions.length === 0 ? (
        <Empty>No open positions — nothing bought yet. Hit Start Trading.</Empty>
      ) : (
        <div className="max-h-48 overflow-auto">
          <table className="w-full text-[11px]">
            <thead className="text-muted-foreground">
              <tr>
                <th className="text-left font-normal py-1">Symbol</th>
                <th className="text-right font-normal">Qty@Avg</th>
                <th className="text-right font-normal">Invested</th>
                <th className="text-right font-normal">uPnL</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i} className="border-t border-border/30">
                  <td className="py-1 num">{p.symbol} <span className="text-muted-foreground text-[9px]">{p.asset_class}</span></td>
                  <td className="text-right num">{fmt.n(p.qty, 2)}@{fmt.n(p.avg_price)}</td>
                  <td className="text-right num">{inr(p.invested)}</td>
                  <td className={`text-right num ${p.unrealized_pnl >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{pnl(p.unrealized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-2">{h.note}</p>
    </Panel>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-secondary/30 border border-border rounded-md px-2 py-1.5">
      <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
      <div className="num text-xs">{v}</div>
    </div>
  );
}
