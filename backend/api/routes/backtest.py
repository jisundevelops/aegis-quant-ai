"""
backend.api.routes.backtest — POST /api/backtest endpoint.

Runs a full backtest for a symbol over a date range.

If the database has no market_data, the endpoint automatically falls
back to fetching data directly from Binance (same as /api/analyze).
"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, status
from loguru import logger

from backend.schemas.backtest import BacktestRequest, BacktestResponse
from backtest.engine import BacktestConfig, BacktestEngine
from backtest.report import ReportGenerator
from features.combiner import FeatureCombiner

router = APIRouter()


async def _build_features_from_db(req: BacktestRequest) -> pd.DataFrame:
    """Build features from PostgreSQL market_data table."""
    combiner = FeatureCombiner()
    return await combiner.build(
        req.symbol, req.timeframe, limit=req.limit, use_cache=False,
    )


async def _build_features_from_binance(req: BacktestRequest) -> pd.DataFrame:
    """Fallback: fetch data from crypto fetcher (Binance→Yahoo) + build features."""
    from data.crypto_fetcher import build_features_from_crypto

    logger.info("FALLBACK: Fetching {} {} from crypto fetcher for backtest...",
                req.symbol, req.timeframe)
    df = await build_features_from_crypto(
        symbol=req.symbol,
        timeframe=req.timeframe,
        limit=min(req.limit, 1000),
    )

    if df.empty:
        raise ValueError(f"No data for {req.symbol} {req.timeframe}")

    logger.info("FALLBACK: Built {} feature rows for backtest", len(df))
    return df


@router.post("/backtest", response_model=BacktestResponse,
             status_code=status.HTTP_200_OK)
async def backtest(req: BacktestRequest) -> BacktestResponse:
    """Run a full backtest for a symbol over a date range."""
    logger.info("POST /api/backtest symbol={} tf={} {} to {}",
                req.symbol, req.timeframe, req.start, req.end)

    # 1. Try to build features from PostgreSQL
    features_df = None
    try:
        features_df = await _build_features_from_db(req)
    except Exception as exc:
        logger.warning("DB feature build failed, will try Binance fallback: {}", exc)

    if features_df is None or features_df.empty:
        # 2. Fallback: fetch directly from Binance
        try:
            features_df = await _build_features_from_binance(req)
        except Exception as exc:
            logger.exception("Binance fallback failed: {}", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Could not build features for {req.symbol} {req.timeframe}. "
                    f"Database is empty/unreachable AND Binance fetch failed: {exc}"
                ),
            ) from exc

    # 3. Run the backtest
    config = BacktestConfig(
        initial_capital=req.initial_capital,
        commission_bps=req.commission_bps,
        slippage_bps=req.slippage_bps,
    )
    engine = BacktestEngine(config=config)

    try:
        result = await engine.run(
            symbol=req.symbol,
            timeframe=req.timeframe,
            features_df=features_df,
            start=req.start,
            end=req.end,
        )
    except Exception as exc:
        logger.exception("Backtest failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Backtest failed: {exc}",
        ) from exc

    # 4. Generate report (JSON + optional DB save)
    try:
        report = ReportGenerator()
        report_dict = report.generate_json(result, save_to_db=req.save_to_db)
    except Exception as exc:
        logger.exception("Report generation failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {exc}",
        ) from exc

    return BacktestResponse(**report_dict)
