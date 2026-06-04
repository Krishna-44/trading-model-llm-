"use client";
import type { Config, RiskSnapshot } from "@/lib/types";

export function Header({
  config, risk, connected, onKill, onResume, onToggleAuto,
}: {
  config?: Config;
  risk?: RiskSnapshot;
  connected: boolean;
  onKill: () => void;
  onResume: () => void;
  onToggleAuto: () => void;
}) {
  const live = config?.mode === "live";
  const halted = risk?.kill_switch_active;
  const auto = risk?.autonomous;

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] px-5 py-3">
      <div className="flex items-center gap-3">
        <div className="relative grid h-9 w-9 place-items-center rounded-xl border border-accent/30 bg-accent/10">
          <span className="absolute inset-0 animate-pulseGlow rounded-xl shadow-glow" />
          <span className="num text-sm font-bold text-accent-soft">Λ</span>
        </div>
        <div>
          <h1 className="text-[15px] font-semibold tracking-tight text-zinc-100">
            AIFOS <span className="text-zinc-500">/ Financial Operating System</span>
          </h1>
          <p className="text-[11px] text-zinc-500">Protect capital first · default action is HOLD</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Status ok={connected} on="streaming" off="offline" />
        <span className={`chip ${live ? "border-short/40 bg-short/10 text-short-soft" : "border-accent/30 bg-accent/10 text-accent-soft"}`}>
          {live ? "● LIVE" : "◇ PAPER"}
        </span>
        <span className={`chip border-white/10 ${config?.llm.available ? "text-long-soft" : "text-zinc-500"}`}>
          LLM {config?.llm.available ? "on" : "off"}
        </span>

        <button onClick={onToggleAuto} className={`btn ${auto ? "btn-accent" : ""}`}>
          {auto ? "◉ Autonomous" : "○ Autonomous"}
        </button>

        {halted ? (
          <button onClick={onResume} className="btn btn-accent">Resume</button>
        ) : (
          <button onClick={onKill} className="btn btn-danger">⛔ Kill Switch</button>
        )}
      </div>
    </header>
  );
}

function Status({ ok, on, off }: { ok: boolean; on: string; off: string }) {
  return (
    <span className="chip border-white/10 text-zinc-400">
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-long animate-pulseGlow" : "bg-zinc-600"}`} />
      {ok ? on : off}
    </span>
  );
}
