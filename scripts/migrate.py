#!/usr/bin/env python
"""
scripts.migrate — Convenience wrapper around Alembic.

Usage:
    python scripts/migrate.py upgrade       # upgrade to head
    python scripts/migrate.py downgrade -1  # rollback one revision
    python scripts/migrate.py current       # show current revision
    python scripts/migrate.py history       # show full history
    python scripts/migrate.py revision -m "msg"  # autogenerate a new revision
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPO_ROOT / "database" / "alembic.ini"


def main() -> int:
    if not ALEMBIC_INI.exists():
        print(f"ERROR: alembic.ini not found at {ALEMBIC_INI}", file=sys.stderr)
        return 1

    args = ["alembic", "-c", str(ALEMBIC_INI), *sys.argv[1:]]
    return subprocess.call(args, cwd=str(REPO_ROOT))


if __name__ == "__main__":
    sys.exit(main())
