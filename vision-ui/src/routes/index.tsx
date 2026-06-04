import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Header, ControlBar, NewsTicker } from "@/components/aifos/Shell";
import { ChartPanel, AnalysisPanels, useAnalyze } from "@/components/aifos/Analysis";
import { Fundamentals, Heatmap } from "@/components/aifos/Market";
import { NewsIntel, ExecutionEngine } from "@/components/aifos/News";
import { PortfolioPanel, RiskEngine } from "@/components/aifos/Portfolio";
import { TrackRecord } from "@/components/aifos/TrackRecord";
import { CapitalPanel } from "@/components/aifos/Capital";
import { Deployment } from "@/components/aifos/Deployment";
import { TodayPanel } from "@/components/aifos/Today";
import { ReasoningTree } from "@/components/aifos/ReasoningTree";
import { OptionsChain } from "@/components/aifos/OptionsChain";
import { ActivityFeed, TradeLog, useActivityFeed } from "@/components/aifos/Activity";
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

function Dashboard() {
  const [symbol, setSymbol] = useState("^NSEI");
  const [interval, setInterval] = useState("1d");
  const { analysis, analyzing, run } = useAnalyze();
  const activity = useActivityFeed();

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

      <main className="px-4 md:px-6 py-4 grid grid-cols-12 gap-4">
        {/* Chart + today's booked P&L directly beneath it */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-4">
          <div className="h-[440px]"><ChartPanel symbol={symbol} interval={interval} /></div>
          <TodayPanel />
        </div>
        <div className="col-span-12 lg:col-span-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-4">
          <AnalysisPanels symbol={symbol} interval={interval} analysis={analysis} analyzing={analyzing} setAnalysis={() => {}} />
        </div>

        <div className="col-span-12 lg:col-span-5"><CapitalPanel /></div>
        <div className="col-span-12 lg:col-span-7"><TrackRecord /></div>

        <div className="col-span-12"><Deployment /></div>

        <div className="col-span-12"><ReasoningTree symbol={symbol} /></div>

        <div className="col-span-12 lg:col-span-6"><OptionsChain symbol={symbol} /></div>
        <div className="col-span-12 lg:col-span-6"><NewsIntel symbol={symbol} /></div>

        <div className="col-span-12 md:col-span-6"><Fundamentals symbol={symbol} /></div>
        <div className="col-span-12 md:col-span-6"><Heatmap /></div>

        <div className="col-span-12 lg:col-span-5"><PortfolioPanel /></div>
        <div className="col-span-12 lg:col-span-4"><RiskEngine /></div>
        <div className="col-span-12 lg:col-span-3"><ExecutionEngine /></div>

        <div className="col-span-12 lg:col-span-7"><TradeLog /></div>
        <div className="col-span-12 lg:col-span-5"><ActivityFeed items={activity} /></div>
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
