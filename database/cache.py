"""
database.cache — Redis cache helpers for real-time market data.

TTL policy (Phase 2 spec):
  - Price  data : 60  seconds
  - Feature data : 300 seconds

Key naming (namespaced under `aegis:`):
  - aegis:price:{symbol}             -> JSON OHLCV snapshot
  - aegis:price:{symbol}:{tf}        -> JSON list of recent bars
  - aegis:features:{symbol}          -> JSON feature vector
  - aegis:features:{symbol}:{name}   -> JSON single feature

All values are stored as JSON strings (decode_responses=True on the client).
Functions are async and tolerate Redis failures gracefully — a cache miss
or outage returns None instead of raising, so the application can fall
back to the database or upstream connector.
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from config import settings

# --------------------------------------------------------------------
# TTLs (seconds)
# --------------------------------------------------------------------
PRICE_TTL = 60
FEATURE_TTL = 300

# --------------------------------------------------------------------
# Key builders
# --------------------------------------------------------------------
def _ns(*parts: str) -> str:
    """Build a namespaced Redis key."""
    return ":".join([settings.redis_namespace, *parts])


def price_key(symbol: str, timeframe: str | None = None) -> str:
    """Cache key for a price snapshot (optionally per-timeframe)."""
    return _ns("price", symbol, timeframe) if timeframe else _ns("price", symbol)


def features_key(symbol: str, feature_name: str | None = None) -> str:
    """Cache key for a feature vector (optionally per-feature)."""
    return (
        _ns("features", symbol, feature_name)
        if feature_name
        else _ns("features", symbol)
    )


# --------------------------------------------------------------------
# Generic get/set
# --------------------------------------------------------------------
async def cache_get(key: str) -> Any | None:
    """Get a JSON-deserialized value, or None on miss / Redis error."""
    try:
        from database.connection import get_redis

        raw = await get_redis().get(key)
    except Exception as exc:  # noqa: BLE001 — cache layer must not raise
        logger.warning("cache_get failed for {}: {}", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("cache_get: invalid JSON at {}", key)
        return None


async def cache_set(key: str, value: Any, ttl: int) -> bool:
    """Set a value as JSON with a TTL. Returns True on success."""
    try:
        from database.connection import get_redis

        payload = json.dumps(value, default=str)
        await get_redis().set(key, payload, ex=ttl)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_set failed for {}: {}", key, exc)
        return False


async def invalidate(key: str) -> bool:
    """Delete a single key. Returns True if deleted, False otherwise."""
    try:
        from database.connection import get_redis

        deleted = await get_redis().delete(key)
        return bool(deleted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("invalidate failed for {}: {}", key, exc)
        return False


async def invalidate_pattern(pattern: str) -> int:
    """Delete every key matching a glob pattern. Returns count deleted."""
    try:
        from database.connection import get_redis

        count = 0
        async for k in get_redis().scan_iter(match=pattern, count=500):
            await get_redis().delete(k)
            count += 1
        return count
    except Exception as exc:  # noqa: BLE001
        logger.warning("invalidate_pattern failed for {}: {}", pattern, exc)
        return 0


# --------------------------------------------------------------------
# Price helpers
# --------------------------------------------------------------------
async def cache_price(
    symbol: str, data: dict, timeframe: str | None = None
) -> bool:
    """Cache a price snapshot for 60 seconds."""
    return await cache_set(price_key(symbol, timeframe), data, PRICE_TTL)


async def get_price(symbol: str, timeframe: str | None = None) -> dict | None:
    """Return a cached price snapshot, or None on miss."""
    value = await cache_get(price_key(symbol, timeframe))
    return value if isinstance(value, dict) else None


# --------------------------------------------------------------------
# Feature helpers
# --------------------------------------------------------------------
async def cache_features(
    symbol: str, features: dict, feature_name: str | None = None
) -> bool:
    """Cache a feature vector for 300 seconds."""
    return await cache_set(features_key(symbol, feature_name), features, FEATURE_TTL)


async def get_features(
    symbol: str, feature_name: str | None = None
) -> dict | None:
    """Return a cached feature vector, or None on miss."""
    value = await cache_get(features_key(symbol, feature_name))
    return value if isinstance(value, dict) else None


__all__ = [
    "PRICE_TTL",
    "FEATURE_TTL",
    "price_key",
    "features_key",
    "cache_get",
    "cache_set",
    "invalidate",
    "invalidate_pattern",
    "cache_price",
    "get_price",
    "cache_features",
    "get_features",
]
