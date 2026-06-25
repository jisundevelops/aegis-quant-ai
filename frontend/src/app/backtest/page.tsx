"use client";

import { useState } from "react";
import {
  postBacktest,
  type BacktestResponse,
  type BacktestMetrics,
} from "@/lib/api";
import EquityChart from "@/components/EquityChart";

const ASSETS = [
  { symbol: "BTCUSDT", label: "BTC" },
  { symbol: "ETHUSDT", label: "ETH" },
  { symbol: "EURUSD=X", label: "EURUSD" },
  { symbol: "XAUUSD=X", label: "XAUUSD" },
];

const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [start, setStart] = useState("2024-01-01");
  const [end, setEnd] = useState("2024-12-31");
  const [initialCapital, setInitialCapital] = useState(100000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const res = await postBacktest({
        symbol,
        timeframe,
        start,
        end,
        initial_capital: initialCapital,
        save_to_db: true,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Backtest</h1>
        <p className="text-sm text-[var(--fg-muted)] mt-1">
          Run the Chief Agent over historical data and view performance metrics.
        </p>
      </div>

      {/* Form */}
      <div className="bg-bg-card border border-border rounded-lg p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <Field label="Asset">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-bg-tertiary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              {ASSETS.map((a) => (
                <option key={a.symbol} value={a.symbol}>
                  {a.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Timeframe">
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full bg-bg-tertiary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Start Date">
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="w-full bg-bg-tertiary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            />
          </Field>
          <Field label="End Date">
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full bg-bg-tertiary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            />
          </Field>
          <Field label="Initial Capital ($)">
            <input
              type="number"
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value))}
              className="w-full bg-bg-tertiary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            />
          </Field>
          <div className="flex items-end">
            <button
              onClick={handleRun}
              disabled={loading}
              className="w-full bg-accent-primary text-bg-primary font-semibold py-2 px-6 rounded hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {loading ? "Running..." : "Run Backtest"}
            </button>
          </div>
        </div>
        {error && (
          <div className="mt-4 p-3 bg-bg-tertiary border border-bear rounded text-sm text-bear">
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Metrics table */}
          <MetricsTable metrics={result.metrics} />

          {/* Equity curve */}
          <div className="bg-bg-card border border-border rounded-lg p-6">
            <h2 className="text-lg font-bold mb-4">Equity Curve</h2>
            <EquityChart data={result.equity_curve} height={400} />
          </div>

          {/* Bias warnings */}
          {result.bias_report.length > 0 && (
            <div className="bg-bg-card border border-border rounded-lg p-6">
              <h2 className="text-lg font-bold mb-3">Bias Detection</h2>
              <div className="space-y-2">
                {result.bias_report.map((warning, i) => (
                  <div
                    key={i}
                    className={`p-3 rounded border text-sm ${
                      warning.severity === "critical"
                        ? "border-bear bg-bg-tertiary"
                        : warning.severity === "warning"
                        ? "border-accent-primary bg-bg-tertiary"
                        : "border-border bg-bg-tertiary"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`text-xs font-bold uppercase ${
                          warning.severity === "critical"
                            ? "text-bear"
                            : warning.severity === "warning"
                            ? "text-accent-primary"
                            : "text-[var(--fg-muted)]"
                        }`}
                      >
                        {warning.severity}
                      </span>
                      <span className="text-xs text-[var(--fg-muted)]">
                        {warning.bias_type}
                      </span>
                    </div>
                    <p className="text-[var(--fg)]">{warning.message}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Trades table */}
          {result.trades.length > 0 && (
            <div className="bg-bg-card border border-border rounded-lg p-6">
              <h2 className="text-lg font-bold mb-4">
                Trades ({result.trades.length})
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-[var(--fg-muted)] uppercase border-b border-border">
                      <th className="py-2 pr-4">Direction</th>
                      <th className="py-2 pr-4">Entry</th>
                      <th className="py-2 pr-4">Exit</th>
                      <th className="py-2 pr-4">PnL</th>
                      <th className="py-2 pr-4">Return</th>
                      <th className="py-2 pr-4">Reason</th>
                      <th className="py-2 pr-4">Bars</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.slice(0, 50).map((trade, i) => (
                      <tr
                        key={i}
                        className="border-b border-border hover:bg-bg-tertiary"
                      >
                        <td
                          className={`py-2 pr-4 font-semibold ${
                            trade.direction === "LONG"
                              ? "text-bull"
                              : "text-bear"
                          }`}
                        >
                          {trade.direction}
                        </td>
                        <td className="py-2 pr-4 font-mono">
                          {trade.entry.toFixed(2)}
                        </td>
                        <td className="py-2 pr-4 font-mono">
                          {trade.exit.toFixed(2)}
                        </td>
                        <td
                          className={`py-2 pr-4 font-mono ${
                            trade.pnl >= 0 ? "text-bull" : "text-bear"
                          }`}
                        >
                          {trade.pnl >= 0 ? "+" : ""}
                          {trade.pnl.toFixed(2)}
                        </td>
                        <td
                          className={`py-2 pr-4 font-mono ${
                            trade.return_pct >= 0 ? "text-bull" : "text-bear"
                          }`}
                        >
                          {(trade.return_pct * 100).toFixed(2)}%
                        </td>
                        <td className="py-2 pr-4 text-[var(--fg-muted)]">
                          {trade.exit_reason}
                        </td>
                        <td className="py-2 pr-4 text-[var(--fg-muted)]">
                          {trade.bars_held}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {!result && !loading && (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center">
          <p className="text-[var(--fg-muted)]">
            Configure the backtest parameters and click{" "}
            <strong>Run Backtest</strong>.
          </p>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs text-[var(--fg-muted)] uppercase tracking-wider mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}

function MetricsTable({ metrics }: { metrics: BacktestMetrics }) {
  const rows = [
    { label: "Total Trades", value: metrics.total_trades.toString() },
    {
      label: "Win Rate",
      value: `${(metrics.win_rate * 100).toFixed(1)}%`,
      color: metrics.win_rate >= 0.5 ? "text-bull" : "text-bear",
    },
    {
      label: "Profit Factor",
      value:
        metrics.profit_factor === Infinity
          ? "∞"
          : metrics.profit_factor.toFixed(2),
      color: metrics.profit_factor >= 1 ? "text-bull" : "text-bear",
    },
    {
      label: "Sharpe Ratio",
      value: metrics.sharpe_ratio.toFixed(2),
      color: metrics.sharpe_ratio >= 1 ? "text-bull" : "text-neutral",
    },
    {
      label: "Sortino Ratio",
      value: metrics.sortino_ratio.toFixed(2),
      color: metrics.sortino_ratio >= 1 ? "text-bull" : "text-neutral",
    },
    {
      label: "Calmar Ratio",
      value: metrics.calmar_ratio.toFixed(2),
      color: metrics.calmar_ratio >= 1 ? "text-bull" : "text-neutral",
    },
    {
      label: "Max Drawdown",
      value: `${(metrics.max_drawdown * 100).toFixed(1)}%`,
      color: "text-bear",
    },
    {
      label: "Expectancy",
      value: `$${metrics.expectancy.toFixed(2)}`,
      color: metrics.expectancy >= 0 ? "text-bull" : "text-bear",
    },
    {
      label: "Total Return",
      value: `${(metrics.total_return * 100).toFixed(1)}%`,
      color: metrics.total_return >= 0 ? "text-bull" : "text-bear",
    },
    {
      label: "Final Equity",
      value: `$${metrics.final_equity.toFixed(2)}`,
      color: metrics.final_equity >= 100000 ? "text-bull" : "text-bear",
    },
  ];

  return (
    <div className="bg-bg-card border border-border rounded-lg p-6">
      <h2 className="text-lg font-bold mb-4">Performance Metrics</h2>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {rows.map((row) => (
          <div key={row.label} className="bg-bg-tertiary rounded p-3">
            <div className="text-xs text-[var(--fg-muted)] mb-1">
              {row.label}
            </div>
            <div className={`text-lg font-mono font-semibold ${row.color || "text-[var(--fg)]"}`}>
              {row.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
