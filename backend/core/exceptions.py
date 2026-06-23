"""
backend.core.exceptions — Custom exception hierarchy and FastAPI handlers.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# --------------------------------------------------------------------
# Domain exceptions
# --------------------------------------------------------------------
class AegisError(Exception):
    """Base exception for all Aegis Quant AI errors."""


class DataConnectorError(AegisError):
    """Raised when a market data connector fails."""


class ConfigurationError(AegisError):
    """Raised when configuration is missing or invalid."""


class RiskLimitExceeded(AegisError):
    """Raised when a proposed position would breach risk limits."""


class AgentError(AegisError):
    """Raised when an agent fails to produce a valid analysis."""


class BacktestError(AegisError):
    """Raised when the backtesting engine encounters an invalid state."""


# --------------------------------------------------------------------
# FastAPI integration
# --------------------------------------------------------------------
def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AegisError)
    async def _aegis_error_handler(request: Request, exc: AegisError) -> JSONResponse:
        status_code = 500
        if isinstance(exc, ConfigurationError):
            status_code = 500
        elif isinstance(exc, DataConnectorError):
            status_code = 502
        elif isinstance(exc, RiskLimitExceeded):
            status_code = 422
        elif isinstance(exc, AgentError):
            status_code = 503
        elif isinstance(exc, BacktestError):
            status_code = 500

        return JSONResponse(
            status_code=status_code,
            content={"error": exc.__class__.__name__, "detail": str(exc)},
        )
