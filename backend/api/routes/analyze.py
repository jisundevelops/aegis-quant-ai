"""
backend.api.routes.analyze — POST /api/analyze endpoint.

Runs the full Chief Agent pipeline for a (symbol, timeframe):
  1. Build features via FeatureCombiner (Phase 4)
  2. Run ChiefAgent.analyze() which fans out to all 8 Phase 5 agents
  3. Run ProbabilityEngine for Bull/Bear/Range scenarios
  4. Run RiskAgent for SL/TP1/TP2/position size
  5. Return the full AnalyzeResponse

If the database has no market_data (e.g. fresh deploy, DB unreachable),
the endpoint automatically falls back to fetching data directly from
Binance and building features in-memory. This ensures /api/analyze
ALWAYS works, even if the scheduler hasn't populated the DB yet.
"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, status
from loguru import logger

from backend.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from chief.chief_agent import ChiefAgent
from features.combiner import FeatureCombiner

router = APIRouter()


async def _build_features_from_db(req: AnalyzeRequest) -> pd.DataFrame:
    """Build features from PostgreSQL market_data table."""
    combiner = FeatureCombiner()
    return await combiner.build(
        req.symbol,
        req.timeframe,
        limit=req.limit,
        use_cache=req.use_feature_cache,
    )


async def _build_features_from_binance(req: AnalyzeRequest) -> pd.DataFrame:
    """Fallback: fetch data directly from Binance/Yahoo + build features.

    Uses the multi-source crypto fetcher that tries Binance first, then
    falls back to Yahoo Finance if Binance is geo-blocked (common on
    US-based servers like Render).
    """
    from data.crypto_fetcher import build_features_from_crypto

    logger.info("FALLBACK: Fetching {} {} from crypto fetcher (Binance→Yahoo)...",
                req.symbol, req.timeframe)
    df = await build_features_from_crypto(
        symbol=req.symbol,
        timeframe=req.timeframe,
        limit=min(req.limit, 1000),
    )

    if df.empty:
        raise ValueError(f"No data for {req.symbol} {req.timeframe}")

    logger.info("FALLBACK: Built {} feature rows", len(df))
    return df


@router.post("/analyze", response_model=AnalyzeResponse,
             status_code=status.HTTP_200_OK)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """Run the full Aegis Quant AI analysis pipeline for a symbol."""
    logger.info("POST /api/analyze symbol={} timeframe={} limit={}",
                req.symbol, req.timeframe, req.limit)

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

    # 3. Run Chief Agent
    try:
        chief = ChiefAgent()
        signal = await chief.analyze(
            symbol=req.symbol,
            timeframe=req.timeframe,
            features_df=features_df,
            capital=req.capital,
        )
    except Exception as exc:
        logger.exception("Chief Agent failed for {}: {}", req.symbol, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chief Agent failed: {exc}",
        ) from exc

    # 4. Convert ChiefSignal -> AnalyzeResponse
    payload = signal.as_dict()
    try:
        return AnalyzeResponse(**payload)
    except Exception as exc:
        logger.exception("Response serialization failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Response serialization failed: {exc}",
        ) from exc
