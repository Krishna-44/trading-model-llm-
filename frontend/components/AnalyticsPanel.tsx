"use client";
import { money, num, pct, signColor } from "@/lib/format";

interface Analytics {
  live: Record<string, number | string>;
  strategies: any[];
}

const tone = (v: number) => (v > 0 ? "text-long-soft" : v < 0 ? "text-short-soft" : "text-zinc-400");

export function AnalyticsPanel({ data, ccy }: { data?: Analytics; ccy: string }) {
  const live = data?.live ?? {};
  const strategies = data?.strategies ?? [];
  const closed = Number(live.closed_trades ?? 0);

  return (
    <div className="panel-pad flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="label">Performance Analytics</span>
        <span className="chip border-white/10 text-zinc-500">transparent · auditable</span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* live account */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-[11px] text-zinc-500">
            <span>Live account (paper)</span>
            <span className="num">{closed} closed trades</span>
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            <Stat k="Sharpe" v={num(Number(live.sharpe ?? 0), 2)} />
            <Stat k="Sortino" v={num(Number(live.sortino ?? 0), 2)} />
            <Stat k="Max DD" v={pct(Number(live.max_drawdown ?? 0))} tone={tone(Number(live.max_drawdown ?? 0))} />
            <Stat k="Profit factor" v={num(Number(live.profit_factor ?? 0), 2)} />
            <Stat k="Win rate" v={pct(Number(live.win_rate ?? 0), 0)} />
            <Stat k="Expectancy" v={num(Number(live.expectancy ?? 0), 0)} tone={tone(Number(live.expectancy ?? 0))} />
            <Stat k="Daily P&L" v={money(Number(live.daily_pnl ?? 0), ccy)} tone={tone(Number(live.daily_pnl ?? 0))} />
            <Stat k="Weekly P&L" v={money(Number(live.weekly_pnl ?? 0), ccy)} tone={tone(Number(live.weekly_pnl ?? 0))} />
            <Stat k="Monthly P&L" v={money(Number(live.monthly_pnl ?? 0), ccy)} tone={tone(Number(live.monthly_pnl ?? 0))} />
          </div>
          {live.note ? <p className="text-[11px] italic text-zinc-600">{String(live.note)}</p> : null}
        </div>

        {/* strategy comparison */}
        <div className="flex flex-col gap-2">
          <span className="text-[11px] text-zinc-500">Strategy comparison (backtested, this symbol)</span>
          <div className="overflow-hidden rounded-lg border border-white/[0.06]">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-wide text-zinc-500">
                  <th className="px-2 py-1.5 text-left font-medium">Strategy</th>
                  <th className="px-2 py-1.5 text-right font-medium">Return</th>
                  <th className="px-2 py-1.5 text-right font-medium">Sharpe</th>
                  <th className="px-2 py-1.5 text-right font-medium">Max DD</th>
                  <th className="px-2 py-1.5 text-right font-medium">Win</th>
                  <th className="px-2 py-1.5 text-right font-medium">PF</th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((s) => (
                  <tr key={s.strategy} className="border-b border-white/[0.03] last:border-0">
                    <td className="px-2 py-1.5 font-medium text-zinc-200">{s.strategy}</td>
                    {s.error ? (
                      <td className="px-2 py-1.5 text-right text-zinc-600" colSpan={5}>—</td>
                    ) : (
                      <>
                        <td className={`num px-2 py-1.5 text-right ${tone(s.total_return)}`}>{pct(s.total_return)}</td>
                        <td className={`num px-2 py-1.5 text-right ${tone(s.sharpe)}`}>{num(s.sharpe, 2)}</td>
                        <td className="num px-2 py-1.5 text-right text-short-soft">{pct(s.max_drawdown)}</td>
                        <td className="num px-2 py-1.5 text-right text-zinc-300">{pct(s.win_rate, 0)}</td>
                        <td className={`num px-2 py-1.5 text-right ${s.profit_factor >= 1 ? "text-long-soft" : "text-short-soft"}`}>{num(s.profit_factor, 2)}</td>
                      </>
                    )}
                  </tr>
                ))}
                {strategies.length === 0 && (
                  <tr><td className="px-2 py-3 text-center text-zinc-600" colSpan={6}>run analysis to populate</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] italic text-zinc-600">
            Backtested net of costs + slippage, no look-ahead. Past performance ≠ future results.
          </p>
        </div>
      </div>
    </div>
  );
}

function Stat({ k, v, tone = "text-zinc-200" }: { k: string; v: string; tone?: string }) {
  return (
    <div className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-zinc-500">{k}</div>
      <div className={`num text-xs ${tone}`}>{v}</div>
    </div>
  );
}
