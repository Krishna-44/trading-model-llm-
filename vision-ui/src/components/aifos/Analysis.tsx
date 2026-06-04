import { useState } from "react";
import { api, fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";
import { CandleChart } from "./CandleChart";
import { Gauge } from "./Gauge";
import { useApi } from "@/lib/aifos/useFetch";
import { ShieldAlert } from "lucide-react";

export function ChartPanel({ symbol, interval }: { symbol: string; interval: string }) {
  const { data, loading, error } = useApi<{ source: string; candles: any[] }>(`/api/market/candles?symbol=${symbol}&interval=${interval}&lookback=240`, { pollMs: 30000, deps: [symbol, interval] });
  return (
    <Panel title={`${symbol} · ${interval}`} subtitle="Price action" right={data?.source && <Chip tone={data.source === "yfinance" ? "up" : "default"}>{data.source === "yfinance" ? "live data" : data.source}</Chip>} className="h-full" padded={false}>
      <div className="h-full min-h-[360px] p-2">
        {error && <div className="p-4 text-xs text-rose-300">backend offline — chart unavailable</div>}
        {loading && !data && <div className="p-4 text-xs text-muted-foreground">loading candles…</div>}
        {data?.candles?.length ? <CandleChart candles={data.candles} /> : !loading && <Empty>No candle data.</Empty>}
      </div>
    </Panel>
  );
}

type Analysis = {
  action: string; side?: string; confidence: number; reasoning?: string; llm_summary?: string; source?: string;
  sizing?: { entry?: number; stop_loss?: number; take_profit?: number; rr_ratio?: number; size_value?: number };
  opinions?: Array<{ agent: string; stance: string; confidence: number; weight: number; reasoning: string; veto?: boolean }>;
};

export function AnalysisPanels({ symbol, interval, analysis, analyzing, setAnalysis }: {
  symbol: string; interval: string;
  analysis: Analysis | null; analyzing: boolean;
  setAnalysis: (a: Analysis | null) => void;
}) {
  return (
    <>
      <Panel title="AI Confidence" subtitle="Probability-gated decision" className="h-full">
        {!analysis && !analyzing && <Empty>Click Analyze to run the committee.</Empty>}
        {analyzing && <div className="text-xs text-muted-foreground animate-pulse">running committee…</div>}
        {analysis && (
          <div className="flex flex-col items-center gap-3">
            <Gauge value={(analysis.confidence ?? 0) * (analysis.confidence > 1 ? 1 : 100)} label="confidence" />
            <div className="flex items-center gap-2">
              <Chip tone={analysis.action === "BUY" ? "up" : analysis.action === "SELL" ? "down" : "default"}>
                {analysis.action}{analysis.side ? ` · ${analysis.side}` : ""}
              </Chip>
              {analysis.source && <Chip>{analysis.source}</Chip>}
            </div>
            {analysis.sizing && (
              <div className="grid grid-cols-2 gap-2 w-full text-[11px] mt-1">
                <SzCell k="Entry" v={fmt.n(analysis.sizing.entry)} />
                <SzCell k="Stop" v={fmt.n(analysis.sizing.stop_loss)} />
                <SzCell k="Target" v={fmt.n(analysis.sizing.take_profit)} />
                <SzCell k="R:R" v={fmt.n(analysis.sizing.rr_ratio, 2)} />
                <SzCell k="Size" v={fmt.usd(analysis.sizing.size_value)} className="col-span-2" />
              </div>
            )}
          </div>
        )}
      </Panel>

      <Panel title="Decision Rationale" subtitle="Committee verdict" className="h-full">
        {!analysis && <Empty>Awaiting analysis.</Empty>}
        {analysis && (
          <div className="text-sm leading-relaxed text-foreground/85 whitespace-pre-wrap">
            {analysis.llm_summary || analysis.reasoning || "—"}
            {analysis.source && <div className="mt-3 text-[10px] text-muted-foreground">source: {analysis.source}</div>}
          </div>
        )}
      </Panel>

      <Panel title="Agent Committee" subtitle="Multi-agent stances · weighted" className="h-full lg:col-span-2">
        {!analysis?.opinions?.length && <Empty>Agents will appear after analysis.</Empty>}
        {analysis?.opinions && (
          <div className="space-y-2">
            <div className="text-[11px] text-muted-foreground bg-secondary/30 border border-border rounded-lg px-3 py-2">
              <span className="font-semibold text-foreground/90">Desk Rationale: </span>
              {analysis.llm_summary || analysis.reasoning || "—"}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {analysis.opinions.map((o, i) => {
                const tone = o.stance?.toLowerCase().includes("buy") || o.stance?.toLowerCase().includes("long") ? "up" : o.stance?.toLowerCase().includes("sell") || o.stance?.toLowerCase().includes("short") ? "down" : "default";
                const conf = (o.confidence ?? 0) * (o.confidence > 1 ? 1 : 100);
                return (
                  <div key={i} className="border border-border rounded-lg p-2.5 bg-secondary/20">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-xs font-semibold">{o.agent}</span>
                      <div className="flex gap-1 items-center">
                        {o.veto && <Chip tone="warn"><ShieldAlert className="w-3 h-3" /> VETO</Chip>}
                        <Chip tone={tone as any}>{o.stance}</Chip>
                      </div>
                    </div>
                    <div className="h-1 rounded-full bg-white/5 overflow-hidden mb-1.5">
                      <div className={`h-full ${tone === "up" ? "bg-[color:var(--up)]" : tone === "down" ? "bg-[color:var(--down)]" : "bg-muted-foreground"}`} style={{ width: `${Math.min(100, conf)}%` }} />
                    </div>
                    <div className="text-[10px] text-muted-foreground flex justify-between mb-1">
                      <span className="num">{conf.toFixed(0)}% conf</span>
                      <span className="num">w {fmt.n(o.weight, 2)}</span>
                    </div>
                    <p className="text-[11px] text-foreground/70 leading-relaxed">{o.reasoning}</p>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Panel>
    </>
  );
}

function SzCell({ k, v, className = "" }: { k: string; v: string; className?: string }) {
  return (
    <div className={`flex items-center justify-between bg-secondary/30 border border-border rounded-md px-2 py-1 ${className}`}>
      <span className="text-muted-foreground">{k}</span><span className="num text-foreground">{v}</span>
    </div>
  );
}

export function useAnalyze() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const run = async (symbol: string, interval: string) => {
    setAnalyzing(true);
    try {
      const a = await api<Analysis>("/api/analyze", { method: "POST", body: JSON.stringify({ symbol, interval }) });
      setAnalysis(a);
    } catch { setAnalysis(null); } finally { setAnalyzing(false); }
  };
  return { analysis, analyzing, run, setAnalysis };
}
