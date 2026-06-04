import { useApi } from "@/lib/aifos/useFetch";
import { Panel, Chip, Empty } from "./Panel";
import { fmt } from "@/lib/aifos/api";

export function Fundamentals({ symbol }: { symbol: string }) {
  const { data, loading } = useApi<any>(`/api/research/fundamentals?symbol=${symbol}`, { deps: [symbol] });
  return (
    <Panel title="Fundamentals & Valuation" subtitle={symbol} right={data?.source && <Chip>{data.source}</Chip>}>
      {loading && <div className="text-xs text-muted-foreground animate-pulse">loading…</div>}
      {!loading && data && data.applicable === false && <Empty>N/A — not an equity ({data?.reasoning || "non-equity asset"}).</Empty>}
      {data && data.applicable !== false && (
        <div className="space-y-3">
          <div>
            <div className="text-sm font-semibold">{data.name || symbol}</div>
            <div className="text-[11px] text-muted-foreground">{data.sector || "—"}</div>
          </div>
          <ScoreBar label="Quality" value={data.quality_score} />
          <ScoreBar label="Value" value={data.value_score} />
          <div className="grid grid-cols-3 gap-1.5 text-[11px]">
            {[
              ["P/E", data.metrics?.pe],
              ["Fwd P/E", data.metrics?.forward_pe],
              ["P/B", data.metrics?.pb],
              ["ROE", data.metrics?.roe, "pct"],
              ["Margin", data.metrics?.profit_margin, "pct"],
              ["Rev Growth", data.metrics?.revenue_growth, "pct"],
              ["D/E", data.metrics?.debt_to_equity],
              ["Div Yield", data.metrics?.dividend_yield, "pct"],
              ["Mkt Cap", data.metrics?.market_cap, "compact"],
            ].map(([k, v, t]: any) => (
              <div key={k} className="bg-secondary/30 border border-border rounded-md px-2 py-1.5">
                <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
                <div className="num text-xs">
                  {v == null ? "—" : t === "pct" ? fmt.pct(v * (v < 1 && v > -1 ? 100 : 1), 1) : t === "compact" ? fmt.compact(v) : fmt.n(v, 2)}
                </div>
              </div>
            ))}
          </div>
          {data.reasoning && <p className="text-[11px] text-foreground/70 leading-relaxed border-l-2 border-[color:var(--cyan)]/50 pl-2">{data.reasoning}</p>}
          {data.stance && <Chip tone={data.stance?.toLowerCase().includes("buy") ? "up" : data.stance?.toLowerCase().includes("sell") ? "down" : "default"}>{data.stance}</Chip>}
        </div>
      )}
    </Panel>
  );
}

function ScoreBar({ label, value }: { label: string; value?: number }) {
  const v = ((value ?? 0) > 1 ? value : (value ?? 0) * 100) || 0;
  return (
    <div>
      <div className="flex justify-between text-[10px] mb-0.5"><span className="text-muted-foreground uppercase">{label}</span><span className="num">{v.toFixed(0)}</span></div>
      <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-[color:var(--cyan)] to-[color:var(--indigo)]" style={{ width: `${Math.min(100, Math.max(0, v))}%` }} />
      </div>
    </div>
  );
}

export function Heatmap() {
  const { data } = useApi<{ tiles: Array<{ symbol: string; asset_class: string; price: number; change_pct: number }> }>("/api/market/heatmap", { pollMs: 5000 });
  const tiles = data?.tiles || [];
  return (
    <Panel title="Market Heatmap" subtitle="Universe % change">
      {!tiles.length && <Empty>No tiles.</Empty>}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-1.5">
        {tiles.map((t) => {
          const p = t.change_pct ?? 0;
          const intensity = Math.min(1, Math.abs(p) / 5);
          const bg = p >= 0 ? `rgba(16,185,129,${0.15 + intensity * 0.5})` : `rgba(244,63,94,${0.15 + intensity * 0.5})`;
          return (
            <div key={t.symbol} style={{ backgroundColor: bg }} className="rounded-md border border-white/5 p-2">
              <div className="text-[10px] font-semibold truncate">{t.symbol}</div>
              <div className="num text-xs">{fmt.n(t.price)}</div>
              <div className={`num text-[10px] ${p >= 0 ? "text-emerald-200" : "text-rose-200"}`}>{fmt.pct(p)}</div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

export function Correlation() {
  const { data } = useApi<{ symbols: string[]; matrix: number[][] }>("/api/analytics/correlation", { pollMs: 30000 });
  const syms = data?.symbols || []; const m = data?.matrix || [];
  return (
    <Panel title="Correlation Matrix" subtitle="Cross-asset relationships">
      {!syms.length && <Empty>No matrix.</Empty>}
      {!!syms.length && (
        <div className="overflow-auto">
          <table className="text-[10px] num border-separate border-spacing-0.5">
            <thead><tr><th></th>{syms.map((s) => <th key={s} className="px-1 text-muted-foreground font-normal">{s}</th>)}</tr></thead>
            <tbody>
              {syms.map((s, i) => (
                <tr key={s}>
                  <td className="pr-1 text-muted-foreground text-right">{s}</td>
                  {syms.map((_, j) => {
                    const v = m[i]?.[j] ?? 0;
                    const bg = v >= 0 ? `rgba(34,211,238,${Math.abs(v) * 0.7})` : `rgba(244,63,94,${Math.abs(v) * 0.7})`;
                    return <td key={j} style={{ backgroundColor: bg }} className="w-9 h-7 text-center rounded">{v.toFixed(2)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

export function AllocationDonut({ positions }: { positions?: Array<{ symbol: string; market_value?: number; qty?: number; price?: number }> }) {
  const segs = (positions || []).map((p) => ({ label: p.symbol, value: Math.abs(p.market_value ?? (p.qty ?? 0) * (p.price ?? 0)) })).filter((s) => s.value > 0);
  const total = segs.reduce((a, b) => a + b.value, 0);
  const colors = ["#22d3ee","#6366f1","#10b981","#f59e0b","#f43f5e","#a855f7","#06b6d4","#eab308"];
  let acc = 0;
  return (
    <Panel title="Allocation" subtitle="Portfolio weights">
      <div className="flex items-center gap-4">
        <svg viewBox="0 0 100 100" className="w-32 h-32 -rotate-90">
          <circle cx={50} cy={50} r={40} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={14} />
          {total === 0 ? (
            <circle cx={50} cy={50} r={40} fill="none" stroke="#22d3ee" strokeWidth={14} />
          ) : segs.map((s, i) => {
            const dash = (s.value / total) * (2 * Math.PI * 40);
            const off = (acc / total) * (2 * Math.PI * 40);
            acc += s.value;
            return <circle key={s.label} cx={50} cy={50} r={40} fill="none" stroke={colors[i % colors.length]} strokeWidth={14} strokeDasharray={`${dash} ${2 * Math.PI * 40}`} strokeDashoffset={-off} />;
          })}
        </svg>
        <div className="flex-1 text-[11px] space-y-1">
          {total === 0 && <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-[#22d3ee]" /><span>100% Cash</span></div>}
          {segs.map((s, i) => (
            <div key={s.label} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: colors[i % colors.length] }} />
              <span className="flex-1">{s.label}</span>
              <span className="num text-muted-foreground">{((s.value / total) * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}
