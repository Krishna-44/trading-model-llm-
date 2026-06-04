"use client";
import type { Decision } from "@/lib/types";
import { stanceColor } from "@/lib/format";

export function AgentPanel({ decision }: { decision?: Decision }) {
  return (
    <div className="panel-pad flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="label">Agent Committee</span>
        <span className="text-[11px] text-zinc-500">{decision?.opinions.length ?? 0} agents</span>
      </div>

      {decision?.llm_summary && (
        <div className="rounded-xl border border-accent/20 bg-accent/[0.06] p-3">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-accent-soft">
            <SparkIcon /> Desk Rationale
          </div>
          <p className="text-[13px] leading-relaxed text-zinc-300">{decision.llm_summary}</p>
        </div>
      )}

      <div className="-mr-1 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {decision?.opinions.map((o) => (
          <div
            key={o.agent}
            className={`group rounded-lg border bg-white/[0.02] px-3 py-2 transition hover:bg-white/[0.04] ${
              o.veto ? "border-short/40" : "border-white/[0.06]"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium text-zinc-200">{o.agent}</span>
              <div className="flex shrink-0 items-center gap-2">
                {o.veto && <span className="chip border-short/40 bg-short/10 text-short-soft">VETO</span>}
                <span className={`text-xs font-medium ${stanceColor(o.stance)}`}>{o.stance}</span>
              </div>
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                <div
                  className={`h-full rounded-full ${
                    o.stance === "bullish" ? "bg-long" : o.stance === "bearish" ? "bg-short" : "bg-zinc-500"
                  }`}
                  style={{ width: `${o.confidence * 100}%` }}
                />
              </div>
              <span className="num w-9 text-right text-[11px] text-zinc-400">{(o.confidence * 100).toFixed(0)}%</span>
            </div>
            <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-zinc-500 group-hover:line-clamp-none">
              {o.reasoning}
            </p>
          </div>
        ))}
        {!decision && <Empty label="Run analysis to convene the committee" />}
      </div>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="flex h-full items-center justify-center text-sm text-zinc-600">{label}</div>;
}

function SparkIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2l2.2 6.6L21 11l-6.8 2.4L12 20l-2.2-6.6L3 11l6.8-2.4z" />
    </svg>
  );
}
