import { useApi } from "@/lib/aifos/useFetch";
import { Panel, Chip, Empty } from "./Panel";

/** Self-learning view — honest lessons mined from realized P&L + resolved journal
 *  outcomes (win/loss per trade). Reads /api/learning. No profit is promised. */
export function LearningPanel() {
  const { data: l } = useApi<any>("/api/learning", { pollMs: 12000 });
  if (!l) return <Panel title="Self-Learning"><Empty>backend offline</Empty></Panel>;

  const outcomes = (l.journal || []).filter((j: any) => j.outcome && j.outcome !== "open");

  return (
    <Panel
      title="Self-Learning"
      subtitle={`learns from realized P&L · intraday ${l.trading_interval}`}
      right={<Chip tone={l.autonomous ? "up" : "default"}>{l.autonomous ? "● TRADING" : "idle"}</Chip>}
    >
      <div className="grid grid-cols-4 gap-2 text-[11px] mb-3">
        <Stat k="Decisions" v={String(l.decisions ?? 0)} />
        <Stat k="Closed trades" v={String(l.closed_trades ?? 0)} />
        <Stat k="Win rate" v={l.closed_trades ? `${Math.round((l.win_rate || 0) * 100)}%` : "—"} />
        <Stat k="Memory" v={String(l.memory?.count ?? 0)} />
      </div>

      <div className="text-[10px] uppercase text-muted-foreground mb-1">Lessons learned</div>
      <ul className="space-y-1 mb-3">
        {(l.lessons || []).map((s: string, i: number) => (
          <li key={i} className="text-[11px] text-foreground/80 flex gap-1.5">
            <span className="text-[color:var(--cyan)]">•</span><span>{s}</span>
          </li>
        ))}
      </ul>

      {outcomes.length > 0 && (
        <>
          <div className="text-[10px] uppercase text-muted-foreground mb-1.5">Recent trade outcomes</div>
          <div className="flex flex-wrap gap-1.5">
            {outcomes.slice(0, 12).map((j: any, i: number) => (
              <Chip key={i} tone={j.outcome === "win" ? "up" : j.outcome === "loss" ? "down" : "default"}>
                {j.symbol} · {j.outcome}
              </Chip>
            ))}
          </div>
        </>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-3">{l.note}</p>
    </Panel>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-secondary/30 border border-border rounded-md px-2 py-1.5">
      <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
      <div className="num text-xs">{v}</div>
    </div>
  );
}
