import { useEffect, useRef } from "react";
import { createChart, ColorType, CandlestickSeries, HistogramSeries, type IChartApi } from "lightweight-charts";

export function CandleChart({ candles }: { candles: Array<{ ts: number; open: number; high: number; low: number; close: number; volume: number }> }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#a5b4cf", fontFamily: "JetBrains Mono, monospace" },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)", timeVisible: true },
      crosshair: { mode: 1 },
      width: ref.current.clientWidth,
      height: ref.current.clientHeight,
    });
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981", downColor: "#f43f5e", borderUpColor: "#10b981", borderDownColor: "#f43f5e",
      wickUpColor: "#10b981", wickDownColor: "#f43f5e",
    });
    const volSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "",
    });
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth, height: ref.current.clientHeight });
    });
    ro.observe(ref.current);

    const data = (candles || []).map((c) => ({ time: (typeof c.ts === "number" ? (c.ts > 1e12 ? Math.floor(c.ts / 1000) : c.ts) : Math.floor(new Date(c.ts).getTime() / 1000)) as any, open: c.open, high: c.high, low: c.low, close: c.close }));
    const vol = (candles || []).map((c) => ({ time: (typeof c.ts === "number" ? (c.ts > 1e12 ? Math.floor(c.ts / 1000) : c.ts) : Math.floor(new Date(c.ts).getTime() / 1000)) as any, value: c.volume, color: c.close >= c.open ? "rgba(16,185,129,0.4)" : "rgba(244,63,94,0.4)" }));
    candleSeries.setData(data);
    volSeries.setData(vol);
    chart.timeScale().fitContent();

    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; };
  }, [candles]);

  return <div ref={ref} className="w-full h-full min-h-[320px]" />;
}
