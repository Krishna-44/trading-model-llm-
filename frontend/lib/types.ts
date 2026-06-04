export interface AgentOpinion {
  agent: string;
  stance: "bullish" | "bearish" | "neutral";
  confidence: number;
  weight: number;
  reasoning: string;
  signals: Record<string, unknown>;
  veto: boolean;
}

export interface Decision {
  symbol: string;
  action: "BUY" | "SELL" | "HOLD";
  side: "long" | "short" | "flat";
  confidence: number;
  reasoning: string;
  llm_summary: string;
  source: string;
  executed: boolean;
  opinions: AgentOpinion[];
  risk: Record<string, any>;
  sizing: Record<string, any>;
}

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Position {
  symbol: string;
  qty: number;
  avg_price: number;
  market_price: number;
  market_value: number;
  unrealized_pnl: number;
  side: string;
}

export interface Portfolio {
  account: { cash: number; equity: number; currency: string; realized_pnl: number };
  positions: Position[];
  equity_curve: { ts: string; equity: number; cash: number }[];
  open_positions: number;
  unrealized_pnl: number;
  mode: string;
  broker: string;
}

export interface RiskSnapshot {
  kill_switch_active: boolean;
  kill_reason: string;
  daily_pnl: number;
  daily_loss_limit: number;
  daily_loss_used_pct: number;
  trades_today: number;
  autonomous: boolean;
  memory: { count: number };
  limits: Record<string, number>;
}

export interface Config {
  universe: string[];
  default_symbol: string;
  default_interval: string;
  base_currency: string;
  broker: string;
  mode: string;
  live_trading_enabled: boolean;
  allow_offshore_forex: boolean;
  llm: { provider: string; available: boolean };
  strategies: string[];
  risk_limits: Record<string, number>;
}

export interface TradeRow {
  ts: string;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  realized_pnl: number;
  mode: string;
}

export interface Fundamentals {
  symbol: string;
  applicable: boolean;
  source: string;
  name: string;
  sector: string;
  metrics: Record<string, number | null>;
  quality_score: number;
  value_score: number;
  composite: number;
  stance: "bullish" | "bearish" | "neutral";
  confidence: number;
  reasoning: string;
}
