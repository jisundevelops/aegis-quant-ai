"""backend.api.routes.backtest — POST /api/backtest endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from backend.schemas.backtest import BacktestRequest, BacktestResponse
from backtest.engine import BacktestConfig, BacktestEngine
from backtest.report import ReportGenerator
from features.combiner import FeatureCombiner

router = APIRouter()


@router.post("/backtest", response_model=BacktestResponse,
             status_code=status.HTTP_200_OK)
async def backtest(req: BacktestRequest) -> BacktestResponse:
    """Run a full backtest for a symbol over a date range."""
    logger.info("POST /api/backtest symbol={} tf={} {} to {}",
                req.symbol, req.timeframe, req.start, req.end)

    # 1. Build features from PostgreSQL
    try:
        combiner = FeatureCombiner()
        features_df = await combiner.build(
            req.symbol, req.timeframe, limit=req.limit, use_cache=False,
        )
    except Exception as exc:
        logger.exception("Feature build failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Feature build failed: {exc}",
        ) from exc

    if features_df is None or features_df.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No market data for {req.symbol} {req.timeframe}. "
                "Run the data scheduler first."
            ),
        )

    # 2. Run the backtest
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

    # 3. Generate report (JSON + optional DB save)
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
