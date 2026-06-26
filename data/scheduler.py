"""
data.scheduler — APScheduler-based data collection scheduler.

Schedules:
  - BinanceConnector.fetch_and_store_all()  every 15 minutes
  - YahooConnector.fetch_and_store_all()    every 1 hour

Each job:
  - Runs asynchronously inside APScheduler's AsyncIOScheduler.
  - Catches its own exceptions so one failed run does not kill the job.
  - Logs every run start, finish, and failure.

Integration:
  - Use `start_scheduler()` / `stop_scheduler()` from FastAPI lifespan.
  - The scheduler is opt-in via `settings.scheduler_enabled`.
"""
from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config import settings

# --------------------------------------------------------------------
# Singletons
# --------------------------------------------------------------------
_scheduler: AsyncIOScheduler | None = None
_binance_connector = None
_yahoo_connector = None


# --------------------------------------------------------------------
# Job wrappers (catch + log, never raise)
# --------------------------------------------------------------------
async def _binance_job() -> None:
    """Fetch + store + cache Binance OHLCV."""
    global _binance_connector
    if _binance_connector is None:
        from data.binance import BinanceConnector
        _binance_connector = BinanceConnector()
    started = datetime.utcnow()
    logger.info("[scheduler] Binance job started at {}", started.isoformat())
    try:
        results = await _binance_connector.fetch_and_store_all(limit=500)
        total = sum(results.values())
        logger.info("[scheduler] Binance job done: {} rows across {} pairs",
                    total, len(results))
    except Exception as exc:  # noqa: BLE001 — must not crash the scheduler
        logger.exception("[scheduler] Binance job FAILED: {}", exc)
    finally:
        await _binance_connector.close()


async def _yahoo_job() -> None:
    """Fetch + store + cache Yahoo OHLCV."""
    global _yahoo_connector
    if _yahoo_connector is None:
        from data.yahoo import YahooConnector
        _yahoo_connector = YahooConnector()
    started = datetime.utcnow()
    logger.info("[scheduler] Yahoo job started at {}", started.isoformat())
    try:
        results = await _yahoo_connector.fetch_and_store_all(limit=500)
        total = sum(results.values())
        logger.info("[scheduler] Yahoo job done: {} rows across {} pairs",
                    total, len(results))
    except Exception as exc:  # noqa: BLE001
        logger.exception("[scheduler] Yahoo job FAILED: {}", exc)
    finally:
        await _yahoo_connector.close()


# --------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------
def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton AsyncIOScheduler (creating it on first call)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,        # Collapse missed runs into one
                "max_instances": 1,      # No overlapping runs of the same job
                "misfire_grace_time": 60,  # Tolerate up to 60s late
            },
        )
    return _scheduler


def start_scheduler() -> AsyncIOScheduler | None:
    """Configure and start the scheduler if `settings.scheduler_enabled` is True.

    Also schedules an immediate data fetch on startup so the market_data
    table is populated without waiting for the first cron tick (which
    could be up to 15 minutes away).
    """
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false); skipping start.")
        return None

    sched = get_scheduler()

    # Binance: every 15 minutes (at the top of the minute)
    sched.add_job(
        _binance_job,
        trigger=CronTrigger(minute="*/15", timezone="UTC"),
        id="binance_fetch",
        name="Binance OHLCV fetch + store + cache",
        replace_existing=True,
    )

    # Yahoo: every 1 hour (at minute 5 to avoid the top-of-hour API congestion)
    sched.add_job(
        _yahoo_job,
        trigger=CronTrigger(hour="*", minute="5", timezone="UTC"),
        id="yahoo_fetch",
        name="Yahoo OHLCV fetch + store + cache",
        replace_existing=True,
    )

    # ── Immediate fetch on startup ────────────────────────────────────
    # Schedule a one-shot job that runs ASAP (next_run_time=now). This
    # populates market_data without waiting for the first cron tick.
    # Critical for fresh deploys where the table is empty.
    from datetime import datetime, timezone
    sched.add_job(
        _binance_job,
        trigger="date",  # one-shot, runs immediately
        id="binance_fetch_startup",
        name="Binance OHLCV initial fetch on startup",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    sched.add_job(
        _yahoo_job,
        trigger="date",
        id="yahoo_fetch_startup",
        name="Yahoo OHLCV initial fetch on startup",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )

    if not sched.running:
        sched.start()
        logger.info("Scheduler started — jobs: {}", [j.id for j in sched.get_jobs()])
        logger.info("Initial data fetch triggered — market_data will be populated within ~30s")

    return sched


async def fetch_now(binance: bool = True, yahoo: bool = True) -> dict[str, int]:
    """Manually trigger an immediate data fetch (used by /api/admin/fetch-data).

    Returns a dict mapping "{symbol}:{timeframe}" -> rows stored.
    """
    results: dict[str, int] = {}
    if binance:
        logger.info("[manual] Triggering immediate Binance fetch...")
        try:
            binance_results = await _binance_job_with_results()
            results.update(binance_results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[manual] Binance fetch failed: {}", exc)
    if yahoo:
        logger.info("[manual] Triggering immediate Yahoo fetch...")
        try:
            yahoo_results = await _yahoo_job_with_results()
            results.update(yahoo_results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[manual] Yahoo fetch failed: {}", exc)
    return results


async def _binance_job_with_results() -> dict[str, int]:
    """Run the Binance fetch and return the per-symbol results dict."""
    global _binance_connector
    if _binance_connector is None:
        from data.binance import BinanceConnector
        _binance_connector = BinanceConnector()
    try:
        results = await _binance_connector.fetch_and_store_all(limit=500)
        logger.info("[manual] Binance fetch done: {} rows across {} pairs",
                    sum(results.values()), len(results))
        return results
    finally:
        await _binance_connector.close()


async def _yahoo_job_with_results() -> dict[str, int]:
    """Run the Yahoo fetch and return the per-symbol results dict."""
    global _yahoo_connector
    if _yahoo_connector is None:
        from data.yahoo import YahooConnector
        _yahoo_connector = YahooConnector()
    try:
        results = await _yahoo_connector.fetch_and_store_all(limit=500)
        logger.info("[manual] Yahoo fetch done: {} rows across {} pairs",
                    sum(results.values()), len(results))
        return results
    finally:
        await _yahoo_connector.close()


async def stop_scheduler() -> None:
    """Gracefully shut down the scheduler and close any open connectors."""
    global _scheduler, _binance_connector, _yahoo_connector
    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler shutting down ...")
        _scheduler.shutdown(wait=False)
    if _binance_connector is not None:
        await _binance_connector.close()
        _binance_connector = None
    if _yahoo_connector is not None:
        await _yahoo_connector.close()
        _yahoo_connector = None
    _scheduler = None


__all__ = ["start_scheduler", "stop_scheduler", "get_scheduler", "fetch_now"]
