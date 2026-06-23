# Aegis Quant AI

> Modular, institutional-grade AI trading research assistant.

[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)]()

---

## Overview

**Aegis Quant AI** is a modular, research-grade trading assistant built around
multi-agent orchestration. Each specialized agent (technical, fundamental,
sentiment, macro) produces independent evidence; a **Chief Agent** aggregates
that evidence into a probabilistic conviction score; a **Risk Manager** then
converts the conviction into a sized, risk-bounded position proposal. Every
signal is backtestable end-to-end before any live deployment.

The codebase is built phase-by-phase. Each phase is a self-contained module
with its own commit, and never conflicts with previously shipped phases.

## Architecture

```
                  +----------------------+
                  |   Frontend (Next.js) |
                  |  TradingView Charts  |
                  +----------+-----------+
                             |
                  +----------v-----------+
                  |   FastAPI Backend    |
                  |  (REST + WebSocket)  |
                  +----------+-----------+
                             |
   +-----------+-------------+-------------+-----------+
   |           |             |             |           |
+--v---+  +----v----+  +-----v-----+ +-----v----+ +----v----+
| Data |  | Features|  |  Agents   | | Backtest | |  Risk   |
| Conn |  | Engine  |  | (multi)   | |  Engine  | | Manager |
+------+  +---------+  +-----+-----+ +----------+ +---------+
                             |
                       +-----v------+
                       | Chief Agent|
                       +-----+------+
                             |
                       +-----v------+
                       | Probability|
                       |   Engine   |
                       +------------+

Database layer:  PostgreSQL (persistent) + Redis (cache/pubsub)
```

## Repository Layout

```
aegis-quant-ai/
├── backend/        FastAPI app: routes, core utilities, Pydantic schemas
├── agents/         One file per specialized agent (technical, fundamental, …)
├── features/       Feature engineering modules (indicators, microstructure)
├── data/           Market data connectors (Binance, Yahoo, MetaTrader 5)
├── backtest/       Backtesting engine, portfolio tracking, performance metrics
├── risk/           Risk manager, position sizing, exposure limits
├── chief/          Chief agent: orchestrates and aggregates subordinate agents
├── probability/    Probability engine: converts evidence into conviction
├── frontend/       Next.js web UI (separate package)
├── database/       PostgreSQL + Redis setup and migrations
├── config/         Centralized .env-backed settings loader
├── scripts/        Operational and deployment scripts
├── tests/          Unit and integration tests
├── .env.example    Template for required environment variables
├── requirements.txt
└── README.md
```

## Tech Stack

| Layer        | Technology                                  |
|--------------|---------------------------------------------|
| Backend      | Python 3.13, FastAPI                        |
| Data         | Pandas, NumPy                              |
| ML           | LightGBM, XGBoost, PyTorch                 |
| Database     | PostgreSQL, Redis                          |
| Frontend     | Next.js                                    |
| Charts       | TradingView Lightweight Charts             |

## Quick Start

```bash
# 1. Clone
git clone <repo-url> aegis-quant-ai
cd aegis-quant-ai

# 2. Create virtual environment (Python 3.13)
python3.13 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# edit .env and fill in your credentials

# 5. Run the API
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the auto-generated OpenAPI specification.

## Frontend

The Next.js frontend lives in `frontend/` and is a separate npm package.
See `frontend/README.md` for setup instructions.

## Development Phases

| Phase | Scope                                         | Status |
|-------|-----------------------------------------------|--------|
| 1     | Project structure, scaffolding, configuration | ✅      |
| 2     | Data connectors (Binance, Yahoo, MT5)         | ⏳      |
| 3     | Feature engine (indicators + microstructure)  | ⏳      |
| 4     | Multi-agent framework                         | ⏳      |
| 5     | Probability engine + Chief agent              | ⏳      |
| 6     | Backtesting engine                            | ⏳      |
| 7     | Risk manager                                  | ⏳      |
| 8     | Frontend (Next.js + TradingView)              | ⏳      |
| 9     | Database + caching layer                      | ⏳      |
| 10    | Deployment, CI/CD, observability              | ⏳      |

## Security

- All secrets are loaded from environment variables via `config/settings.py`.
- The `.env` file is git-ignored and MUST NEVER be committed.
- API keys are never logged.
- Database credentials are never hardcoded.

## License

Proprietary. All rights reserved.
