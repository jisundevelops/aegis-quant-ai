"""
config — Centralized configuration loader for Aegis Quant AI.

All application settings are loaded from environment variables (typically
provided through a `.env` file at the repository root). No credentials are
ever hardcoded in source. The single `settings` instance exposed by this
package is the authoritative configuration object for the entire codebase.

Usage:
    from config import settings
    db_url = settings.postgres_dsn
"""
from config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings", "settings"]

# Lazy singleton — created on first import.
settings: Settings = get_settings()
