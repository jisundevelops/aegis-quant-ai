# Aegis Quant AI — Frontend

Next.js web UI for the Aegis Quant AI backend.

## Stack

- Next.js 14 (App Router)
- React 18
- TypeScript
- TradingView Lightweight Charts
- SWR (data fetching)

## Quick Start

```bash
cd frontend
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment

| Variable              | Description                          | Default                       |
|-----------------------|--------------------------------------|-------------------------------|
| `NEXT_PUBLIC_API_URL` | Base URL of the FastAPI backend      | `http://localhost:8000`       |

## Layout

```
frontend/
├── src/
│   ├── app/             # Next.js App Router pages
│   ├── components/      # Reusable React components (charts, tables, …)
│   └── lib/             # API client, helpers
├── public/              # Static assets
├── next.config.js
├── tsconfig.json
└── package.json
```
