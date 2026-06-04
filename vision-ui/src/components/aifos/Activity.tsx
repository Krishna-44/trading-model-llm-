import { useEffect, useState } from "react";
import { useWSEvents } from "@/lib/aifos/ws";
import { Panel, Chip, Empty } from "./Panel";
import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";

export type ActivityItem = { kind: string; ts: number; seq?: number; payload: any };

export function useActivityFeed() {
  const [items, setItems] = useState<ActivityItem[]>([]);
  useWSEvents((e) => {
    if (e.kind === "decision" || e.kind === "fill" || e.kind === "control") {
      setItems((prev) => [{ kind: e.kind, ts: (e as any).ts || Date.now() / 1000, seq: (e as any).seq, payload: e }, ...prev].slice(0, 50));
    }
  });
  return items;
}

export function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return (
    <Panel title="Live Activity" subtitle="Streaming events">
      {!items.length && <Empty>Waiting for stream events…</Empty>}
      <div className="space-y-1.5 max-h-72 overflow-auto pr-1">
        {items.map((it, i) => {
          const p = it.payload;
          const tone = it.kind === "fill" ? "cyan" : it.kind === "control" ? "warn" : "indigo";
          return (
            <div key={i} className="flex items-start gap-2 text-[11px] border-b border-border/30 pb-1">
              <Chip tone={tone as any}>{it.kind}</Chip>
              <div className="flex-1 min-w-0">
                <div className="text-foreground/85 truncate">
                  {p.symbol && <span className="num text-[color:var(--cyan)] mr-1">{p.symbol}</span>}
                  {p.action && <span className="font-semibold mr-1">{p.action}</span>}
                  {p.side && <span className="mr-1">{p.side}</span>}
                  {p.qty != null && <span className="num mr-1">{fmt.n(p.qty, 2)}</span>}
                  {p.price != null && <span className="num">@ {fmt.n(p.price)}</span>}
                  {p.message && <span className="text-muted-foreground">{p.message}</span>}
                </div>
                <div className="text-[10px] text-muted-foreground num">{fmt.time(it.ts)} · seq {it.seq ?? "—"}</div>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

export function TradeLog() {
  const { data } = useApi<{ trades: any[] }>("/api/trades", { pollMs: 15000 });
  const trades = data?.trades || [];
  return (
    <Panel title="Trade Log" subtitle="Closed positions & fills">
      {!trades.length && <Empty>No trades yet.</Empty>}
      {trades.length > 0 && (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-[11px]">
            <thead className="text-muted-foreground sticky top-0 bg-background/80 backdrop-blur"><tr>
              <th className="text-left font-normal py-1">Time</th><th className="text-left font-normal">Sym</th><th className="text-left font-normal">Side</th>
              <th className="text-right font-normal">Qty</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">P&L</th><th className="text-right font-normal">Mode</th>
            </tr></thead>
            <tbody>
              {trades.map((t: any, i: number) => (
                <tr key={i} className="border-t border-border/30">
                  <td className="py-1 num text-muted-foreground">{fmt.time(t.ts)}</td>
                  <td className="num">{t.symbol}</td>
                  <td className={t.side === "buy" || t.side === "long" ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}>{t.side}</td>
                  <td className="text-right num">{fmt.n(t.qty, 2)}</td>
                  <td className="text-right num">{fmt.n(t.price)}</td>
                  <td className={`text-right num ${(t.realized_pnl ?? 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{fmt.usd(t.realized_pnl)}</td>
                  <td className="text-right text-[10px] text-muted-foreground">{t.mode}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
