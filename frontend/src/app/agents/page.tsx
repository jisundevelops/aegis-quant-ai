"use client";

import { useState } from "react";
import { postAnalyze, type AnalyzeResponse } from "@/lib/api";
import AgentCard from "@/components/AgentCard";

const ASSETS = [
  { symbol: "BTCUSDT", label: "BTC" },
  { symbol: "ETHUSDT", label: "ETH" },
  { symbol: "EURUSD=X", label: "EURUSD" },
  { symbol: "XAUUSD=X", label: "XAUUSD" },
];

const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

export default function AgentsPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signal, setSignal] = useState<AnalyzeResponse | null>(null);

  async function handleAnalyze() {
    setLoading(true);
    setError(null);
    try {
      const result = await postAnalyze({ symbol, timeframe, limit: 500 });
      setSignal(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setSignal(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Agent Breakdown</h1>
        <p className="text-sm text-[var(--fg-muted)] mt-1">
          Individual outputs from each specialized agent in the Aegis pipeline.
        </p>
      </div>

      {/* Controls */}
      <div className="bg-bg-card border border-border rounded-lg p-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs text-[var(--fg-muted)] uppercase mb-1">
              Asset
            </label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-bg-tertiary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              {ASSETS.map((a) => (
                <option key={a.symbol} value={a.symbol}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--fg-muted)] uppercase mb-1">
              Timeframe
            </label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="bg-bg-tertiary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="bg-accent-primary text-bg-primary font-semibold py-2 px-6 rounded hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? "Running..." : "Run Agents"}
          </button>
        </div>
        {error && (
          <div className="mt-3 p-2 bg-bg-tertiary border border-bear rounded text-xs text-bear">
            {error}
          </div>
        )}
      </div>

      {/* Agent cards */}
      {signal && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(signal.agent_breakdown).map(([name, data]) => (
            <AgentCard key={name} name={name} data={data} />
          ))}
        </div>
      )}

      {!signal && !loading && (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center">
          <p className="text-[var(--fg-muted)]">
            Run an analysis to see each agent&rsquo;s individual output.
          </p>
        </div>
      )}
    </div>
  );
}
