/**
 * TradingView Lightweight Charts candlestick component.
 * Phase 8 implements the full chart with live data streaming.
 */
"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  CandlestickSeries,
} from "lightweight-charts";

export interface Candle {
  time: number; // UNIX seconds
  open: number;
  high: number;
  low: number;
  close: number;
}

interface ChartProps {
  data: Candle[];
  height?: number;
}

export default function Chart({ data, height = 480 }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#0b0e14" },
        textColor: "#e6e9ef",
      },
      grid: {
        vertLines: { color: "#1f242e" },
        horzLines: { color: "#1f242e" },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    series.setData(
      data.map((c) => ({
        time: c.time as never,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data, height]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
