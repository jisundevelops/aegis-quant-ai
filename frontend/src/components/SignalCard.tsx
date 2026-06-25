"use client";

import type { AnalyzeResponse, Direction } from "@/lib/api";

const DIRECTION_STYLES: Record<Direction, { color: string; label: string; bg: string }> = {
  LONG: { color: "text-bull", label: "LONG", bg: "bg-bull" },
  SHORT: { color: "text-bear", label: "SHORT", bg: "bg-bear" },
  NEUTRAL: { color: "text-neutral", label: "NEUTRAL", bg: "bg-neutral" },
};

function formatPrice(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  return val.toFixed(4);
}

export default function SignalCard({ signal }: { signal: AnalyzeResponse }) {
  const style = DIRECTION_STYLES[signal.direction];
  const confidence = Math.round(signal.confidence_score);
  const riskScore = Math.round(signal.risk_score);
  const entryMid =
    signal.entry_zone && signal.entry_zone.length === 2
      ? (signal.entry_zone[0] + signal.entry_zone[1]) / 2
      : null;

  return (
    <div className="bg-bg-card border border-border rounded-lg p-6">
      {/* Header row */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold">
            {signal.symbol}{" "}
            <span className="text-sm text-[var(--fg-muted)] font-normal">
              {signal.timeframe}
            </span>
          </h2>
          <p className="text-xs text-[var(--fg-muted)] mt-1">
            {new Date(signal.timestamp).toLocaleString()}
          </p>
        </div>
        <div className="text-right">
          <div className={`text-3xl font-bold ${style.color}`}>
            {style.label}
          </div>
          <div className="text-xs text-[var(--fg-muted)] mt-1">
            Confidence: {confidence}%
          </div>
        </div>
      </div>

      {/* Confidence + Risk bars */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <div className="flex justify-between text-xs text-[var(--fg-muted)] mb-1">
            <span>Confidence</span>
            <span>{confidence}%</span>
          </div>
          <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
            <div
              className={`h-full ${style.bg} transition-all duration-300`}
              style={{ width: `${confidence}%` }}
            />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-xs text-[var(--fg-muted)] mb-1">
            <span>Risk Safety</span>
            <span>{riskScore}%</span>
          </div>
          <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-primary transition-all duration-300"
              style={{ width: `${riskScore}%` }}
            />
          </div>
        </div>
      </div>

      {/* Trade levels */}
      {signal.direction !== "NEUTRAL" && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <LevelBox label="Entry" value={formatPrice(entryMid)} />
          <LevelBox
            label="Stop Loss"
            value={formatPrice(signal.stop_loss)}
            color="text-bear"
          />
          <LevelBox
            label="TP1"
            value={formatPrice(signal.take_profit_1)}
            color="text-bull"
          />
          <LevelBox
            label="TP2"
            value={formatPrice(signal.take_profit_2)}
            color="text-bull"
          />
          <LevelBox
            label="R/R"
            value={
              signal.trade_plan?.risk_reward_ratio
                ? `${signal.trade_plan.risk_reward_ratio.toFixed(2)}`
                : "—"
            }
          />
        </div>
      )}

      {/* Reasoning */}
      <div className="mt-6 pt-4 border-t border-border">
        <h3 className="text-xs font-semibold text-[var(--fg-muted)] uppercase tracking-wider mb-2">
          Reasoning
        </h3>
        <p className="text-sm text-[var(--fg)] leading-relaxed whitespace-pre-wrap">
          {signal.reasoning}
        </p>
      </div>
    </div>
  );
}

function LevelBox({
  label,
  value,
  color = "text-[var(--fg)]",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="bg-bg-tertiary rounded p-3">
      <div className="text-xs text-[var(--fg-muted)] mb-1">{label}</div>
      <div className={`text-sm font-mono font-semibold ${color}`}>{value}</div>
    </div>
  );
}
