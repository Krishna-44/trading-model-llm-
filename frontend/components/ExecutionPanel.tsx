"use client";

function Dot({ ok }: { ok: boolean }) {
  return <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-long animate-pulseGlow" : "bg-short"}`} />;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-xs">
      <span className="text-zinc-500">{label}</span>
      <span className="num flex items-center gap-1.5 text-zinc-200">{children}</span>
    </div>
  );
}

export function ExecutionPanel({ data }: { data?: any }) {
  const b = data?.broker, d = data?.data, l = data?.llm, c = data?.costs, o = data?.orders;
  return (
    <div className="panel-pad flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="label">Execution Engine</span>
        {data && (
          <span className={`chip ${data.kill_switch ? "border-short/40 text-short-soft" : "border-long/30 text-long-soft"}`}>
            {data.kill_switch ? "halted" : "operational"}
          </span>
        )}
      </div>
      {!data ? (
        <div className="py-6 text-center text-xs text-zinc-600">loading…</div>
      ) : (
        <div className="grid grid-cols-1 gap-1.5">
          <Row label="Broker"><Dot ok={b.connected} />{b.name} · {b.mode}</Row>
          <Row label="Live gate"><Dot ok={!b.live_gate} />{b.live_gate ? "ARMED" : "off (paper)"}</Row>
          <Row label="Data feed"><Dot ok={d.ok} />{d.provider} · {d.source}</Row>
          <Row label="Data latency">{d.latency_ms} ms</Row>
          <Row label="LLM"><Dot ok={l.available} />{l.provider} {l.available ? "" : "(off)"}</Row>
          <Row label="Slippage model">{c.slippage_bps} bps</Row>
          <Row label="Commission">{c.commission_bps} bps</Row>
          <Row label="Orders / failed">{o.total} / {o.failed}</Row>
          <Row label="Autonomous"><Dot ok={data.autonomous} />{data.autonomous ? "on" : "off"}</Row>
        </div>
      )}
    </div>
  );
}
