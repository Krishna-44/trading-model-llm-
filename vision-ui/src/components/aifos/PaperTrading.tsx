import { useApi } from "@/lib/aifos/useFetch";
import { PAPER_API_BASE, fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const CLS: Record<string, string> = {
  equity: "Equity · intraday", forex: "Forex", crypto: "Crypto",
  index: "Index", options: "Options", unknown: "Other",
};
const inr = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v < 0 ? "−" : ""}₹${fmt.n(Math.abs(v), 0)}`;

/** Paper-trading scoreboard — reads the forward instance (:8001), separate from the
 *  AngelOne monitor on :8000. Booked profit vs loss, by market and by strategy. */
export function PaperTrading() {
  const { data, error } = useApi<any>("/api/pnl/breakdown", { base: PAPER_API_BASE, pollMs: 8000 });
  const { data: tdata } = useApi<any>("/api/trades", { base: PAPER_API_BASE, pollMs: 8000 });
  const { data: pf } = useApi<any>("/api/portfolio", { base: PAPER_API_BASE, pollMs: 8000 });
  const { data: mar } = useApi<any>("/api/control/marathon", { base: PAPER_API_BASE, pollMs: 6000 });
  const { data: tr } = useApi<any>("/api/track-record", { base: PAPER_API_BASE, pollMs: 10000 });

  if (error && !data)
    return <Panel title="Paper Trading"><Empty>paper instance offline (:8001) — start it with <code className="text-foreground/80">scripts/paper-forward.sh status</code></Empty></Panel>;
  if (!data) return <Panel title="Paper Trading"><Empty>loading paper record…</Empty></Panel>;

  const t = data.totals || {};
  const acct = data.account || {};
  const classes: any[] = data.by_class || [];
  const strats: any[] = data.by_strategy || [];
  const trades: any[] = (tdata?.trades || tdata || []).filter((x: any) => x?.realized_pnl);
  const has = (t.trades || 0) > 0;
  const positions: any[] = pf?.positions || [];
  const openUpnl = pf?.unrealized_pnl || 0;
  // marathon progress: equity between ₹0 (ruin) and its high-water peak
  const curve: number[] = (tr?.curve || []).map((c: any) => c.equity || 0);
  const start = mar?.starting_capital ?? acct.equity ?? 1000000;
  const equity = mar?.equity ?? acct.equity ?? start;
  const peak = Math.max(start, equity, ...curve);
  const ddFromPeak = peak > 0 ? (equity - peak) / peak : 0;
  const running = !!mar?.marathon;
  const capPct = Math.max(0, Math.min(1, peak ? equity / peak : 0));

  return (
    <Panel
      title="Paper Trading"
      subtitle="forward instance · booked P&L by market & strategy"
      right={
        <div className="flex items-center gap-2">
          <Chip tone="cyan">PAPER · :8001</Chip>
          <span className={`num text-[12px] ${(t.net_booked || 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
            net {inr(t.net_booked)}
          </span>
        </div>
      }
    >
      <div className="mb-3 rounded-md border border-border bg-secondary/10 p-2.5">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <Chip tone={running ? "up" : "warn"}>{running ? "● marathon running" : "○ marathon stopped"}</Chip>
          <span className="text-[11px] num">{inr(equity)}</span>
          <span className="text-[10px] text-muted-foreground">peak {inr(peak)}</span>
          <span className={`text-[10px] num ml-auto ${ddFromPeak >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
            {(ddFromPeak * 100).toFixed(1)}% from peak
          </span>
        </div>
        <div className="h-2 rounded-full bg-background/60 overflow-hidden relative" title="equity between ₹0 (ruin) and the high-water peak">
          <div className={`h-full ${capPct > 0.5 ? "bg-[color:var(--up)]" : capPct > 0.2 ? "bg-amber-400" : "bg-[color:var(--down)]"}`} style={{ width: `${capPct * 100}%` }} />
          <div className="absolute top-0 h-full w-px bg-foreground/50" style={{ left: `${Math.min(100, peak ? (start / peak) * 100 : 0)}%` }} title={`start ${inr(start)}`} />
        </div>
        <div className="flex justify-between text-[8px] text-muted-foreground mt-0.5">
          <span>₹0 · ruin</span><span>start {inr(start)}</span><span>peak {inr(peak)}</span>
        </div>
        {curve.length > 1 && <Sparkline pts={curve} />}
      </div>

      <div className="grid grid-cols-4 gap-2 mb-3">
        <Stat k="Equity" v={inr(acct.equity)} />
        <Stat k="Profit booked" v={inr(t.profit_booked)} tone="up" />
        <Stat k="Loss booked" v={inr(t.loss_booked)} tone="down" />
        <Stat k="Net booked" v={inr(t.net_booked)} tone={(t.net_booked || 0) >= 0 ? "up" : "down"} />
      </div>

      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] uppercase text-muted-foreground">Open positions · live</div>
          {positions.length > 0 && (
            <span className={`num text-[11px] ${openUpnl >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
              open uPnL {inr(openUpnl)}
            </span>
          )}
        </div>
        {positions.length === 0 ? (
          <div className="text-[11px] text-muted-foreground/60 italic px-2 py-1.5 border border-border rounded bg-secondary/10">
            flat — no open positions right now (the loop opens them when conviction clears the bar)
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="bg-secondary/30 text-muted-foreground text-[9px] uppercase tracking-wide">
                  <th className="text-left font-medium px-2 py-1">Symbol</th>
                  <th className="text-left font-medium px-2 py-1">Side</th>
                  <th className="text-right font-medium px-2 py-1">Qty</th>
                  <th className="text-right font-medium px-2 py-1">Avg</th>
                  <th className="text-right font-medium px-2 py-1">Live uPnL</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p: any, i: number) => {
                  const long = (p.qty || 0) >= 0;
                  return (
                    <tr key={i} className="border-t border-border/50">
                      <td className="px-2 py-1 font-medium">{p.symbol}</td>
                      <td className="px-2 py-1"><Chip tone={long ? "up" : "down"}>{long ? "long" : "short"}</Chip></td>
                      <td className="px-2 py-1 text-right num">{fmt.n(Math.abs(p.qty || 0), 4)}</td>
                      <td className="px-2 py-1 text-right num">{fmt.n(p.avg_price, 2)}</td>
                      <td className={`px-2 py-1 text-right num ${(p.unrealized_pnl || 0) >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
                        {inr(p.unrealized_pnl)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!has ? (
        <Empty>no trades booked yet — the forward loop books P&amp;L here as positions close.</Empty>
      ) : (
        <>
          <Breakdown title="By market" rows={classes} head="Market" label={(k) => CLS[k] || k} />
          <Breakdown title="By strategy" rows={strats} head="Strategy" label={(k) => k} />
        </>
      )}

      {trades.length > 0 && (
        <div className="mt-1">
          <div className="text-[10px] uppercase text-muted-foreground mb-1">Recent booked trades</div>
          <div className="space-y-0.5">
            {trades.slice(0, 8).map((x: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-[11px]">
                <span className="text-muted-foreground num w-[64px] shrink-0">{fmt.time(x.ts)}</span>
                <Chip tone={x.side === "buy" ? "up" : "down"}>{x.side}</Chip>
                <span className="font-medium truncate">{x.symbol}</span>
                {x.strategy && <span className="text-muted-foreground truncate">{x.strategy}</span>}
                <span className={`num ml-auto shrink-0 ${x.realized_pnl >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>
                  {inr(x.realized_pnl)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-3">
        Separate paper-forward book on :8001 — your live AngelOne monitor is unaffected. P&amp;L is
        REAL realized profit/loss from the strategies on real data, not a forecast.
      </p>
    </Panel>
  );
}

function Sparkline({ pts }: { pts: number[] }) {
  if (pts.length < 2) return null;
  const w = 300, h = 26;
  const min = Math.min(...pts), max = Math.max(...pts), rng = max - min || 1;
  const d = pts.map((p, i) => `${(i / (pts.length - 1)) * w},${h - ((p - min) / rng) * h}`).join(" ");
  const up = pts[pts.length - 1] >= pts[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-6 mt-1.5" preserveAspectRatio="none">
      <polyline points={d} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Stat({ k, v, tone }: { k: string; v: string; tone?: "up" | "down" }) {
  return (
    <div className="bg-secondary/20 border border-border rounded px-2 py-1.5">
      <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
      <div className={`num text-[13px] ${tone === "up" ? "text-[color:var(--up)]" : tone === "down" ? "text-[color:var(--down)]" : ""}`}>{v}</div>
    </div>
  );
}

function Breakdown({ title, rows, head, label }: { title: string; rows: any[]; head: string; label: (k: string) => string }) {
  if (!rows.length) return null;
  return (
    <div className="mb-3">
      <div className="text-[10px] uppercase text-muted-foreground mb-1">{title}</div>
      <div className="overflow-hidden rounded-md border border-border">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="bg-secondary/30 text-muted-foreground text-[9px] uppercase tracking-wide">
              <th className="text-left font-medium px-2 py-1">{head}</th>
              <th className="text-right font-medium px-2 py-1">Trades</th>
              <th className="text-right font-medium px-2 py-1">Win</th>
              <th className="text-right font-medium px-2 py-1">Profit</th>
              <th className="text-right font-medium px-2 py-1">Loss</th>
              <th className="text-right font-medium px-2 py-1">Net</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any) => (
              <tr key={r.key} className="border-t border-border/50">
                <td className="px-2 py-1">{label(r.key)}</td>
                <td className="px-2 py-1 text-right num">{r.trades}</td>
                <td className="px-2 py-1 text-right num">{Math.round((r.win_rate || 0) * 100)}%</td>
                <td className="px-2 py-1 text-right num text-[color:var(--up)]">{inr(r.profit)}</td>
                <td className="px-2 py-1 text-right num text-[color:var(--down)]">{inr(r.loss)}</td>
                <td className={`px-2 py-1 text-right num ${r.net >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{inr(r.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
