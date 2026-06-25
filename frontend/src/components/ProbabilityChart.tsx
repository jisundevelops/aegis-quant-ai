"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";
import type { ScenarioProbabilities } from "@/lib/api";

interface ProbabilityChartProps {
  probabilities: ScenarioProbabilities;
}

const COLORS = {
  bull: "#00d4a0",
  bear: "#ff4757",
  range: "#8b95a7",
};

export default function ProbabilityChart({ probabilities }: ProbabilityChartProps) {
  const data = [
    { name: "Bull", value: probabilities.bull_pct, color: COLORS.bull },
    { name: "Bear", value: probabilities.bear_pct, color: COLORS.bear },
    { name: "Range", value: probabilities.range_pct, color: COLORS.range },
  ];

  return (
    <div className="bg-bg-card border border-border rounded-lg p-6">
      <h2 className="text-lg font-bold mb-1">Scenario Probabilities</h2>
      <p className="text-xs text-[var(--fg-muted)] mb-6">
        Bull / Bear / Range — must sum to 100%
      </p>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={90}
              paddingAngle={2}
              dataKey="value"
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: "#11151c",
                border: "1px solid #1f242e",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number) => `${value.toFixed(2)}%`}
            />
            <Legend
              verticalAlign="bottom"
              iconType="circle"
              wrapperStyle={{ fontSize: "12px", paddingTop: "16px" }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Probability bars */}
      <div className="mt-6 space-y-3">
        {data.map((item) => (
          <div key={item.name}>
            <div className="flex justify-between text-xs mb-1">
              <span style={{ color: item.color }}>{item.name}</span>
              <span className="text-[var(--fg-muted)]">
                {item.value.toFixed(2)}%
              </span>
            </div>
            <div className="h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
              <div
                className="h-full transition-all duration-500"
                style={{ width: `${item.value}%`, backgroundColor: item.color }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-border text-xs text-[var(--fg-muted)]">
        Sum: {probabilities.sum_pct.toFixed(2)}%
      </div>
    </div>
  );
}
