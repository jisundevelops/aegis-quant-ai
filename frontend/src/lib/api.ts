/**
 * API client for the Aegis Quant AI backend.
 *
 * Uses RELATIVE URLs (/api/*) so all requests go through the Next.js
 * rewrite proxy (see next.config.js). The proxy forwards /api/* to
 * NEXT_PUBLIC_API_URL (set on Vercel) or http://localhost:8000 (in dev).
 *
 * Benefits of the rewrite proxy approach:
 *   1. No CORS issues — browser only sees same-origin requests
 *   2. Backend URL is not exposed to the client
 *   3. Works even if backend URL changes (just update env var)
 *
 * Types match the actual backend response schemas (Phase 6 + 7).
 */

// ── Types ─────────────────────────────────────────────────────────────────────

export type Bias = "Bullish" | "Bearish" | "Neutral";
export type Direction = "LONG" | "SHORT" | "NEUTRAL";

export interface AgentBreakdown {
  bias: Bias;
  confidence: number;
  weight: number;
  weighted_contribution: number;
  reasoning: string;
}

export interface ScenarioProbabilities {
  bull_pct: number;
  bear_pct: number;
  range_pct: number;
  sum_pct: number;
  contributions: Record<string, unknown>;
  explanation: string;
}

export interface TradePlan {
  entry?: number;
  stop_loss?: number;
  take_profit_1?: number;
  take_profit_2?: number;
  position_size?: number;
  risk_per_unit?: number;
  risk_reward_ratio?: number;
  trade_safety_score?: number;
  [key: string]: unknown;
}

export interface AnalyzeResponse {
  symbol: string;
  timeframe: string;
  direction: Direction;
  entry_zone: number[] | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  risk_score: number;
  confidence_score: number;
  reasoning: string;
  agent_breakdown: Record<string, AgentBreakdown>;
  probabilities: ScenarioProbabilities;
  trade_plan: TradePlan | null;
  timestamp: string;
}

export interface AnalyzeRequest {
  symbol: string;
  timeframe: string;
  limit?: number;
  capital?: number;
  use_feature_cache?: boolean;
}

export interface BacktestRequest {
  symbol: string;
  timeframe: string;
  start: string;
  end: string;
  limit?: number;
  initial_capital?: number;
  commission_bps?: number;
  slippage_bps?: number;
  save_to_db?: boolean;
}

export interface BacktestMetrics {
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown: number;
  expectancy: number;
  total_return: number;
  final_equity: number;
}

export interface BiasWarning {
  bias_type: string;
  severity: string;
  message: string;
  details: Record<string, unknown>;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  direction: string;
  entry: number;
  exit: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  size: number;
  pnl: number;
  return_pct: number;
  exit_reason: string;
  bars_held: number;
}

export interface BacktestResponse {
  name: string;
  symbol: string;
  timeframe: string;
  start_date: string | null;
  end_date: string | null;
  generated_at: string;
  metrics: BacktestMetrics;
  bias_report: BiasWarning[];
  config: Record<string, unknown>;
  total_trades: number;
  total_signals: number;
  equity_curve: EquityPoint[];
  trades: BacktestTrade[];
}

export interface JournalEntry {
  id: number;
  symbol: string;
  entry: number;
  exit: number | null;
  pnl: number | null;
  notes: string;
  timestamp: string;
}

// ── Functions ─────────────────────────────────────────────────────────────────
// All calls use RELATIVE URLs (/api/*) — proxied by next.config.js rewrites

export async function postAnalyze(
  payload: AnalyzeRequest
): Promise<AnalyzeResponse> {
  const res = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Analyze failed (${res.status}): ${err}`);
  }
  return res.json();
}

export async function postBacktest(
  payload: BacktestRequest
): Promise<BacktestResponse> {
  const res = await fetch("/api/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Backtest failed (${res.status}): ${err}`);
  }
  return res.json();
}

export async function getJournal(): Promise<JournalEntry[]> {
  try {
    const res = await fetch("/api/journal");
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getHealth(): Promise<{ status: string }> {
  const res = await fetch("/api/health");
  return res.json();
}

export const api = {
  get: async (endpoint: string) => {
    const res = await fetch(endpoint);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },
  post: async (endpoint: string, body: unknown) => {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },
};

export default api;
