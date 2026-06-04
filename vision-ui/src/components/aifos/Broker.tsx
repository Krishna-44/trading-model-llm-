import { useApi } from "@/lib/aifos/useFetch";
import { fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty, Dot } from "./Panel";

const inr = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `₹${fmt.n(v)}`;

/** Broker connection status — real account funds/positions + the order-arming
 *  locks. Read from /api/broker; never places an order. */
export function BrokerPanel() {
  const { data: b } = useApi<any>("/api/broker", { pollMs: 8000 });
  if (!b) return <Panel title="Broker"><Empty>backend offline</Empty></Panel>;

  const armed: boolean = !!b.orders_armed;
  const modeLabel = !b.is_live ? "PAPER" : b.monitor_only ? `${String(b.broker).toUpperCase()} · MONITOR` : "LIVE";
  const modeTone: "cyan" | "indigo" | "down" = !b.is_live ? "cyan" : b.monitor_only ? "indigo" : "down";

  return (
    <Panel
      title="Broker"
      subtitle={b.is_live ? `${b.broker} · real account` : "paper simulator"}
      right={<Chip tone={modeTone}>{modeLabel}</Chip>}
    >
      <div className="flex items-center gap-2 text-[12px] mb-3">
        <Dot on={b.connected} color={b.connected ? "emerald" : "rose"} />
        <span className={b.connected ? "text-[color:var(--up)]" : "text-muted-foreground"}>
          {b.connected ? "Connected" : b.is_live ? "Not connected" : "Paper mode"}
        </span>
      </div>

      {b.is_live && b.connected && b.funds && (
        <div className="grid grid-cols-2 gap-2 text-[11px] mb-3">
          <Stat k="Available funds" v={inr(b.funds.cash)} />
          <Stat k="Equity (incl. holdings)" v={inr(b.funds.equity)} />
          <Stat k="Open positions" v={String(b.positions ?? 0)} />
          <Stat k="Currency" v={b.funds.currency || "INR"} />
        </div>
      )}
      {b.error && <p className="text-[11px] text-[color:var(--down)] mb-2">⚠ {b.error}</p>}

      <div className="text-[10px] uppercase text-muted-foreground mb-1">Real orders</div>
      <div className={`text-[12px] font-semibold mb-2 ${armed ? "text-[color:var(--down)]" : "text-[color:var(--up)]"}`}>
        {armed ? "⚠ ARMED — real orders enabled" : "🔒 BLOCKED — no real orders"}
      </div>
      <div className="space-y-1 text-[11px]">
        <Lock label="Monitor-only turned off" ok={!b.monitor_only} />
        <Lock label="Live trading enabled" ok={!!b.live_trading_enabled} />
      </div>
      <p className="text-[10px] text-muted-foreground/70 italic mt-2">
        Even when armed, orders only fire after go-live readiness passes (see the “Trained?” strip).
      </p>
      {!b.is_live && (
        <p className="text-[10px] text-muted-foreground/70 italic mt-1">
          Set broker + creds in <span className="num">backend/.env</span> to connect AngelOne (read-only).
        </p>
      )}
    </Panel>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-secondary/30 border border-border rounded-md px-2 py-1.5">
      <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
      <div className="num text-xs">{v}</div>
    </div>
  );
}

function Lock({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-[color:var(--down)]" : "bg-[color:var(--up)]"}`} />
      <span className="text-muted-foreground">{label}</span>
      <span className={`ml-auto num text-[10px] ${ok ? "text-[color:var(--down)]" : "text-[color:var(--up)]"}`}>{ok ? "yes" : "locked"}</span>
    </div>
  );
}
