import { useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { PAPER_API_BASE } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const pct = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

const verdictTone = (v: string) =>
  v === "KEEP" ? "up" : v === "REVIEW" ? "warn" : "down";

const timeAgo = (iso?: string | null) => {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};

/** Strategies Cooking — continuous background discovery. Each cycle the loop
 *  picks one parameter variant of an existing strategy (or a hybrid), backtests
 *  it across the multi-market basket, runs Monte Carlo, and grades it honestly.
 *  Most variants DROP — that's the honest signal of what doesn't have edge. */
export function Cooking() {
  const { data, error } = useApi<any>("/api/cooking", { base: PAPER_API_BASE, pollMs: 15000 });
  const [showRecent, setShowRecent] = useState(false);

  if (error && !data)
    return <Panel title="Strategies Cooking"><Empty>paper instance offline (:8001)</Empty></Panel>;
  if (!data) return <Panel title="Strategies Cooking"><Empty>warming up the kitchen…</Empty></Panel>;

  const v = data.verdicts || {};
  const leaderboard: any[] = data.leaderboard || [];
  const recent: any[] = data.recent || [];
  const total = data.candidates_total || 0;
  const runs = data.rounds_run || 0;
  const coverage = total ? Math.min(100, Math.round((runs / total) * 100)) : 0;

  return (
    <Panel
      title="Strategies Cooking"
      subtitle={`background discovery · ${total} candidate variants · graded by real backtest + Monte Carlo`}
      right={
        <div className="flex items-center gap-2">
          <Chip tone="cyan">{runs} rounds</Chip>
          <span className="text-[10px] text-muted-foreground">last {timeAgo(data.last_round_ts)}</span>
        </div>
      }
    >
      {/* live verdict tally */}
      <div className="grid grid-cols-4 gap-2 mb-3">
        <Stat k="Candidates" v={String(total)} />
        <Stat k="KEEP" v={String(v.keep || 0)} tone="up" />
        <Stat k="REVIEW" v={String(v.review || 0)} tone="warn" />
        <Stat k="DROP" v={String(v.drop || 0)} tone="down" />
      </div>

      {/* coverage progress bar — how much of the candidate space has been cooked */}
      <div className="mb-3">
        <div className="flex justify-between text-[10px] text-muted-foreground mb-1">
          <span>Coverage</span>
          <span className="num">{coverage}% · {runs}/{total} rounds</span>
        </div>
        <div className="h-1.5 rounded-full bg-background/60 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-amber-400 to-[color:var(--cyan)] transition-all"
               style={{ width: `${coverage}%` }} />
        </div>
      </div>

      {/* leaderboard — best variants discovered so far */}
      <div className="mb-3">
        <div className="text-[10px] uppercase text-muted-foreground mb-1">Leaderboard · best variants</div>
        {leaderboard.length === 0 ? (
          <Empty>no rounds yet — the first one runs on the next trading cycle</Empty>
        ) : (
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="bg-secondary/30 text-muted-foreground text-[9px] uppercase tracking-wide">
                  <th className="text-left font-medium px-2 py-1">Variant</th>
                  <th className="text-right font-medium px-2 py-1">Avg return</th>
                  <th className="text-right font-medium px-2 py-1">MC robust</th>
                  <th className="text-left font-medium px-2 py-1 pl-3">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((r: any) => (
                  <tr key={r.variant_id} className="border-t border-border/50">
                    <td className="px-2 py-1 truncate"><span className="font-medium">{r.variant_id}</span></td>
                    <td className={`px-2 py-1 text-right num ${(r.avg_return || 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
                      {pct(r.avg_return)}
                    </td>
                    <td className="px-2 py-1 text-right num">{r.mc_robust_count}/{r.markets_tested}</td>
                    <td className="px-2 py-1 pl-3"><Chip tone={verdictTone(r.verdict)}>{r.verdict}</Chip></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* recent rounds — show what's been cooked moment-to-moment */}
      <button onClick={() => setShowRecent(!showRecent)}
              className="text-[10px] text-muted-foreground hover:text-foreground transition">
        {showRecent ? "▾ hide" : "▸ show"} recent rounds ({recent.length})
      </button>
      {showRecent && recent.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {recent.map((r: any) => (
            <div key={r.id} className="flex items-center gap-2 text-[10.5px]">
              <span className="text-muted-foreground num w-[70px] shrink-0">{timeAgo(r.ts)}</span>
              <span className="truncate flex-1">{r.variant_id}</span>
              <span className={`num shrink-0 ${(r.avg_return || 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
                {pct(r.avg_return)}
              </span>
              <Chip tone={verdictTone(r.verdict)}>{r.verdict}</Chip>
            </div>
          ))}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-3">
        Real research — each round backtests a variant on 4 markets + Monte Carlo. Most DROP;
        that's honest, not a bug. KEEP variants are candidates for promotion to the live
        marketplace (never auto-deployed — human review only).
      </p>
    </Panel>
  );
}

function Stat({ k, v, tone }: { k: string; v: string; tone?: "up" | "down" | "warn" }) {
  const color = tone === "up" ? "text-[color:var(--up)]" : tone === "down" ? "text-[color:var(--down)]" : tone === "warn" ? "text-amber-400" : "";
  return (
    <div className="bg-secondary/20 border border-border rounded px-2 py-1.5">
      <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
      <div className={`num text-[13px] ${color}`}>{v}</div>
    </div>
  );
}
