import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const dirTone = (s?: string) => (/bull/i.test(s || "") ? "up" : /bear/i.test(s || "") ? "down" : "default");

/** NSE options-chain intelligence — PCR, max pain, OI support/resistance walls.
 *  Real data when a feed is reachable; honest "unavailable" otherwise (no fake OI). */
export function OptionsChain({ symbol }: { symbol: string }) {
  const { data: o } = useApi<any>(`/api/options?symbol=${encodeURIComponent(symbol)}`, { deps: [symbol], pollMs: 30000 });

  if (!o) return <Panel title="Options Chain Intelligence"><Empty>loading…</Empty></Panel>;

  if (!o.available) {
    return (
      <Panel title="Options Chain Intelligence" subtitle="NSE OI · PCR · max pain">
        <div className="text-[11px] leading-relaxed">
          <p className="text-amber-300/90 mb-1">Live NSE options feed unavailable.</p>
          <p className="text-muted-foreground">{o.reason}</p>
          <p className="mt-2 text-muted-foreground/70">
            The intelligence engine (PCR, max pain, OI walls, IV) is built and verified — it activates
            the moment a real feed is connected (a broker's option-chain API in Phase 3). No OI is invented.
          </p>
        </div>
      </Panel>
    );
  }

  const pin = o.max_pain_vs_spot_pct;
  return (
    <Panel
      title="Options Chain Intelligence"
      subtitle={`NSE ${o.nse_symbol} · exp ${o.expiry} · spot ${fmt.n(o.spot)}`}
      right={<Chip tone={dirTone(o.bias)}>{o.bias} · PCR {o.pcr}</Chip>}
    >
      <div className="grid grid-cols-3 gap-2 text-[11px] mb-3">
        <Stat k="PCR" v={String(o.pcr)} />
        <Stat k="Max Pain" v={`${fmt.n(o.max_pain)}${pin != null ? ` · ${pin >= 0 ? "+" : ""}${pin}%` : ""}`} />
        <Stat k="Avg IV" v={`${o.avg_iv}%`} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Wall title="Resistance · call OI" rows={(o.resistance || []).map((r: any) => [r.strike, r.ce_oi])} tone="down" />
        <Wall title="Support · put OI" rows={(o.support || []).map((r: any) => [r.strike, r.pe_oi])} tone="up" />
      </div>

      <p className="text-[11px] text-muted-foreground mt-3">{o.reasoning}</p>
      <p className="text-[10px] text-muted-foreground/70 italic mt-1">{o.note}</p>
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

function Wall({ title, rows, tone }: { title: string; rows: [number, number][]; tone: "up" | "down" }) {
  return (
    <div className="bg-secondary/20 border border-border rounded-md p-2">
      <div className="text-[9px] uppercase text-muted-foreground mb-1">{title}</div>
      {rows.map(([strike, oi], i) => (
        <div key={i} className="flex justify-between text-[11px] num">
          <span className={tone === "up" ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}>{fmt.n(strike)}</span>
          <span className="text-muted-foreground">{fmt.compact(oi)}</span>
        </div>
      ))}
    </div>
  );
}
