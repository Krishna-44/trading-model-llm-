"use client";
import type { Decision } from "@/lib/types";
import { num } from "@/lib/format";

const ACTION = {
  BUY: { ring: "stroke-long", text: "text-long-soft", bg: "bg-long/10 border-long/30" },
  SELL: { ring: "stroke-short", text: "text-short-soft", bg: "bg-short/10 border-short/30" },
  HOLD: { ring: "stroke-zinc-500", text: "text-zinc-300", bg: "bg-white/[0.04] border-white/10" },
} as const;

export function ConfidenceMeter({ decision, threshold }: { decision?: Decision; threshold: number }) {
  const conf = decision?.confidence ?? 0;
  const action = (decision?.action ?? "HOLD") as keyof typeof ACTION;
  const style = ACTION[action];
  const R = 52;
  const C = 2 * Math.PI * R;
  const dash = C * conf;
  const passed = conf >= threshold;

  return (
    <div className="panel-pad flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="label">AI Confidence</span>
        <span className={`chip ${style.bg} ${style.text}`}>{action}</span>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative h-32 w-32 shrink-0">
          <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
            <circle cx="60" cy="60" r={R} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="9" />
            <circle
              cx="60" cy="60" r={R} fill="none" strokeWidth="9" strokeLinecap="round"
              className={style.ring}
              strokeDasharray={`${dash} ${C}`}
              style={{ transition: "stroke-dasharray 0.7s cubic-bezier(.4,0,.2,1)" }}
            />
            {/* threshold tick */}
            <circle
              cx={60 + R * Math.cos(2 * Math.PI * threshold)}
              cy={60 + R * Math.sin(2 * Math.PI * threshold)}
              r="3" className="fill-accent"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`num text-2xl font-semibold ${style.text}`}>{(conf * 100).toFixed(0)}%</span>
            <span className="text-[10px] text-zinc-500">conf.</span>
          </div>
        </div>

        <div className="min-w-0 flex-1 space-y-2 text-sm">
          <div className="flex items-center gap-2 text-xs">
            <span className="h-2 w-2 rounded-full bg-accent" />
            <span className="text-zinc-400">trade threshold</span>
            <span className="num ml-auto text-zinc-300">{(threshold * 100).toFixed(0)}%</span>
          </div>
          <div className={`rounded-lg border px-2.5 py-1.5 text-xs ${passed ? "border-long/25 text-long-soft" : "border-white/10 text-zinc-400"}`}>
            {passed ? "✓ above threshold — actionable" : "below threshold — holding"}
          </div>
          {decision?.sizing?.rr_ratio ? (
            <div className="grid grid-cols-3 gap-1.5 pt-1">
              <Stat k="entry" v={num(decision.sizing.entry)} />
              <Stat k="stop" v={num(decision.sizing.stop_loss)} tone="text-short-soft" />
              <Stat k="target" v={num(decision.sizing.take_profit)} tone="text-long-soft" />
              <Stat k="R:R" v={`${num(decision.sizing.rr_ratio, 2)}`} />
              <Stat k="size" v={num(decision.sizing.size_value, 0)} />
              <Stat k="risk" v={num(decision.sizing.risk_amount, 0)} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Stat({ k, v, tone = "text-zinc-200" }: { k: string; v: string; tone?: string }) {
  return (
    <div className="rounded-md border border-white/[0.06] bg-white/[0.02] px-1.5 py-1">
      <div className="text-[9px] uppercase tracking-wide text-zinc-500">{k}</div>
      <div className={`num text-xs ${tone}`}>{v}</div>
    </div>
  );
}
