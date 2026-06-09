import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Header, ControlBar, NewsTicker } from "@/components/aifos/Shell";
import { ChartPanel, useAnalyze } from "@/components/aifos/Analysis";
import { NewsIntel } from "@/components/aifos/News";
import { HoldingsPanel } from "@/components/aifos/Holdings";
import { BrokerPanel } from "@/components/aifos/Broker";
import { StrategyMarket } from "@/components/aifos/StrategyMarket";
import { PaperTrading } from "@/components/aifos/PaperTrading";
import { Robustness } from "@/components/aifos/Robustness";
import { Cooking } from "@/components/aifos/Cooking";
import { TradeLog } from "@/components/aifos/Activity";
import { TodayPanel } from "@/components/aifos/Today";
import { CandleRead } from "@/components/aifos/CandleRead";
import { StatusStrip } from "@/components/aifos/StatusStrip";
import { SessionStrip } from "@/components/aifos/SessionStrip";
import { VisionDock } from "@/components/aifos/Vision";
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

  return (
    <div className="min-h-screen">
      <Header symbol={symbol} />
      <ControlBar
        symbol={symbol} setSymbol={setSymbol}
        interval={interval} setInterval={setInterval}
        onAnalyze={() => run(symbol, interval)}
        analyzing={analyzing}
      />
      <NewsTicker />
      <StatusStrip />
      <SessionStrip />

      <main className="px-4 md:px-6 py-4 grid grid-cols-12 gap-4">
        {/* the chart being traded + today's booked P&L right beneath it */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-4">
          <div className="h-[440px]"><ChartPanel symbol={symbol} interval={interval} /></div>
          <TodayPanel />
        </div>

        {/* live news + a candlestick learning read of the chart */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-4">
          <NewsIntel symbol={symbol} />
          <CandleRead symbol={symbol} interval={interval} />
        </div>

        {/* broker connection + holdings by asset class + trade log */}
        <div className="col-span-12 lg:col-span-4"><BrokerPanel /></div>
        <div className="col-span-12 lg:col-span-8"><HoldingsPanel /></div>

        {/* paper-forward scoreboard (:8001) — booked P&L by market & strategy */}
        <div className="col-span-12"><PaperTrading /></div>

        <div className="col-span-12"><TradeLog /></div>

        {/* strategy marketplace — backtested + ranked, enable/disable */}
        <div className="col-span-12 lg:col-span-7"><StrategyMarket symbol={symbol} /></div>

        {/* robustness · Monte Carlo enforcement (forward instance) */}
        <div className="col-span-12 lg:col-span-5"><Robustness symbol={symbol} /></div>

        {/* strategies cooking — continuous background discovery on :8001 */}
        <div className="col-span-12"><Cooking /></div>
      </main>

      <footer className="px-4 md:px-6 py-4 border-t border-border bg-background/60 backdrop-blur-md mt-4 mb-24">
        <div className="flex items-center gap-2 max-w-4xl mx-auto text-[11px] text-muted-foreground">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span>Paper-first · live execution gated · not investment advice.</span>
        </div>
      </footer>

      <VisionDock />
    </div>
  );
}
