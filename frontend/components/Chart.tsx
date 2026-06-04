"use client";
import { ColorType, createChart } from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Candle } from "@/lib/types";

export function Chart({ candles, source }: { candles: Candle[]; source?: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || candles.length === 0) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)", timeVisible: false },
      crosshair: { mode: 1, vertLine: { color: "rgba(34,211,238,0.4)" }, horzLine: { color: "rgba(34,211,238,0.4)" } },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#10b981", downColor: "#f43f5e",
      borderUpColor: "#34d399", borderDownColor: "#fb7185",
      wickUpColor: "#34d399", wickDownColor: "#fb7185",
    });
    candleSeries.setData(
      candles.map((c) => ({
        time: c.ts.slice(0, 10) as any,
        open: c.open, high: c.high, low: c.low, close: c.close,
      }))
    );

    if (candles.some((c) => c.volume > 0)) {
      const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "" });
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
      vol.setData(
        candles.map((c) => ({
          time: c.ts.slice(0, 10) as any,
          value: c.volume,
          color: c.close >= c.open ? "rgba(16,185,129,0.35)" : "rgba(244,63,94,0.35)",
        }))
      );
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [candles]);

  return (
    <div className="relative h-full w-full">
      <div ref={ref} className="h-full w-full" />
      {source && (
        <span className="chip absolute right-2 top-2 border-white/10 text-zinc-500">
          <span className={source === "yfinance" ? "h-1.5 w-1.5 rounded-full bg-long" : "h-1.5 w-1.5 rounded-full bg-amber-400"} />
          {source === "yfinance" ? "live data" : source}
        </span>
      )}
    </div>
  );
}
