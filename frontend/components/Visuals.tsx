"use client";
import type { Portfolio } from "@/lib/types";
import { pct } from "@/lib/format";

const shortSym = (s: string) => s.replace(".NS", "").replace("=X", "").replace("-USD", "").replace("^", "");

function changeColor(chg: number): string {
  const t = Math.max(-1, Math.min(1, chg / 0.04)); // clamp ±4%
  const a = 0.12 + Math.abs(t) * 0.5;
  return t >= 0 ? `rgba(16,185,129,${a})` : `rgba(244,63,94,${a})`;
}

function corrColor(v: number): string {
  const a = 0.08 + Math.abs(v) * 0.55;
  return v >= 0 ? `rgba(16,185,129,${a})` : `rgba(244,63,94,${a})`;
}

export function Heatmap({ tiles }: { tiles: any[] }) {
  return (
    <div className="panel-pad flex flex-col gap-2">
      <span className="label">Market Heatmap</span>
      <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
        {tiles.filter((t) => !t.error).map((t) => (
          <div key={t.symbol} className="rounded-lg border border-white/[0.06] px-2 py-2"
               style={{ background: changeColor(t.change_pct) }}>
            <div className="truncate text-xs font-medium text-zinc-100">{shortSym(t.symbol)}</div>
            <div className={`num text-[11px] ${t.change_pct >= 0 ? "text-long-soft" : "text-short-soft"}`}>
              {t.change_pct >= 0 ? "+" : ""}{pct(t.change_pct, 2)}
            </div>
          </div>
        ))}
        {tiles.length === 0 && <div className="col-span-4 py-4 text-center text-xs text-zinc-600">loading…</div>}
      </div>
    </div>
  );
}

export function CorrelationMatrix({ data }: { data?: { symbols: string[]; matrix: number[][] } }) {
  const syms = data?.symbols ?? [];
  const m = data?.matrix ?? [];
  return (
    <div className="panel-pad flex flex-col gap-2">
      <span className="label">Correlation Matrix</span>
      {syms.length < 2 ? (
        <div className="py-6 text-center text-xs text-zinc-600">loading…</div>
      ) : (
        <div className="overflow-x-auto">
          <div className="inline-grid gap-px" style={{ gridTemplateColumns: `auto repeat(${syms.length}, 1fr)` }}>
            <div />
            {syms.map((s) => (
              <div key={s} className="num px-1 py-0.5 text-center text-[8px] text-zinc-500">{shortSym(s)}</div>
            ))}
            {m.map((row, i) => (
              <Row key={syms[i]} label={shortSym(syms[i])} row={row} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, row }: { label: string; row: number[] }) {
  return (
    <>
      <div className="num px-1 py-0.5 text-right text-[8px] text-zinc-500">{label}</div>
      {row.map((v, j) => (
        <div key={j} className="num grid h-5 min-w-[22px] place-items-center text-[8px] text-zinc-300"
             style={{ background: corrColor(v) }} title={`${v}`}>
          {v.toFixed(1)}
        </div>
      ))}
    </>
  );
}

export function AllocationDonut({ pf }: { pf?: Portfolio }) {
  const cash = pf?.account.cash ?? 0;
  const positions = pf?.positions ?? [];
  const segs = [
    ...positions.map((p) => ({ label: p.symbol, value: Math.abs(p.market_value) })),
    { label: "Cash", value: Math.max(0, cash) },
  ].filter((s) => s.value > 0);
  const total = segs.reduce((a, s) => a + s.value, 0) || 1;
  const colors = ["#22d3ee", "#6366f1", "#10b981", "#f59e0b", "#f43f5e", "#a855f7", "#64748b"];
  const C = 2 * Math.PI * 42;
  let offset = 0;

  return (
    <div className="panel-pad flex flex-col gap-2">
      <span className="label">Allocation</span>
      <div className="flex items-center gap-4">
        <svg viewBox="0 0 100 100" className="h-28 w-28 -rotate-90">
          {segs.map((s, i) => {
            const frac = s.value / total;
            const dash = frac * C;
            const el = (
              <circle key={s.label} cx="50" cy="50" r="42" fill="none"
                      stroke={colors[i % colors.length]} strokeWidth="11"
                      strokeDasharray={`${dash} ${C - dash}`} strokeDashoffset={-offset} />
            );
            offset += dash;
            return el;
          })}
        </svg>
        <div className="min-w-0 flex-1 space-y-1 text-xs">
          {segs.slice(0, 6).map((s, i) => (
            <div key={s.label} className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: colors[i % colors.length] }} />
              <span className="truncate text-zinc-300">{s.label}</span>
              <span className="num ml-auto text-zinc-500">{pct(s.value / total, 0)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
