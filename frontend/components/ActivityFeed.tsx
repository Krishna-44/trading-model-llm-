"use client";
import type { TradeRow } from "@/lib/types";
import { num, signColor, timeAgo } from "@/lib/format";

const ACTION_TONE: Record<string, string> = {
  BUY: "text-long-soft", SELL: "text-short-soft", HOLD: "text-zinc-500",
};

export function ActivityFeed({ events }: { events: any[] }) {
  return (
    <div className="panel-pad flex h-full flex-col gap-2">
      <span className="label">Live Activity</span>
      <div className="-mr-1 flex-1 space-y-1 overflow-y-auto pr-1">
        {events.length === 0 && <div className="py-4 text-center text-xs text-zinc-600">awaiting events…</div>}
        {events.map((e) => (
          <div key={e.seq} className="flex items-center gap-2 rounded-md border border-white/[0.05] bg-white/[0.02] px-2.5 py-1.5 text-xs">
            <Kind kind={e.kind} />
            <span className="truncate text-zinc-300">
              {e.kind === "decision" && (
                <>
                  <span className={ACTION_TONE[e.decision?.action] ?? ""}>{e.decision?.action}</span>{" "}
                  <span className="font-medium">{e.decision?.symbol}</span>{" "}
                  <span className="num text-zinc-500">{((e.decision?.confidence ?? 0) * 100).toFixed(0)}%</span>
                </>
              )}
              {e.kind === "fill" && (
                <><span className="text-accent-soft">FILL</span> {e.symbol} <span className="num text-zinc-500">{num(e.fill?.qty, 2)} @ {num(e.fill?.price)}</span></>
              )}
              {e.kind === "control" && <span className="text-amber-300">{e.event} {e.reason ?? (e.on ? "on" : "off")}</span>}
            </span>
            <span className="num ml-auto shrink-0 text-[10px] text-zinc-600">{timeAgo(e.ts)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TradeLog({ trades }: { trades: TradeRow[] }) {
  return (
    <div className="panel-pad flex h-full flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="label">Trade Log</span>
        <span className="text-[11px] text-zinc-500">{trades.length}</span>
      </div>
      <div className="-mr-1 flex-1 space-y-1 overflow-y-auto pr-1">
        {trades.length === 0 && <div className="py-4 text-center text-xs text-zinc-600">no executed trades yet</div>}
        {trades.map((t, i) => (
          <div key={i} className="flex items-center justify-between rounded-md border border-white/[0.05] bg-white/[0.02] px-2.5 py-1.5 text-xs">
            <div className="flex items-center gap-2">
              <span className={`chip border-white/10 ${t.side === "buy" ? "text-long-soft" : "text-short-soft"}`}>{t.side}</span>
              <span className="font-medium text-zinc-200">{t.symbol}</span>
              <span className="num text-zinc-500">{num(t.qty, 2)} @ {num(t.price)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`num ${signColor(t.realized_pnl)}`}>{t.realized_pnl ? (t.realized_pnl > 0 ? "+" : "") + num(t.realized_pnl, 0) : "—"}</span>
              <span className="num text-[10px] text-zinc-600">{timeAgo(t.ts)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Kind({ kind }: { kind: string }) {
  const map: Record<string, string> = {
    decision: "bg-accent", fill: "bg-long", control: "bg-amber-400",
  };
  return <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${map[kind] ?? "bg-zinc-600"}`} />;
}
