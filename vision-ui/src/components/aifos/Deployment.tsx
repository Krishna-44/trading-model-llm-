import { useApi } from "@/lib/aifos/useFetch";
import { Panel, Chip, Empty } from "./Panel";

/** Staged live-trading safety: the empirical "earn trust" gate that blocks real
 *  money until the forward paper test clears every threshold. Reads /api/deployment. */
export function Deployment() {
  const { data: d } = useApi<any>("/api/deployment", { pollMs: 15000 });
  if (!d) return <Panel title="Go-Live Readiness"><Empty>backend offline</Empty></Panel>;

  const r = d.readiness || {};
  const gates: any[] = r.gates || [];

  return (
    <Panel
      title="Go-Live Readiness"
      subtitle={`staged pipeline · ${d.mode} mode · stage: ${d.stage_label}`}
      right={<Chip tone={d.live_permitted ? "up" : "warn"}>{d.live_permitted ? "LIVE PERMITTED" : "LIVE BLOCKED"}</Chip>}
    >
      {/* stage stepper: paper → micro → scaling */}
      <div className="flex items-center gap-2 mb-3">
        {(d.stages || []).map((s: any) => {
          const active = s.key === d.stage;
          return (
            <div
              key={s.key}
              className={`flex-1 rounded-md border px-2 py-1.5 text-center ${active ? "border-[color:var(--cyan)] bg-[color:var(--cyan)]/10" : "border-border bg-secondary/20"}`}
              title={s.desc}
            >
              <div className={`text-[10px] uppercase ${active ? "text-[color:var(--cyan)]" : "text-muted-foreground"}`}>{s.label}</div>
              <div className="text-[9px] text-muted-foreground/70">{s.live ? "real money" : "paper"}</div>
            </div>
          );
        })}
      </div>

      {/* readiness gates */}
      <div className="text-[10px] uppercase text-muted-foreground mb-1.5">
        Readiness gates · {r.passed}/{r.total} passed
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 mb-3">
        {gates.map((g, i) => (
          <div key={i} className="flex items-center justify-between text-[11px] bg-secondary/20 border border-border rounded px-2 py-1">
            <span className="flex items-center gap-1.5 min-w-0">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${g.pass ? "bg-[color:var(--up)]" : "bg-[color:var(--down)]"}`} />
              <span className="text-muted-foreground truncate">{g.name}</span>
            </span>
            <span className="num shrink-0">{g.value} {g.op} {g.threshold}</span>
          </div>
        ))}
      </div>

      {/* what's blocking live */}
      {!d.live_permitted && (
        <div className="text-[11px]">
          <div className="text-[10px] uppercase text-muted-foreground mb-1">Blocking live execution</div>
          <ul className="space-y-0.5">
            {(d.blocking || []).map((b: string, i: number) => (
              <li key={i} className="text-amber-300/80 flex gap-1.5"><span>•</span><span>{b}</span></li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-3">{d.note}</p>
    </Panel>
  );
}
