# MarketRecall AI

Hourly 4-hour direction forecasts for SUI, WAL and CETUS from a model that keeps its own track record on Walrus. Built for the Walrus × Tatum *Total Recall* hackathon (Track 1).

## Stack

- **Backend:** Python 3.12, FastAPI, APScheduler, SQLModel (SQLite locally, Postgres in production)
- **Frontend:** React, Vite, TypeScript, Tailwind, @mysten/dapp-kit
- **Data:** Tatum Data API (live 1h OHLCV), Tatum Sui gRPC (checkpoints, epoch), Binance public klines (historical backfill), CoinGecko (market overview)
- **Memory:** Walrus Memory Mainnet via the `memwal` Python SDK
- **LLM:** `agnes-3.0-flash` via yjs (OpenAI-compatible Chat Completions)

## Setup

```bash
cp .env.example .env          # fill in keys
python3.12 -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt   # Windows; use .venv/bin/pip elsewhere
cd frontend && npm install
```

## Run

```bash
# backend (from backend/)
../.venv/Scripts/python -m uvicorn app.main:app --port 8000

# frontend (from frontend/), proxies /api to :8000
npm run dev
```

Every hour the backend collects one Tatum candle, one Sui onchain snapshot and a CoinGecko overview, resolves forecasts whose 4h horizon has passed (writing each as an EPISODE memory to Walrus), and makes a new Amnesiac + Recall forecast. Daily it retrains the models, snapshots the learned state to Walrus as CREDIBILITY memories, and writes an observation lesson.

Open http://localhost:5173 for the landing page; `/app` is the signed-in dashboard.

## Sign-in

- **Sui wallet**: any Wallet Standard extension, or the Slush web wallet. The user signs a one-time, gas-free message; the backend verifies it with Tatum's Sui gRPC `SignatureVerificationService` and issues a session token.
- **Google (zkLogin via Enoki)**: enabled when `frontend/.env.local` has both keys (see `frontend/.env.example`):
  1. Google Cloud Console → APIs & Services → Credentials → *Create OAuth client ID* (type: Web application). Add `http://localhost:5173` (and your production domain) to *Authorized JavaScript origins* and *Authorized redirect URIs*. Copy the client ID.
  2. Enoki portal (portal.enoki.mystenlabs.com) → create an app → add a **public** API key with zkLogin enabled for **mainnet** → under Auth providers add Google with the client ID from step 1.
  3. Put both values in `frontend/.env.local` as `VITE_GOOGLE_CLIENT_ID` and `VITE_ENOKI_API_KEY`, then restart `npm run dev`.

## Security

- The wallet is only used for `signPersonalMessage` at sign-in; the app never requests a transaction. Challenges are single-use and expire after 10 minutes, and sign-out revokes the token server-side.
- LLM input is prefiltered for advice and prompt-injection requests, and every reply is validated (numbers must come from the facts; no advice, links or wallet-scam wording). Failed replies fall back to a template.
- Rate limits on sign-in, the guide and paid actions; 32 KB body limit; CORS restricted to `CORS_ORIGINS`.
- The production build sets a Content-Security-Policy; `frontend/vercel.json` adds `X-Frame-Options` and `frame-ancestors`.
- Deploy as a single backend process (the scheduler and the rate limits assume it). Set `CORS_ORIGINS`, `APP_DOMAIN` and a random `ADMIN_TOKEN`; set `TRUST_PROXY=true` (with `PROXY_HOPS`) only behind a proxy you trust.

## Deploy

Backend on Render with Neon Postgres, frontend on Vercel: see [DEPLOY.md](DEPLOY.md).

## Scripts (from repo root)

| Script | Purpose |
|---|---|
| `backend/scripts/backfill.py --days 90` | Historical candles + hourly onchain snapshots for backtesting (resumable) |
| `backend/scripts/backtest.py [--no-onchain]` | Walk-forward backtest report (Amnesiac vs Recall, per voice, per regime) |
| `backend/scripts/bootstrap.py` | Seed memory from the backtest, run the promotion gate, snapshot to Walrus (run once) |
| `backend/scripts/wipe_restore.py [--all]` | Delete the local learned state and rebuild it from Walrus |
| `backend/scripts/copy_db.py <postgres-url>` | Copy the local SQLite database into an empty Postgres |
| `backend/scripts/check_walrus.py` | Read-only Walrus Memory auth check |
| `backend/scripts/check_tatum_grpc.py` | List Sui gRPC services exposed by Tatum |
| `backend/scripts/first_memory.py` | Write + recall one memory on Walrus Mainnet |

## Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest
```
