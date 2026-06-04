import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";
import { Chip } from "./Panel";

/** Slim always-visible strip: am I "trained" yet (go-live readiness) + today's P&L
 *  + equity — so the minimal dashboard never loses sight of when real money unlocks. */
export function StatusStrip() {
  const { data: dep } = useApi<any>("/api/deployment", { pollMs: 15000 });
  const { data: today } = useApi<any>("/api/today", { pollMs: 12000 });
  const { data: cap } = useApi<any>("/api/capital", { pollMs: 12000 });

  const r = dep?.readiness || {};
  const passed = r.passed ?? 0;
  const total = r.total ?? 6;
  const pct = total ? Math.round((passed / total) * 100) : 0;
  const livePermitted = dep?.live_permitted ?? false;
  const booked = today?.live_pnl_today ?? today?.booked_today ?? 0;
  const pnl = cap?.total_pnl ?? 0;

  return (
    <div className="px-4 md:px-6 py-2 border-b border-border bg-background/40 backdrop-blur-md flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px]">
      <div className="flex items-center gap-2">
        <span className="uppercase text-muted-foreground text-[10px] tracking-wide">Trained?</span>
        <div className="w-24 h-1.5 bg-white/5 rounded-full overflow-hidden">
          <div className={`h-full ${livePermitted ? "bg-[color:var(--up)]" : "bg-[color:var(--cyan)]"}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="num text-muted-foreground">{passed}/{total} gates</span>
        <Chip tone={livePermitted ? "up" : "warn"}>{livePermitted ? "LIVE READY" : "LIVE LOCKED"}</Chip>
      </div>

      <div className="flex items-center gap-1.5">
        <span className="uppercase text-muted-foreground text-[10px] tracking-wide">Today</span>
        <span className={`num font-semibold ${booked >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
          {booked >= 0 ? "+" : ""}₹{fmt.n(booked)}
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <span className="uppercase text-muted-foreground text-[10px] tracking-wide">Equity</span>
        <span className="num">₹{fmt.n(cap?.equity)}</span>
        {cap && (
          <span className={`num ${pnl >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
            ({pnl >= 0 ? "+" : ""}₹{fmt.n(pnl)})
          </span>
        )}
      </div>

      <span className="ml-auto text-[10px] text-muted-foreground/60 italic">
        {dep?.mode || "paper"} · real money unlocks at {total}/{total} gates
      </span>
    </div>
  );
}
