import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const inr = (v: number | null | undefined, d = 0) =>
  v == null || !Number.isFinite(v) ? "—" : `₹${fmt.n(v, d)}`;
const pnl = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : "−"}₹${fmt.n(Math.abs(v))}`;

/** Today's P&L — realized (booked) + real-time floating (open positions),
 *  marked to a live ~1-min quote. Polls every 5s. */
export function TodayPanel() {
  const { data: t } = useApi<any>("/api/today", { pollMs: 5000 });
  if (!t) return <Panel title="Today"><Empty>backend offline</Empty></Panel>;

  const booked = t.booked_today ?? 0;
  const unreal = t.unrealized_pnl ?? 0;
  const live = t.live_pnl_today ?? booked;
  return (
    <Panel
      title="Today"
      subtitle={`real-time P&L · ${t.date || "—"} · IST trading day`}
      right={<Chip tone={live >= 0 ? "up" : "down"}>{pnl(live)} · live</Chip>}
    >
      <table className="w-full text-[12px]">
        <tbody>
          <Row k="Profit booked today" v={inr(t.profit_today)} tone="up" />
          <Row k="Loss booked today" v={inr(t.loss_today_abs)} tone="down" />
          <Row k="Net booked (realized)" v={pnl(booked)} tone={booked >= 0 ? "up" : "down"} />
          <Row k={`Open P&L · live (${t.open_positions ?? 0} pos)`} v={pnl(unreal)} tone={unreal >= 0 ? "up" : "down"} />
          <Row k="Live P&L today" v={pnl(live)} tone={live >= 0 ? "up" : "down"} strong />
          <Row k="Capital used (from wallet)" v={`${inr(t.deployed)} · ${(t.deployed_pct ?? 0).toFixed(1)}%`} />
          <Row k="Idle cash (safe)" v={inr(t.cash_idle)} />
          <Row k="Trades today" v={String(t.trades_today ?? 0)} />
        </tbody>
      </table>
    </Panel>
  );
}

function Row({ k, v, tone, strong }: { k: string; v: string; tone?: "up" | "down"; strong?: boolean }) {
  return (
    <tr className="border-t border-border/40 first:border-t-0">
      <td className="py-1.5 text-muted-foreground">{k}</td>
      <td className={`py-1.5 text-right num ${strong ? "font-semibold" : ""} ${tone === "up" ? "text-[color:var(--up)]" : tone === "down" ? "text-[color:var(--down)]" : ""}`}>{v}</td>
    </tr>
  );
}
