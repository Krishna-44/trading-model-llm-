import { useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { api, fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const inr = (v: number | null | undefined, d = 0) =>
  v == null || !Number.isFinite(v) ? "—" : `₹${fmt.n(v, d)}`;
const pnl = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : "−"}₹${fmt.n(Math.abs(v))}`;
const biasTone = (b?: string) =>
  b === "bullish" ? "up" : b === "bearish" ? "down" : b === "range" ? "indigo" : "cyan";

/** Paper Options Lab — practise strategies with virtual money. Premiums are
 *  Black–Scholes model prices (no live option feed), clearly a simulation. */
export function OptionsLab({ symbol }: { symbol: string }) {
  const [days, setDays] = useState(7);
  const [lots, setLots] = useState(1);
  const [busy, setBusy] = useState("");

  const { data: s } = useApi<any>(`/api/options/strategies?symbol=${encodeURIComponent(symbol)}&days=${days}`,
    { deps: [symbol, days], pollMs: 30000 });
  const { data: book, refetch } = useApi<any>("/api/options/paper", { pollMs: 6000 });

  const open = async (strategy: string) => {
    setBusy(strategy);
    try { await api("/api/options/paper/open", { method: "POST", body: JSON.stringify({ symbol, strategy, days, lots }) }); refetch(); }
    finally { setBusy(""); }
  };
  const close = async (id: number) => { try { await api("/api/options/paper/close", { method: "POST", body: JSON.stringify({ id }) }); refetch(); } catch {} };

  const strategies: any[] = s?.strategies || [];
  const positions: any[] = book?.positions || [];

  return (
    <Panel
      title="Options Lab · paper"
      subtitle={s ? `${symbol} · spot ${fmt.n(s.spot)} · model-priced (IV≈${(s.vol * 100).toFixed(0)}%) · lot ${s.lot_size}` : `${symbol} · loading…`}
      right={
        <div className="flex items-center gap-1.5">
          <select value={days} onChange={(e) => setDays(+e.target.value)} className="bg-secondary/60 border border-border rounded px-1.5 py-0.5 text-[11px] num">
            {[7, 14, 30].map((d) => <option key={d} value={d}>{d}d exp</option>)}
          </select>
          <input type="number" min={1} max={50} value={lots} onChange={(e) => setLots(Math.max(1, +e.target.value || 1))}
            className="w-12 bg-secondary/60 border border-border rounded px-1.5 py-0.5 text-[11px] num" title="lots" />
        </div>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-3">
        {strategies.map((st) => (
          <div key={st.strategy} className="bg-secondary/20 border border-border rounded-md p-2.5 flex flex-col">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[12px] font-medium">{st.label}</span>
              <Chip tone={biasTone(st.bias)}>{st.bias}</Chip>
            </div>
            <p className="text-[10px] text-muted-foreground leading-snug mb-2 min-h-[28px]">{st.desc}</p>
            <div className="text-[11px] num space-y-0.5 mb-2">
              <Row k={st.net_premium >= 0 ? "Debit (pay)" : "Credit (get)"} v={inr(Math.abs(st.net_premium))} />
              <Row k="Max profit" v={st.max_profit === "unlimited" ? "unlimited" : inr(st.max_profit)} tone="up" />
              <Row k="Max loss" v={inr(st.max_loss)} tone="down" />
              <Row k="Breakeven" v={(st.breakevens || []).map((b: number) => fmt.n(b)).join(" / ") || "—"} />
            </div>
            <button onClick={() => open(st.strategy)} disabled={!!busy}
              className="mt-auto chip border-[color:var(--cyan)]/40 text-[color:var(--cyan)] hover:bg-[color:var(--cyan)]/10 disabled:opacity-50 justify-center">
              {busy === st.strategy ? "opening…" : "Open (paper)"}
            </button>
          </div>
        ))}
      </div>

      <div className="text-[10px] uppercase text-muted-foreground mb-1">Open paper positions · {positions.length}</div>
      {positions.length === 0 ? (
        <Empty>No paper option positions yet — open a strategy above to practise.</Empty>
      ) : (
        <div className="space-y-1">
          {positions.map((p) => (
            <div key={p.id} className="flex items-center gap-2 text-[11px] bg-secondary/20 border border-border rounded px-2 py-1.5">
              <span className="font-medium">{p.label}</span>
              <span className="text-muted-foreground num">{p.symbol} · {p.days_left}d left</span>
              <span className={`num font-semibold ${p.pnl >= 0 ? "text-[color:var(--up)]" : "text-[color:var(--down)]"}`}>{pnl(p.pnl)}</span>
              <button onClick={() => close(p.id)} className="ml-auto chip border-border/60 text-muted-foreground hover:text-foreground">Close</button>
            </div>
          ))}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-3">
        Black–Scholes model prices (IV proxied by realised volatility) — a paper learning sandbox, not live option quotes.
        Positions are session-only (reset on backend restart).
      </p>
    </Panel>
  );
}

function Row({ k, v, tone }: { k: string; v: string; tone?: "up" | "down" }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{k}</span>
      <span className={tone === "up" ? "text-[color:var(--up)]" : tone === "down" ? "text-[color:var(--down)]" : ""}>{v}</span>
    </div>
  );
}
