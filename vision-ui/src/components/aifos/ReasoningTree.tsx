import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const dirTone = (s?: string) =>
  /up|bull|long|buy/i.test(s || "") ? "up" : /down|bear|short|sell/i.test(s || "") ? "down" : "default";

/** Auditable "why" for the current decision: regime, smart-money, indicators,
 *  the full committee and the risk plan — straight from /api/explain. */
export function ReasoningTree({ symbol }: { symbol: string }) {
  const { data: e } = useApi<any>(`/api/explain?symbol=${encodeURIComponent(symbol)}`, { deps: [symbol], pollMs: 60000 });
  if (!e) return <Panel title="AI Reasoning Tree"><Empty>Loading the decision rationale…</Empty></Panel>;

  const d = e.decision || {};
  const reg = e.regime || {};
  const smc = e.smc || {};
  const ind = e.indicators || {};
  const rp = e.risk_plan || {};
  const agents = (e.agents || []).filter((a: any) => a.weight > 0 || a.veto);

  return (
    <Panel
      title="AI Reasoning Tree"
      subtitle={`why this decision · ${e.symbol} @ ${fmt.n(e.price)}`}
      right={<Chip tone={dirTone(d.action)}>{d.action} · {Math.round((d.confidence || 0) * 100)}%</Chip>}
    >
      <p className="text-[12px] text-foreground/80 mb-3 leading-relaxed">{d.summary || d.reasoning}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Branch title="Market Regime">
          <Chip tone={dirTone(reg.regime)}>{reg.regime || "—"}</Chip>
          <Kv k="ADX (trend strength)" v={String(reg.adx ?? "—")} />
          <Kv k="Volatility vs median" v={`${reg.vol_ratio ?? "—"}×`} />
        </Branch>

        <Branch title="Smart Money (SMC)">
          <Chip tone={dirTone(smc.bias)}>{smc.bias || "—"} · {smc.score ?? 0}</Chip>
          <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">{smc.reasoning}</p>
        </Branch>

        <Branch title="Indicators">
          <div className="grid grid-cols-3 gap-1.5">
            <Ind k="RSI" v={ind.rsi} />
            <Ind k="MACD" v={ind.macd_hist} />
            <Ind k="ADX" v={ind.adx} />
            <Ind k="Supertrend" v={ind.supertrend_dir === 1 ? "↑ up" : ind.supertrend_dir === -1 ? "↓ down" : "—"} />
            <Ind k="Stoch %K" v={ind.stoch_k} />
            <Ind k="vs VWAP" v={ind.vs_vwap != null ? `${(ind.vs_vwap * 100).toFixed(1)}%` : "—"} />
          </div>
        </Branch>

        <Branch title="Risk Plan">
          {rp.entry && rp.stop_loss ? (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              <Kv k="Entry" v={fmt.n(rp.entry)} />
              <Kv k="Stop" v={fmt.n(rp.stop_loss)} />
              <Kv k="Target" v={fmt.n(rp.take_profit)} />
              <Kv k="Reward : Risk" v={fmt.n(rp.rr_ratio, 2)} />
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Holding — no trade. {(rp.rejections || []).join("; ") || "edge/threshold not met."}
            </p>
          )}
        </Branch>
      </div>

      <div className="mt-3">
        <div className="text-[10px] uppercase text-muted-foreground mb-1">Committee · {agents.length} voices</div>
        <div className="max-h-44 overflow-auto pr-1">
          {agents.map((a: any, i: number) => (
            <div key={i} className="flex items-start gap-2 text-[11px] border-t border-border/30 py-1.5 first:border-t-0">
              <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${a.veto ? "bg-amber-400" : a.stance === "bullish" ? "bg-[color:var(--up)]" : a.stance === "bearish" ? "bg-[color:var(--down)]" : "bg-muted-foreground/40"}`} />
              <div className="min-w-0 flex-1">
                <span className="text-foreground/90">{a.agent}</span>
                <span className="text-muted-foreground"> · {a.stance} {Math.round((a.confidence || 0) * 100)}%{a.veto ? " · VETO" : ""}</span>
                <div className="text-muted-foreground/80 truncate">{a.reasoning}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function Branch({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-secondary/20 border border-border rounded-md p-2.5">
      <div className="text-[10px] uppercase text-muted-foreground mb-1.5">{title}</div>
      {children}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between text-[11px] mt-0.5">
      <span className="text-muted-foreground">{k}</span>
      <span className="num">{v}</span>
    </div>
  );
}

function Ind({ k, v }: { k: string; v: any }) {
  return (
    <div className="bg-background/40 rounded px-1.5 py-1">
      <div className="text-[8px] uppercase text-muted-foreground tracking-wide">{k}</div>
      <div className="num text-[11px]">{v ?? "—"}</div>
    </div>
  );
}
