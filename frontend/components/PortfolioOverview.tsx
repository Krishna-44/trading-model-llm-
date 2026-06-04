"use client";
import type { Portfolio } from "@/lib/types";
import { money, num, signColor } from "@/lib/format";

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return <div className="h-10" />;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * 100},${28 - ((v - min) / span) * 26}`)
    .join(" ");
  const up = data[data.length - 1] >= data[0];
  return (
    <svg viewBox="0 0 100 28" preserveAspectRatio="none" className="h-10 w-full">
      <polyline
        points={pts} fill="none" strokeWidth="1.5"
        className={up ? "stroke-long-soft" : "stroke-short-soft"}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function PortfolioOverview({ pf, ccy }: { pf?: Portfolio; ccy: string }) {
  const eq = pf?.account.equity ?? 0;
  const curve = pf?.equity_curve.map((p) => p.equity) ?? [];
  const unreal = pf?.unrealized_pnl ?? 0;
  const real = pf?.account.realized_pnl ?? 0;

  return (
    <div className="panel-pad flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="label">Portfolio</span>
        <span className="chip border-white/10 text-zinc-400">{pf?.broker ?? "—"}</span>
      </div>

      <div className="flex items-end justify-between">
        <div>
          <div className="num text-2xl font-semibold text-zinc-100">{money(eq, ccy)}</div>
          <div className="text-[11px] text-zinc-500">total equity</div>
        </div>
        <div className="text-right text-xs">
          <div className={`num ${signColor(unreal)}`}>{unreal >= 0 ? "+" : ""}{num(unreal, 0)}</div>
          <div className="text-[10px] text-zinc-500">unrealized</div>
        </div>
      </div>

      <Sparkline data={curve.length ? curve : [eq, eq]} />

      <div className="grid grid-cols-3 gap-1.5 text-center">
        <Mini k="cash" v={money(pf?.account.cash ?? 0, ccy)} />
        <Mini k="realized" v={`${real >= 0 ? "+" : ""}${num(real, 0)}`} tone={signColor(real)} />
        <Mini k="positions" v={`${pf?.open_positions ?? 0}`} />
      </div>

      <div className="-mr-1 max-h-44 space-y-1 overflow-y-auto pr-1">
        {pf?.positions.length ? (
          pf.positions.map((p) => (
            <div key={p.symbol} className="flex items-center justify-between rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 rounded-full ${p.qty >= 0 ? "bg-long" : "bg-short"}`} />
                <span className="font-medium text-zinc-200">{p.symbol}</span>
                <span className="num text-zinc-500">{num(p.qty, 2)} @ {num(p.avg_price)}</span>
              </div>
              <span className={`num ${signColor(p.unrealized_pnl)}`}>
                {p.unrealized_pnl >= 0 ? "+" : ""}{num(p.unrealized_pnl, 0)}
              </span>
            </div>
          ))
        ) : (
          <div className="py-3 text-center text-xs text-zinc-600">flat — holding cash</div>
        )}
      </div>
    </div>
  );
}

function Mini({ k, v, tone = "text-zinc-200" }: { k: string; v: string; tone?: string }) {
  return (
    <div className="rounded-md border border-white/[0.06] bg-white/[0.02] py-1.5">
      <div className={`num text-xs ${tone}`}>{v}</div>
      <div className="text-[9px] uppercase tracking-wide text-zinc-500">{k}</div>
    </div>
  );
}
