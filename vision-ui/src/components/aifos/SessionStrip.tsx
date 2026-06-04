import { useApi } from "@/lib/aifos/useFetch";

/** Thin always-visible bar: which markets are open right now and what the engine
 *  is rotating to (NSE → forex → crypto). Reads /api/sessions. */
export function SessionStrip() {
  const { data: s } = useApi<any>("/api/sessions", { pollMs: 30000 });
  if (!s) return null;

  return (
    <div className="px-4 md:px-6 py-1.5 border-b border-border bg-background/30 flex flex-wrap items-center gap-x-5 gap-y-1 text-[10.5px]">
      <span className="num text-muted-foreground">{s.now_ist}</span>
      <Market label="NSE" on={s.nse_open} />
      <Market label={`Forex${s.forex_sessions?.length ? " · " + s.forex_sessions.join("/") : ""}`} on={s.forex_open} />
      <Market label="Crypto" on={true} suffix="24/7" />
      <span className="text-muted-foreground">
        <span className="uppercase text-[9px] tracking-wide">Focus</span>{" "}
        <span className="text-foreground/80">{s.focus}</span>
      </span>
      <span className="ml-auto text-muted-foreground/70">{s.tradeable_count} markets tradeable now</span>
    </div>
  );
}

function Market({ label, on, suffix }: { label: string; on: boolean; suffix?: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${on ? "bg-[color:var(--up)] dot-pulse" : "bg-muted-foreground/40"}`} />
      <span className={on ? "text-foreground/80" : "text-muted-foreground"}>{label} {suffix || (on ? "open" : "closed")}</span>
    </span>
  );
}
