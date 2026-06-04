"use client";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

function Chips({ items }: { items?: string[] }) {
  if (!items || items.length === 0) return <span className="text-[11px] text-zinc-600">none detected</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((x) => (
        <span key={x} className="chip border-white/10 text-[10px] text-zinc-300">{x}</span>
      ))}
    </div>
  );
}

export function LabPanel({ symbol }: { symbol: string }) {
  const [channels, setChannels] = useState<string[]>([]);
  const [alertMsg, setAlertMsg] = useState("");
  const [url, setUrl] = useState("");
  const [video, setVideo] = useState<any>();
  const [videoBusy, setVideoBusy] = useState(false);
  const [rl, setRl] = useState<any>();
  const [rlBusy, setRlBusy] = useState(false);

  useEffect(() => {
    api.alertsStatus().then((s) => setChannels(s.channels)).catch(() => {});
    api.rlStatus().then(setRl).catch(() => {});
  }, []);

  const testAlert = async () => {
    const r = await api.alertsTest().catch(() => null);
    setAlertMsg(r ? (r.sent.length ? `sent to: ${r.sent.join(", ")}` : "no channels configured") : "failed");
  };
  const learn = async () => {
    if (!url) return;
    setVideoBusy(true);
    setVideo(undefined);
    try { setVideo(await api.learnVideo(url)); } finally { setVideoBusy(false); }
  };
  const train = async () => {
    setRlBusy(true);
    try { setRl(await api.rlTrain(symbol)); } finally { setRlBusy(false); }
  };

  return (
    <div className="panel-pad flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="label">AI Lab — Learning · Alerts · RL</span>
        <span className="chip border-white/10 text-zinc-500">seed</span>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {/* alerts */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="mb-2 text-xs font-medium text-zinc-300">External Alerts</div>
          <div className="mb-2 flex flex-wrap gap-1">
            {channels.length ? channels.map((c) => (
              <span key={c} className="chip border-long/30 text-long-soft">{c}</span>
            )) : <span className="text-[11px] text-zinc-600">no channels — set Telegram/Discord in .env</span>}
          </div>
          <button onClick={testAlert} className="btn w-full">Send test alert</button>
          {alertMsg && <p className="mt-1.5 text-[11px] text-zinc-500">{alertMsg}</p>}
        </div>

        {/* video learning */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="mb-2 text-xs font-medium text-zinc-300">Video Learning</div>
          <div className="flex gap-1.5">
            <input
              value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder="YouTube URL…"
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-ink-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-accent/40"
            />
            <button onClick={learn} disabled={videoBusy} className="btn btn-accent shrink-0">
              {videoBusy ? "…" : "Learn"}
            </button>
          </div>
          {video && (
            <div className="mt-2 space-y-1.5 text-[11px]">
              {video.error ? (
                <p className="text-short-soft">{video.error}</p>
              ) : (
                <>
                  <div className="text-zinc-500">{video.length_chars} chars · {video.strategy?.method}</div>
                  <div className="text-zinc-500">indicators</div>
                  <Chips items={video.strategy?.indicators} />
                  <div className="text-zinc-500">entries / exits</div>
                  <Chips items={[...(video.strategy?.entry_rules || []), ...(video.strategy?.exit_rules || [])]} />
                </>
              )}
            </div>
          )}
        </div>

        {/* RL search */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-300">RL Strategy Search</span>
            <span className={`chip ${rl?.deps_installed ? "border-long/30 text-long-soft" : "border-white/10 text-zinc-500"}`}>
              {rl?.deps_installed ? "ready" : "deps off"}
            </span>
          </div>
          <p className="mb-2 text-[11px] leading-snug text-zinc-500">{rl?.reward ?? rl?.note ?? "PPO · survival-weighted reward"}</p>
          <button onClick={train} disabled={rlBusy} className="btn w-full">
            {rlBusy ? "running env…" : `Train on ${symbol}`}
          </button>
          {rl?.status && (
            <p className="mt-1.5 text-[11px] text-zinc-500">
              {rl.status === "trained"
                ? `trained · policy equity ${rl.final_equity} vs buy&hold ${rl.buy_hold_equity}`
                : `${rl.status} · env ran (random reward ${rl.random_policy_reward ?? "—"})`}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
