"use client";

/**
 * Chart.tsx — Backward-compatible re-export shim.
 *
 * Phase 1 shipped this as a generic candlestick chart. Phase 8 moved the
 * equity-curve implementation to EquityChart.tsx. This module re-exports
 * EquityChart so any existing imports continue to work.
 */
export { default } from "./EquityChart";
export type { EquityPoint as Candle } from "./EquityChart";
