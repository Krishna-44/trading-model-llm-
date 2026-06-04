"use client";
import type { Fundamentals } from "@/lib/types";
import { stanceColor } from "@/lib/format";

const compact = (n: number) =>
  new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 2 }).format(n);

function fmt(key: string, v: number | null): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (["roe", "profit_margin", "revenue_growth", "dividend_yield"].includes(key))
    return `${(v * 100).toFixed(1)}%`;
  if (key === "market_cap") return `₹${compact(v)}`;
  return v.toFixed(2);
}

const LABELS: [string, string][] = [
  ["pe", "P/E"], ["forward_pe", "Fwd P/E"], ["pb", "P/B"], ["roe", "ROE"],
  ["profit_margin", "Margin"], ["revenue_growth", "Rev growth"],
  ["debt_to_equity", "D/E"], ["dividend_yield", "Div yield"], ["market_cap", "Mkt cap"],
];

function Bar({ label, v }: { label: string; v: number }) {
  return (
    <div>
      <div className="mb-0.5 flex justify-between text-[10px] text-zinc-500">
        <span>{label}</span>
        <span className="num">{(v * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className={`h-full rounded-full ${v >= 0.6 ? "bg-long" : v >= 0.4 ? "bg-amber-400" : "bg-short"}`}
          style={{ width: `${Math.min(100, v * 100)}%` }}
        />
      </div>
    </div>
  );
}

export function ResearchPanel({ f, symbol }: { f?: Fundamentals; symbol: string }) {
  return (
    <div className="panel-pad flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="label">Fundamentals &amp; Valuation</span>
        <span className="chip border-white/10 text-zinc-500">
          {f?.source && f.source !== "none" ? `via ${f.source}` : "OpenBB-style"}
        </span>
      </div>

      {!f || !f.applicable ? (
        <div className="py-6 text-center text-xs text-zinc-600">
          Fundamentals apply to equities — N/A for {symbol}
        </div>
      ) : f.source === "none" ? (
        <div className="py-6 text-center text-xs text-zinc-600">no fundamental data available</div>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-zinc-200">{f.name || f.symbol}</div>
              {f.sector && <div className="text-[11px] text-zinc-500">{f.sector}</div>}
            </div>
            <span className={`chip border-white/10 ${stanceColor(f.stance)}`}>{f.stance}</span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Bar label="quality" v={f.quality_score} />
            <Bar label="value" v={f.value_score} />
          </div>

          <div className="grid grid-cols-3 gap-1.5">
            {LABELS.map(([k, lbl]) => (
              <div key={k} className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1.5">
                <div className="text-[9px] uppercase tracking-wide text-zinc-500">{lbl}</div>
                <div className="num text-xs text-zinc-200">{fmt(k, f.metrics[k] ?? null)}</div>
              </div>
            ))}
          </div>
          <p className="text-[11px] leading-snug text-zinc-500">{f.reasoning}</p>
        </>
      )}
    </div>
  );
}
