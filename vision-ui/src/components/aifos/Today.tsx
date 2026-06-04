import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const inr = (v: number | null | undefined, d = 0) =>
  v == null || !Number.isFinite(v) ? "—" : `₹${fmt.n(v, d)}`;

/** Today's booked P&L (IST trading day) + how much of the wallet is deployed. */
export function TodayPanel() {
  const { data: t } = useApi<any>("/api/today", { pollMs: 8000 });
  if (!t) return <Panel title="Today"><Empty>backend offline</Empty></Panel>;

  const booked = t.booked_today ?? 0;
  return (
    <Panel
      title="Today"
      subtitle={`booked P&L · ${t.date || "—"} · IST trading day`}
      right={<Chip tone={booked >= 0 ? "up" : "down"}>{(booked >= 0 ? "+" : "") + inr(booked)}</Chip>}
    >
      <table className="w-full text-[12px]">
        <tbody>
          <Row k="Profit booked today" v={inr(t.profit_today)} tone="up" />
          <Row k="Loss booked today" v={inr(t.loss_today_abs)} tone="down" />
          <Row k="Net booked today" v={inr(booked)} tone={booked >= 0 ? "up" : "down"} strong />
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
