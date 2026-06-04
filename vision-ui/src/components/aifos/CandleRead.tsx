import { useApi } from "@/lib/aifos/useFetch";
import { Panel, Chip, Empty } from "./Panel";

const dirTone = (s?: string) => (/bull/i.test(s || "") ? "up" : /bear/i.test(s || "") ? "down" : "default");
const edge = (s?: string) => (s === "bullish" ? "var(--up)" : s === "bearish" ? "var(--down)" : "var(--border)");

/** Candle Read — classic candlestick patterns on the latest bar with a plain-English
 *  "why", so the chart doubles as a lesson. Reads /api/candle-read. */
export function CandleRead({ symbol, interval }: { symbol: string; interval: string }) {
  const { data: r } = useApi<any>(`/api/candle-read?symbol=${encodeURIComponent(symbol)}&interval=${interval}`,
    { deps: [symbol, interval], pollMs: 20000 });
  if (!r) return <Panel title="Candle Read"><Empty>reading the candles…</Empty></Panel>;

  const pats: any[] = r.patterns || [];
  return (
    <Panel
      title="Candle Read"
      subtitle={`${symbol} · ${interval} · what the candles say`}
      right={<Chip tone={dirTone(r.bias)}>{r.bias}</Chip>}
    >
      {pats.length === 0 ? (
        <Empty>No notable candlestick pattern on the latest bar.</Empty>
      ) : (
        <div className="space-y-2">
          {pats.map((p, i) => (
            <div key={i} className="border-l-2 pl-2.5 py-0.5" style={{ borderColor: edge(p.bias) }}>
              <div className="text-[12px] font-medium flex items-center gap-1.5">
                <Chip tone={dirTone(p.bias)}>{p.bias}</Chip> {p.name}
              </div>
              <div className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">{p.meaning}</div>
            </div>
          ))}
        </div>
      )}
      <p className="text-[10px] text-muted-foreground/70 italic mt-3">{r.note}</p>
    </Panel>
  );
}
