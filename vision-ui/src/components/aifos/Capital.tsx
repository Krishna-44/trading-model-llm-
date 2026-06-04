import { useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { api, fmt } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const inr = (v: number | null | undefined, d = 0) =>
  v == null || !Number.isFinite(v) ? "—" : `₹${fmt.n(v, d)}`;

/**
 * Capital management — you fund and withdraw; AIFOS only deploys cash on
 * high-confidence signals, otherwise it stays uninvested and safe.
 * Paper book today; the same flow drives a real broker balance once connected.
 */
export function CapitalPanel() {
  const { data: c, refetch } = useApi<any>("/api/capital", { pollMs: 8000 });
  const [amt, setAmt] = useState("");
  const [busy, setBusy] = useState<"" | "deposit" | "withdraw">("");
  const [msg, setMsg] = useState("");

  if (!c) return <Panel title="Capital"><Empty>backend offline</Empty></Panel>;

  const act = async (kind: "deposit" | "withdraw") => {
    const amount = parseFloat(amt);
    if (!amount || amount <= 0) { setMsg("Enter a positive amount."); return; }
    setBusy(kind); setMsg("");
    try {
      const r = await api<any>(`/api/capital/${kind}`, { method: "POST", body: JSON.stringify({ amount }) });
      if (r.ok === false) { setMsg(r.error || "failed"); }
      else {
        setAmt("");
        if (kind === "withdraw" && r.withdrawn != null && r.withdrawn < amount)
          setMsg(`Withdrew ${inr(r.withdrawn)} — the rest is locked in open positions (close them to free it).`);
        refetch();
      }
    } catch (e: any) { setMsg(e?.message || "failed"); }
    finally { setBusy(""); }
  };

  const pnlUp = (c.total_pnl ?? 0) >= 0;
  return (
    <Panel
      title="Capital"
      subtitle={`${c.mode || "paper"} · you fund & withdraw · deployed only when confident`}
      right={<Chip tone={pnlUp ? "up" : "down"}>{`${pnlUp ? "+" : ""}${(c.return_pct ?? 0).toFixed(2)}%`}</Chip>}
    >
      <div className="flex items-end gap-3 mb-3">
        <div className="num text-3xl font-semibold">{inr(c.equity)}</div>
        <div className="text-[10px] text-muted-foreground mb-1.5">total · {inr(c.contributed)} net in</div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[11px] mb-3">
        <Stat k="Cash · safe" v={inr(c.cash)} tone="up" />
        <Stat k="Deployed · at risk" v={inr(c.deployed)} />
        <Stat k="Total P&L" v={inr(c.total_pnl)} tone={pnlUp ? "up" : "down"} />
      </div>

      <div className="flex gap-2 items-center">
        <input
          value={amt}
          onChange={(e) => setAmt(e.target.value)}
          inputMode="decimal"
          placeholder="amount ₹"
          className="flex-1 bg-secondary/40 border border-border rounded-md px-2.5 py-1.5 text-xs num outline-none focus:border-foreground/40"
        />
        <button
          onClick={() => act("deposit")}
          disabled={!!busy}
          className="chip border-[color:var(--up)]/40 text-[color:var(--up)] hover:bg-[color:var(--up)]/10 disabled:opacity-50"
        >
          {busy === "deposit" ? "…" : "Deposit"}
        </button>
        <button
          onClick={() => act("withdraw")}
          disabled={!!busy}
          className="chip border-border/60 text-muted-foreground hover:text-foreground hover:border-foreground/40 disabled:opacity-50"
        >
          {busy === "withdraw" ? "…" : "Withdraw"}
        </button>
      </div>
      {msg && <p className="text-[10px] text-amber-300/90 mt-2">{msg}</p>}

      <p className="text-[10px] text-muted-foreground/70 italic mt-2 leading-relaxed">
        Idle cash stays uninvested and safe — AIFOS deploys a risk-sized slice only on high-confidence signals,
        otherwise it holds. Paper book; with real money your balance lives at a regulated broker.
      </p>
    </Panel>
  );
}

function Stat({ k, v, tone }: { k: string; v: string; tone?: "up" | "down" }) {
  return (
    <div className="bg-secondary/30 border border-border rounded-md px-2 py-1.5">
      <div className="text-[9px] uppercase text-muted-foreground">{k}</div>
      <div className={`num text-xs ${tone === "up" ? "text-[color:var(--up)]" : tone === "down" ? "text-[color:var(--down)]" : ""}`}>{v}</div>
    </div>
  );
}
