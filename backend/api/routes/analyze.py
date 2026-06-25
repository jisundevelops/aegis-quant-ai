"""backend.api.routes.analyze — POST /api/analyze endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from backend.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from chief.chief_agent import ChiefAgent
from features.combiner import FeatureCombiner

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse,
             status_code=status.HTTP_200_OK)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    logger.info("POST /api/analyze symbol={} timeframe={} limit={}",
                req.symbol, req.timeframe, req.limit)

    try:
        combiner = FeatureCombiner()
        features_df = await combiner.build(
            req.symbol, req.timeframe, limit=req.limit,
            use_cache=req.use_feature_cache,
        )
    except Exception as exc:
        logger.exception("Feature build failed for {}: {}", req.symbol, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Feature build failed: {exc}",
        ) from exc

    if features_df is None or features_df.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No market data found for {req.symbol} {req.timeframe}. "
                "Run the Phase 3 data scheduler first to populate market_data."
            ),
        )

    try:
        chief = ChiefAgent()
        signal = await chief.analyze(
            symbol=req.symbol, timeframe=req.timeframe,
            features_df=features_df, capital=req.capital,
        )
    except Exception as exc:
        logger.exception("Chief Agent failed for {}: {}", req.symbol, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chief Agent failed: {exc}",
        ) from exc

    payload = signal.as_dict()
    try:
        return AnalyzeResponse(**payload)
    except Exception as exc:
        logger.exception("Response serialization failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Response serialization failed: {exc}",
        ) from exc
