"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  UTCTimestamp,
} from "lightweight-charts";

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

interface EquityChartProps {
  data: EquityPoint[];
  height?: number;
}

export default function EquityChart({ data, height = 400 }: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#141921" },
        textColor: "#8b95a7",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1f242e" },
        horzLines: { color: "#1f242e" },
      },
      rightPriceScale: {
        borderColor: "#1f242e",
      },
      timeScale: {
        borderColor: "#1f242e",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: 1,
        vertLine: { color: "#00d4ff", width: 1, style: 3 },
        horzLine: { color: "#00d4ff", width: 1, style: 3 },
      },
    });
    chartRef.current = chart;

    // v4 API: chart.addAreaSeries(options) — NOT chart.addSeries(AreaSeries, options)
    // (AreaSeries export was introduced in v5; we're pinned to v4.2.0)
    const series = chart.addAreaSeries({
      lineColor: "#00d4ff",
      topColor: "rgba(0, 212, 255, 0.4)",
      bottomColor: "rgba(0, 212, 255, 0.0)",
      lineWidth: 2,
      priceLineVisible: true,
      priceLineStyle: 2,
    });

    // Convert data: lightweight-charts expects {time, value}
    // Time must be a UNIX timestamp (seconds) for intraday data
    const seriesData = data.map((point) => {
      const ts = new Date(point.timestamp);
      return {
        time: Math.floor(ts.getTime() / 1000) as UTCTimestamp,
        value: point.equity,
      };
    });

    series.setData(seriesData);
    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data, height]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center bg-bg-card border border-border rounded-lg text-[var(--fg-muted)] text-sm"
        style={{ height }}
      >
        No equity data
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
