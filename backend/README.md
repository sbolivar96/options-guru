# Options Guru — Backend API

FastAPI service that exposes the existing Options Guru analytics as JSON for the
mobile app. It imports the modules at the repo root (`data.py`, `greeks.py`,
`significance.py`, `risk_rating.py`, `scanner.py`) **without modifying them**.

## Run locally

From the repo root (`Options Guru/`):

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

- Interactive docs: http://localhost:8000/docs
- `--host 0.0.0.0` is important so your **phone on the same Wi-Fi** can reach it
  at `http://<your-computer-LAN-ip>:8000`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |
| GET | `/api/stock/{ticker}` | Price, sector, risk-free rate, drift |
| GET | `/api/chain?ticker=&timeframe=&flag=` | Chain (±20% strikes) w/ Greeks, P(ITM), signals |
| GET | `/api/analysis?ticker=&timeframe=&strike=&flag=` | Greeks + significance, risk score, probability |
| GET | `/api/scan?limit=` | S&P 500 slice ranked by ATM 1-month risk |

`timeframe` ∈ `5d`,`1m`,`3m`.  `flag` ∈ `c` (call), `p` (put).

## Market data (Tradier)

Data comes from **Tradier** (quotes, options chains + IV/greeks, history). Yahoo
Finance was dropped because it rate-limits datacenter IPs, which breaks cloud
hosting. Set these environment variables:

| Var | Required | Notes |
|-----|----------|-------|
| `TRADIER_TOKEN` | **yes** | Free developer token from https://developer.tradier.com |
| `TRADIER_BASE_URL` | no | Defaults to `https://sandbox.tradier.com/v1` (free, delayed). Use `https://api.tradier.com/v1` with a funded/market-data account for real-time. |
| `FRED_API_KEY` | no | Live 3-month T-bill risk-free rate; else constant `0.0525`. |

Get a token: sign up at https://developer.tradier.com → create an app → copy the
**Sandbox Access Token**. Locally, `export TRADIER_TOKEN=...` before running uvicorn.

## Deploy

- **Render:** use [`../render.yaml`](../render.yaml) (New → Blueprint). Free tier works.
  Set `TRADIER_TOKEN` in the dashboard (it's marked `sync: false`, so Render prompts for it).
- **Any host:** run `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` from the
  repo root, with `TRADIER_TOKEN` set. The service must run from the repo root so the
  analytics modules import.

## Environment / CORS

CORS is open (`*`) because it's a read-only market-data API consumed by a mobile
client. Lock it down to your app's needs if you expose it publicly.
