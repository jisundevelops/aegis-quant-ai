"use client";

import { useState } from "react";
import { postAnalyze, type AnalyzeResponse } from "@/lib/api";
import SignalCard from "@/components/SignalCard";
import ProbabilityChart from "@/components/ProbabilityChart";

const ASSETS = [
  { symbol: "BTCUSDT", label: "BTC" },
  { symbol: "ETHUSDT", label: "ETH" },
  { symbol: "EURUSD=X", label: "EURUSD" },
  { symbol: "XAUUSD=X", label: "XAUUSD" },
];

const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

export default function DashboardPage() {
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
      const msg = err instanceof Error ? err.message : "Analysis failed";
      setError(msg);
      setSignal(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-[var(--fg-muted)] mt-1">
          Run the full Aegis Quant AI analysis pipeline on any asset.
        </p>
      </div>

      <div className="bg-bg-card border border-border rounded-lg p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div>
            <label className="block text-xs text-[var(--fg-muted)] uppercase tracking-wider mb-2">
              Asset
            </label>
            <div className="grid grid-cols-4 gap-2">
              {ASSETS.map((asset) => (
                <button
                  key={asset.symbol}
                  onClick={() => setSymbol(asset.symbol)}
                  className={`px-3 py-2 text-sm rounded transition-colors ${
                    symbol === asset.symbol
                      ? "bg-accent-primary text-bg-primary font-semibold"
                      : "bg-bg-tertiary text-[var(--fg-muted)] hover:text-[var(--fg)]"
                  }`}
                >
                  {asset.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs text-[var(--fg-muted)] uppercase tracking-wider mb-2">
              Timeframe
            </label>
            <div className="grid grid-cols-4 gap-2">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-3 py-2 text-sm rounded transition-colors ${
                    timeframe === tf
                      ? "bg-accent-primary text-bg-primary font-semibold"
                      : "bg-bg-tertiary text-[var(--fg-muted)] hover:text-[var(--fg)]"
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="bg-accent-primary text-bg-primary font-semibold py-2 px-6 rounded hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Analyzing..." : "Analyze"}
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 bg-bg-tertiary border border-bear rounded text-sm text-bear">
            {error}
          </div>
        )}
      </div>

      {signal && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <SignalCard signal={signal} />
            </div>
            <div>
              <ProbabilityChart probabilities={signal.probabilities} />
            </div>
          </div>
        </div>
      )}

      {!signal && !loading && (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center">
          <p className="text-[var(--fg-muted)]">
            Select an asset and timeframe, then click <strong>Analyze</strong> to
            run the full pipeline.
          </p>
        </div>
      )}
    </div>
  );
}
