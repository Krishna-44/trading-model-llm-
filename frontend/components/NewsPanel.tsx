"use client";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { stanceColor, timeAgo } from "@/lib/format";

function sentBorder(s: string) {
  return s === "bullish" ? "border-l-long" : s === "bearish" ? "border-l-short" : "border-l-zinc-600";
}
const short = (s: string) => s.replace(".NS", "").replace("-USD", "").replace("=X", "").replace("^", "");

export function NewsPanel({ data, symbol }: { data?: any; symbol: string }) {
  const heads: any[] = data?.headlines ?? [];
  const agg = data?.aggregate;
  const top = heads[0]?.title;
  const [similar, setSimilar] = useState<any>();

  useEffect(() => {
    if (top) api.newsSimilar(symbol, top).then(setSimilar).catch(() => setSimilar(undefined));
    else setSimilar(undefined);
  }, [symbol, top]);

  const echoes: any[] = similar?.matches ?? [];

  return (
    <div className="panel-pad flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="label">News Intelligence · {symbol}</span>
        {agg && (
          <span className={`chip border-white/10 ${stanceColor(agg.sentiment)}`}>
            {agg.sentiment} · {agg.bullish}↑/{agg.bearish}↓ · impact {agg.avg_impact}
          </span>
        )}
      </div>

      <div className="-mr-1 max-h-[260px] space-y-1.5 overflow-y-auto pr-1">
        {heads.length === 0 && (
          <div className="py-6 text-center text-xs text-zinc-600">no live headlines for {symbol}</div>
        )}
        {heads.map((h, i) => (
          <a key={i} href={h.link || "#"} target="_blank" rel="noreferrer"
             className={`block rounded-md border border-white/[0.06] border-l-2 bg-white/[0.02] px-2.5 py-1.5 transition hover:bg-white/[0.04] ${sentBorder(h.sentiment)}`}>
            <div className="flex items-start justify-between gap-2">
              <span className="text-[12px] leading-snug text-zinc-200">{h.title}</span>
              <span className={`num shrink-0 text-[10px] ${stanceColor(h.sentiment)}`}>{(h.impact_score * 100).toFixed(0)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-500">
              <span className="truncate">{h.publisher || "—"}</span>
              <span className="num shrink-0">{h.ts ? timeAgo(new Date(h.ts * 1000).toISOString()) : ""}</span>
            </div>
          </a>
        ))}
      </div>

      {echoes.length > 0 && (
        <div className="border-t border-white/[0.06] pt-2">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-accent-soft">Historical echoes</span>
            <span className="text-[10px] text-zinc-600">{similar?.memory?.events ?? 0} events in memory</span>
          </div>
          <div className="space-y-1">
            {echoes.map((m, i) => (
              <div key={i} className="flex items-center gap-2 text-[11px]">
                <span className="num text-zinc-500">{short(m.symbol)}</span>
                <span className="truncate text-zinc-400">{m.title}</span>
                <span className="num ml-auto shrink-0 text-zinc-600">{(m.similarity * 100).toFixed(0)}%</span>
                <span className={`num shrink-0 ${m.forward_return_5d == null ? "text-zinc-600" : m.forward_return_5d >= 0 ? "text-long-soft" : "text-short-soft"}`}>
                  {m.forward_return_5d == null ? "—" : `${(m.forward_return_5d * 100).toFixed(1)}%`}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-1 text-[10px] italic text-zinc-600">5-day realized move after similar past events (— = not yet resolvable)</p>
        </div>
      )}
    </div>
  );
}
