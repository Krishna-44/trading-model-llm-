import { useApi } from "@/lib/aifos/useFetch";
import { Panel, Chip, Dot, Empty } from "./Panel";
import { fmt } from "@/lib/aifos/api";

export function NewsIntel({ symbol }: { symbol: string }) {
  const { data } = useApi<any>(`/api/news?symbol=${symbol}`, { deps: [symbol] });
  const heads = data?.headlines || [];
  const agg = data?.aggregate;
  return (
    <Panel title="News Intelligence" subtitle={symbol} right={agg && <Chip tone={agg.sentiment > 0.1 ? "up" : agg.sentiment < -0.1 ? "down" : "default"}>sent {fmt.n(agg.sentiment, 2)} · imp {fmt.n(agg.avg_impact, 1)}</Chip>}>
      {!heads.length && <Empty>No headlines.</Empty>}
      <div className="space-y-2 max-h-72 overflow-auto pr-1">
        {heads.map((h: any, i: number) => {
          const tone = h.sentiment > 0.1 ? "border-[color:var(--up)]" : h.sentiment < -0.1 ? "border-[color:var(--down)]" : "border-muted-foreground/40";
          return (
            <a key={i} href={h.link} target="_blank" rel="noreferrer" className={`block border-l-2 ${tone} pl-2 py-1 hover:bg-secondary/30 rounded-r transition`}>
              <div className="text-xs leading-snug">{h.title}</div>
              <div className="text-[10px] text-muted-foreground flex gap-2 mt-0.5 num">
                <span>{h.publisher || "—"}</span>
                <span>·</span>
                <span>impact {fmt.n(h.impact_score, 1)}</span>
                <span>·</span>
                <span>{fmt.time(h.ts)}</span>
              </div>
            </a>
          );
        })}
      </div>
      <HistoricalEchoes symbol={symbol} title={heads[0]?.title} />
    </Panel>
  );
}

function HistoricalEchoes({ symbol, title }: { symbol: string; title?: string }) {
  const url = title ? `/api/news/similar?symbol=${symbol}&title=${encodeURIComponent(title)}` : null;
  const { data } = useApi<any>(url, { deps: [symbol, title] });
  const matches = data?.matches || [];
  if (!matches.length) return null;
  return (
    <div className="mt-3 pt-3 border-t border-border">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">Historical Echoes</div>
      <div className="space-y-1">
        {matches.slice(0, 3).map((m: any, i: number) => (
          <div key={i} className="text-[11px] flex items-center gap-2">
            <span className="num text-[color:var(--cyan)]">{m.symbol}</span>
            <span className="truncate flex-1 text-foreground/70">{m.title}</span>
            <span className="num text-muted-foreground">sim {fmt.n(m.similarity, 2)}</span>
            <span className={`num font-semibold ${m.forward_return_5d == null ? "text-muted-foreground" : m.forward_return_5d >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
              {m.forward_return_5d == null ? "—" : fmt.pct(m.forward_return_5d * (Math.abs(m.forward_return_5d) < 1 ? 100 : 1), 1)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ExecutionEngine() {
  const { data } = useApi<any>("/api/execution/status", { pollMs: 5000 });
  if (!data) return <Panel title="Execution Engine"><Empty>backend offline</Empty></Panel>;
  const rows: Array<[string, any, boolean | undefined]> = [
    ["Broker", `${data.broker?.name || data.broker || "—"} · ${data.broker?.mode || data.mode || "—"}`, !!data.broker],
    ["Live Gate", data.live_gate || (data.live ? "open" : "closed"), data.live_gate === "open" || data.live],
    ["Data Feed", `${data.data_feed?.source || data.source || "—"} · ${data.data_feed?.latency_ms ?? data.latency_ms ?? "—"}ms`, !!data.data_feed],
    ["LLM", data.llm ? "on" : "off", !!data.llm],
    ["Slippage", `${data.slippage_bps ?? "—"} bps`, true],
    ["Commission", `${data.commission_bps ?? "—"} bps`, true],
    ["Orders", `${data.orders ?? 0} ok · ${data.failed ?? 0} failed`, (data.failed ?? 0) === 0],
    ["Autonomous", data.autonomous ? "ON" : "OFF", data.autonomous],
  ];
  return (
    <Panel title="Execution Engine" subtitle="Order flow status">
      <div className="space-y-1.5">
        {rows.map(([k, v, ok]) => (
          <div key={k} className="flex items-center justify-between text-[11px] border-b border-border/50 pb-1">
            <span className="text-muted-foreground flex items-center gap-2"><Dot on={!!ok} color={ok ? "emerald" : "rose"} /> {k}</span>
            <span className="num text-foreground/90">{String(v)}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
