"use client";

import type { AgentBreakdown, Bias } from "@/lib/api";

const BIAS_COLORS: Record<Bias, string> = {
  Bullish: "text-bull",
  Bearish: "text-bear",
  Neutral: "text-neutral",
};

const BIAS_BAR_COLORS: Record<Bias, string> = {
  Bullish: "bg-bull",
  Bearish: "bg-bear",
  Neutral: "bg-neutral",
};

const AGENT_LABELS: Record<string, string> = {
  trend: "Trend Agent",
  smc: "Smart Money Agent",
  derivatives: "Derivatives Agent",
  macro: "Macro Agent",
  session: "Session Agent",
  sentiment: "Sentiment Agent",
  retail_trap: "Retail Trap Agent",
  risk: "Risk Agent",
};

interface AgentCardProps {
  name: string;
  data: AgentBreakdown;
}

export default function AgentCard({ name, data }: AgentCardProps) {
  const label = AGENT_LABELS[name] || name;
  const confidence = Math.round(data.confidence);
  const weightPct = Math.round(data.weight * 100);

  return (
    <div className="bg-bg-card border border-border rounded-lg p-4 hover:border-border-subtle transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--fg)]">{label}</h3>
          <p className="text-xs text-[var(--fg-muted)]">
            Weight: {weightPct}%
          </p>
        </div>
        <div className={`text-lg font-bold ${BIAS_COLORS[data.bias]}`}>
          {data.bias}
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-[var(--fg-muted)] mb-1">
          <span>Confidence</span>
          <span>{confidence}%</span>
        </div>
        <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
          <div
            className={`h-full ${BIAS_BAR_COLORS[data.bias]} transition-all duration-300`}
            style={{ width: `${confidence}%` }}
          />
        </div>
      </div>

      {/* Weighted contribution */}
      <div className="text-xs text-[var(--fg-muted)] mb-2">
        Weighted contribution:{" "}
        <span
          className={
            data.weighted_contribution > 0
              ? "text-bull"
              : data.weighted_contribution < 0
              ? "text-bear"
              : "text-neutral"
          }
        >
          {data.weighted_contribution > 0 ? "+" : ""}
          {data.weighted_contribution.toFixed(2)}
        </span>
      </div>

      {/* Reasoning */}
      <p className="text-xs text-[var(--fg-muted)] leading-relaxed line-clamp-3">
        {data.reasoning}
      </p>
    </div>
  );
}
