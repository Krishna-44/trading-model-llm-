"use client";
import type { RiskSnapshot } from "@/lib/types";
import { num } from "@/lib/format";

export function RiskDashboard({ risk }: { risk?: RiskSnapshot }) {
  const used = risk?.daily_loss_used_pct ?? 0;
  const limits = risk?.limits ?? {};
  return (
    <div className="panel-pad flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="label">Adaptive Risk Engine</span>
        {risk?.kill_switch_active ? (
          <span className="chip animate-pulseGlow border-short/50 bg-short/15 text-short-soft">● HALTED</span>
        ) : (
          <span className="chip border-long/30 bg-long/10 text-long-soft">● armed</span>
        )}
      </div>

      <div>
        <div className="mb-1 flex justify-between text-xs">
          <span className="text-zinc-400">daily loss budget</span>
          <span className="num text-zinc-300">{(used * 100).toFixed(0)}% used</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              used > 0.75 ? "bg-short" : used > 0.4 ? "bg-amber-400" : "bg-long"
            }`}
            style={{ width: `${Math.min(100, used * 100)}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-zinc-500">
          <span className="num">P&L {num(risk?.daily_pnl ?? 0, 0)}</span>
          <span className="num">limit {num(risk?.daily_loss_limit ?? 0, 0)}</span>
        </div>
      </div>

      {risk?.kill_reason && (
        <p className="rounded-lg border border-short/30 bg-short/[0.06] px-2.5 py-1.5 text-[11px] text-short-soft">
          {risk.kill_reason}
        </p>
      )}

      <div className="grid grid-cols-2 gap-1.5">
        <Limit k="confidence floor" v={`${((limits.confidence_threshold ?? 0) * 100).toFixed(0)}%`} />
        <Limit k="max position" v={`${((limits.max_position_pct ?? 0) * 100).toFixed(0)}%`} />
        <Limit k="max positions" v={`${limits.max_open_positions ?? 0}`} />
        <Limit k="min R:R" v={`${limits.min_rr_ratio ?? 0}`} />
        <Limit k="trades today" v={`${risk?.trades_today ?? 0}`} />
        <Limit k="memory" v={`${risk?.memory?.count ?? 0} situ.`} />
      </div>
    </div>
  );
}

function Limit({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-zinc-500">{k}</div>
      <div className="num text-xs text-zinc-200">{v}</div>
    </div>
  );
}
