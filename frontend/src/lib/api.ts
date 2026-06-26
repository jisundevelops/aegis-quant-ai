const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://aegis-quant-ai.onrender.com';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AgentData {
  signal: string;
  confidence: number;
  reasoning: string;
}

export interface AnalyzeResponse {
  symbol: string;
  timeframe: string;
  conviction_score: number;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  probabilities: {
    bull: number;
    bear: number;
    range: number;
  };
  agent_breakdown: Record<string, AgentData>;
  risk: {
    entry: number;
    stop_loss: number;
    take_profit: number;
    position_size: number;
  };
  timestamp: string;
}

export interface AnalyzeRequest {
  symbol: string;
  timeframe: string;
  limit?: number;
}

// ── Functions ─────────────────────────────────────────────────────────────────

export async function postAnalyze(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Analyze failed: ${res.status}`);
  return res.json();
}

export const api = {
  get: async (endpoint: string) => {
    const res = await fetch(`${API_BASE_URL}${endpoint}`);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },
  post: async (endpoint: string, body: unknown) => {
    const res = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },
};

export default api;
