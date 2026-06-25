# Aegis Quant AI — Frontend

Next.js web UI for the Aegis Quant AI backend.

## Stack

- Next.js 14 (App Router)
- React 18 + TypeScript
- Tailwind CSS 3
- TradingView Lightweight Charts (equity curves)
- Recharts (probability pie charts)
- Axios (API client)

## Quick Start

```bash
cd frontend
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Pages

| Route          | Description                                                    |
|----------------|----------------------------------------------------------------|
| `/`            | Dashboard — asset/timeframe selector, Analyze button, signal   |
| `/agents`      | Per-agent breakdown cards with bias + confidence bars          |
| `/probability` | Bull/Bear/Range scenario probabilities (pie chart)             |
| `/backtest`    | Backtest form + metrics table + equity curve + trades + biases |
| `/journal`     | Trade journal table view                                       |

## Styling

Dark theme: `#0a0e14` background, green (`#00d4a0`) for bullish, red (`#ff4757`) for bearish, gray (`#8b95a7`) for neutral.

## Environment

| Variable              | Description                          | Default                       |
|-----------------------|--------------------------------------|-------------------------------|
| `NEXT_PUBLIC_API_URL` | Base URL of the FastAPI backend      | `http://localhost:8000`       |
