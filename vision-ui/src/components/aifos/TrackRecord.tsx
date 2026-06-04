import { useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { api, fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const inr = (v: number | null | undefined, d = 0) =>
  v == null || !Number.isFinite(v) ? "—" : `₹${fmt.n(v, d)}`;
const pctOf = (frac: number | null | undefined, d = 2) =>
  frac == null || !Number.isFinite(frac) ? "—" : `${frac >= 0 ? "+" : ""}${(frac * 100).toFixed(d)}%`;

/**
 * The "prove it before real money" scoreboard — honest forward paper performance
 * since inception, straight from /api/track-record. Zeros are real, never invented.
 */
export function TrackRecord() {
  const { data: t, refetch } = useApi<any>("/api/track-record", { pollMs: 15000 });
  const [busy, setBusy] = useState(false);

  if (!t) return <Panel title="Forward Track Record"><Empty>backend offline</Empty></Panel>;

  const ret = t.total_return ?? 0;
  const up = ret >= 0;
  const curve = (t.curve || []).map((c: any) => c.equity);

  const onReset = async () => {
    if (!window.confirm("Wipe the paper track record and restart the clock from the starting book? This cannot be undone.")) return;
    setBusy(true);
    try {
      await api("/api/track-record/reset", { method: "POST", body: JSON.stringify({ confirm: true }) });
      refetch();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Forward Track Record"
      subtitle={`${t.mode || "paper"} · prove it before real money · since ${t.inception ? new Date(t.inception).toLocaleDateString() : "—"}`}
      right={
        <div className="flex items-center gap-2">
          <Chip tone={up ? "up" : "down"}>{pctOf(ret)}</Chip>
          <button
            onClick={onReset}
            disabled={busy}
            className="chip border-border/60 text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors disabled:opacity-50"
            title="Wipe paper history and start a fresh forward test"
          >
            {busy ? "resetting…" : "Start the clock"}
          </button>
        </div>
      }
    >
      <div className="flex items-end gap-3 mb-2">
        <div className="num text-3xl font-semibold">{inr(t.current_equity)}</div>
        <div className="text-[10px] text-muted-foreground mb-1.5">
          from {inr(t.starting_capital)} · {fmt.n(t.days_running, 1)}d
        </div>
      </div>

      <Sparkline points={curve} up={up} />

      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mt-3 text-[11px]">
        <Stat k="Realized" v={inr(t.realized_pnl)} tone={(t.realized_pnl ?? 0) >= 0 ? "up" : "down"} />
        <Stat k="Unrealized" v={inr(t.unrealized_pnl)} tone={(t.unrealized_pnl ?? 0) >= 0 ? "up" : "down"} />
        <Stat k="Decisions" v={`${t.decisions ?? 0}`} />
        <Stat k="Executed" v={`${t.executed ?? 0} · ${((t.execution_rate ?? 0) * 100).toFixed(0)}%`} />
        <Stat k="Win rate" v={t.closed_trades ? `${((t.win_rate ?? 0) * 100).toFixed(0)}%` : "—"} />
        <Stat k="Profit factor" v={t.closed_trades ? fmt.n(t.profit_factor, 2) : "—"} />
        <Stat k="Max DD" v={pctOf(t.max_drawdown, 1)} tone={(t.max_drawdown ?? 0) < 0 ? "down" : undefined} />
        <Stat k="Sharpe" v={fmt.n(t.sharpe, 2)} />
      </div>

      <p className="text-[10px] text-muted-foreground/70 italic mt-3 leading-relaxed">{t.note}</p>
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

function Sparkline({ points, up }: { points: number[]; up: boolean }) {
  if (!points || points.length < 2)
    return (
      <div className="h-12 flex items-center text-[10px] text-muted-foreground italic">
        Equity curve builds as cycles run — turn on Autonomous (or Run Cycle) to accumulate a forward record.
      </div>
    );
  const min = Math.min(...points), max = Math.max(...points), span = max - min || 1;
  const W = 300, H = 48;
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${(i / (points.length - 1)) * W},${H - ((p - min) / span) * H}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-12" preserveAspectRatio="none">
      <path d={d} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth={1.5} />
      <path d={`${d} L${W},${H} L0,${H} Z`} fill={up ? "rgba(16,185,129,0.15)" : "rgba(244,63,94,0.15)"} />
    </svg>
  );
}
