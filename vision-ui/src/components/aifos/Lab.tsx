import { useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { Panel, Chip, Empty } from "./Panel";
import { api, fmt } from "@/lib/aifos/api";

export function AILab({ symbol }: { symbol: string }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <ExternalAlerts />
      <VideoLearning />
      <RLSearch symbol={symbol} />
    </div>
  );
}

function ExternalAlerts() {
  const { data, refetch } = useApi<any>("/api/alerts/status", { pollMs: 30000 });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  return (
    <Panel title="External Alerts" subtitle="Channels & test pings">
      <div className="space-y-2 text-[11px]">
        {!data && <Empty>—</Empty>}
        {data && Object.entries(data.channels || data || {}).map(([k, v]: any) => (
          <div key={k} className="flex justify-between"><span className="text-muted-foreground">{k}</span><Chip tone={v?.enabled || v === true ? "up" : "default"}>{v?.enabled || v === true ? "on" : "off"}</Chip></div>
        ))}
        <button disabled={busy} onClick={async () => { setBusy(true); setMsg(""); try { const r = await api<any>("/api/alerts/test", { method: "POST" }); setMsg(r?.message || "sent"); refetch(); } catch { setMsg("failed"); } finally { setBusy(false); } }} className="mt-2 w-full px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-secondary/60 transition">{busy ? "sending…" : "Send test alert"}</button>
        {msg && <div className="text-[10px] text-muted-foreground">{msg}</div>}
      </div>
    </Panel>
  );
}

function VideoLearning() {
  const [url, setUrl] = useState("");
  const [strategy, setStrategy] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Panel title="Video Learning" subtitle="Extract strategy from YouTube">
      <div className="space-y-2">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://youtube.com/…" className="w-full text-xs bg-secondary/60 border border-border rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-[color:var(--cyan)]/60" />
        <button disabled={!url || busy} onClick={async () => { setBusy(true); try { const r = await api<any>("/api/learn/video", { method: "POST", body: JSON.stringify({ url }) }); setStrategy(r?.strategy || r); } catch { setStrategy(null); } finally { setBusy(false); } }} className="w-full px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-[color:var(--cyan)] to-[color:var(--indigo)] text-background disabled:opacity-60">{busy ? "extracting…" : "Extract Strategy"}</button>
        {strategy && (
          <div className="text-[11px] space-y-1.5 mt-2">
            {strategy.indicators?.length > 0 && <Row k="Indicators" v={strategy.indicators.join(", ")} />}
            {strategy.entry_rules?.length > 0 && <Row k="Entry" v={strategy.entry_rules.join(" · ")} />}
            {strategy.exit_rules?.length > 0 && <Row k="Exit" v={strategy.exit_rules.join(" · ")} />}
            {strategy.method && <Row k="Method" v={strategy.method} />}
          </div>
        )}
      </div>
    </Panel>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div><span className="text-[10px] uppercase text-muted-foreground">{k}</span><div className="text-foreground/85 leading-snug">{v}</div></div>;
}

function RLSearch({ symbol }: { symbol: string }) {
  const { data, refetch } = useApi<any>("/api/rl/status", { pollMs: 5000 });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  return (
    <Panel title="RL Strategy Search" subtitle={`Train · ${symbol}`}>
      <div className="space-y-2 text-[11px]">
        {data && Object.entries(data).slice(0, 4).map(([k, v]: any) => (
          <div key={k} className="flex justify-between border-b border-border/40 pb-0.5"><span className="text-muted-foreground">{k}</span><span className="num truncate ml-2">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span></div>
        ))}
        <button disabled={busy} onClick={async () => { setBusy(true); try { const r = await api<any>("/api/rl/train", { method: "POST", body: JSON.stringify({ symbol }) }); setResult(r); refetch(); } catch { setResult({ status: "failed" }); } finally { setBusy(false); } }} className="w-full px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-secondary/60 transition">{busy ? "training…" : "Train"}</button>
        {result && (
          <div className="text-[11px] space-y-1 mt-1">
            <Row k="Status" v={String(result.status)} />
            {result.final_equity != null && <Row k="Final equity" v={fmt.usd(result.final_equity)} />}
            {result.buy_hold_equity != null && <Row k="Buy & hold" v={fmt.usd(result.buy_hold_equity)} />}
          </div>
        )}
      </div>
    </Panel>
  );
}

export function PerformanceAnalytics({ symbol }: { symbol: string }) {
  const { data } = useApi<any>(`/api/analytics?symbol=${symbol}`, { deps: [symbol], pollMs: 30000 });
  const live = data?.live || {};
  const strats = data?.strategies || [];
  const noTrades = !live.num_trades && !live.sharpe;
  return (
    <Panel title="Performance Analytics" subtitle="Live & strategy comparison" className="col-span-full">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] uppercase text-muted-foreground mb-2">Live Metrics</div>
          {noTrades && <div className="text-[11px] text-muted-foreground/80 italic mb-2">Populates as trades close. Past performance ≠ future results.</div>}
          <div className="grid grid-cols-3 gap-2 text-[11px]">
            {[
              ["Sharpe", live.sharpe], ["Sortino", live.sortino], ["Max DD", live.max_drawdown, "pct"],
              ["Profit Factor", live.profit_factor], ["Win Rate", live.win_rate, "pct"], ["Expectancy", live.expectancy, "usd"],
              ["Daily P&L", live.daily_pnl, "usd"], ["Weekly P&L", live.weekly_pnl, "usd"], ["Monthly P&L", live.monthly_pnl, "usd"],
            ].map(([k, v, t]: any) => (
              <div key={k} className="bg-secondary/30 border border-border rounded-md px-2 py-1.5">
                <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
                <div className="num text-xs">{v == null ? "—" : t === "pct" ? fmt.pct(v * (Math.abs(v) < 1 ? 100 : 1), 1) : t === "usd" ? fmt.usd(v) : fmt.n(v, 2)}</div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-muted-foreground mb-2">Strategy Comparison</div>
          {!strats.length && <Empty>No strategy results.</Empty>}
          {strats.length > 0 && (
            <div className="overflow-auto max-h-80">
              <table className="w-full text-[11px]">
                <thead className="text-muted-foreground sticky top-0 bg-background/80"><tr>
                  <th className="text-left font-normal py-1">Strategy</th>
                  <th className="text-right font-normal">Return</th><th className="text-right font-normal">Sharpe</th>
                  <th className="text-right font-normal">DD</th><th className="text-right font-normal">Win</th>
                  <th className="text-right font-normal">PF</th><th className="text-right font-normal">N</th>
                </tr></thead>
                <tbody>
                  {strats.map((s: any, i: number) => (
                    <tr key={i} className="border-t border-border/30">
                      <td className="py-1">{s.strategy}</td>
                      <td className={`text-right num ${(s.total_return ?? 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{fmt.pct(s.total_return * (Math.abs(s.total_return) < 1 ? 100 : 1), 1)}</td>
                      <td className="text-right num">{fmt.n(s.sharpe, 2)}</td>
                      <td className="text-right num text-[color:var(--down)]">{fmt.pct(s.max_drawdown * (Math.abs(s.max_drawdown) < 1 ? 100 : 1), 1)}</td>
                      <td className="text-right num">{fmt.pct(s.win_rate * (Math.abs(s.win_rate) < 1 ? 100 : 1), 0)}</td>
                      <td className="text-right num">{fmt.n(s.profit_factor, 2)}</td>
                      <td className="text-right num text-muted-foreground">{s.num_trades}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="text-[10px] text-muted-foreground mt-2 italic">Past performance ≠ future results.</div>
        </div>
      </div>
    </Panel>
  );
}
