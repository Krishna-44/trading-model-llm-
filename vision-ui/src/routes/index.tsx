import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Header, ControlBar, NewsTicker } from "@/components/aifos/Shell";
import { ChartPanel, useAnalyze } from "@/components/aifos/Analysis";
import { NewsIntel } from "@/components/aifos/News";
import { HoldingsPanel } from "@/components/aifos/Holdings";
import { TradeLog } from "@/components/aifos/Activity";
import { TodayPanel } from "@/components/aifos/Today";
import { StatusStrip } from "@/components/aifos/StatusStrip";
import { VisionDock } from "@/components/aifos/Vision";
import { api } from "@/lib/aifos/api";
import { AlertTriangle } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "AIFOS — Artificial Intelligence Financial Operating System" },
      { name: "description", content: "Real-time, probability-gated AI trading dashboard. Paper-first; live execution gated." },
      { property: "og:title", content: "AIFOS — Financial Operating System" },
      { property: "og:description", content: "Hedge-fund-grade autonomous trading control panel." },
    ],
  }),
  component: Dashboard,
});

// Minimal operational view: live news · the chart being traded · today's P&L ·
// what's been bought/sold · positions & P&L. All other intelligence (committee,
// reasoning, regime, SMC, options engine, readiness, self-learning) keeps running
// in the backend — it's just not shown on this screen.
function Dashboard() {
  const [symbol, setSymbol] = useState("^NSEI");
  const [interval, setInterval] = useState("1d");
  const { analyzing, run } = useAnalyze();

  const onBacktest = async () => { try { await api(`/api/backtest`, { method: "POST", body: JSON.stringify({ symbol, interval }) }); } catch {} };
  const onCycle = async () => { try { await api(`/api/control/cycle`, { method: "POST", body: JSON.stringify({ symbol, interval }) }); } catch {} };

  return (
    <div className="min-h-screen">
      <Header symbol={symbol} />
      <ControlBar
        symbol={symbol} setSymbol={setSymbol}
        interval={interval} setInterval={setInterval}
        onAnalyze={() => run(symbol, interval)}
        onBacktest={onBacktest}
        onCycle={onCycle}
        analyzing={analyzing}
      />
      <NewsTicker />
      <StatusStrip />

      <main className="px-4 md:px-6 py-4 grid grid-cols-12 gap-4">
        {/* the chart being traded + today's booked P&L right beneath it */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-4">
          <div className="h-[440px]"><ChartPanel symbol={symbol} interval={interval} /></div>
          <TodayPanel />
        </div>

        {/* live news */}
        <div className="col-span-12 lg:col-span-4"><NewsIntel symbol={symbol} /></div>

        {/* under news: what's bought + how much is invested by asset class, and the trade log */}
        <div className="col-span-12 lg:col-span-7"><HoldingsPanel /></div>
        <div className="col-span-12 lg:col-span-5"><TradeLog /></div>
      </main>

      <footer className="px-4 md:px-6 py-6 border-t border-border bg-background/60 backdrop-blur-md mt-4 mb-24">
        <div className="flex items-start gap-3 max-w-4xl mx-auto text-[11px] text-muted-foreground">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p>
            <span className="text-foreground/90 font-semibold">AIFOS reasons in probabilities and does not guarantee profit. Paper-first; live execution is gated.</span>{" "}
            Default action is HOLD. Past performance ≠ future results. Nothing on this screen is investment advice.
          </p>
        </div>
      </footer>

      <VisionDock />
    </div>
  );
}
