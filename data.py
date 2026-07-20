from __future__ import annotations
import os
import requests
import pandas as pd
from datetime import datetime, timedelta


# ── Tradier configuration ──────────────────────────────────────────────────────
# Sandbox is free (delayed data) and works from cloud/datacenter IPs, unlike the
# previous Yahoo Finance source which gets rate-limited on hosts like Render.
#   TRADIER_TOKEN     — your developer access token (required)
#   TRADIER_BASE_URL  — https://sandbox.tradier.com/v1 (default) or
#                       https://api.tradier.com/v1 for a funded/market-data account
TRADIER_BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1").rstrip("/")
TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN", "")

_TIMEOUT = 15


SECTOR_ETF_MAP: dict[str, str] = {
    'Technology': 'XLK',
    'Financial Services': 'XLF',
    'Healthcare': 'XLV',
    'Consumer Cyclical': 'XLY',
    'Consumer Defensive': 'XLP',
    'Industrials': 'XLI',
    'Energy': 'XLE',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Basic Materials': 'XLB',
    'Communication Services': 'XLC',
}

TIMEFRAME_DAYS: dict[str, int] = {'5d': 5, '1m': 30, '3m': 90}


class TradierError(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    if not TRADIER_TOKEN:
        raise TradierError(
            "TRADIER_TOKEN is not set. Create a free developer token at "
            "https://developer.tradier.com and set it as an environment variable."
        )
    resp = requests.get(
        f"{TRADIER_BASE_URL}{path}",
        params=params,
        headers={"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 401:
        raise TradierError("Tradier rejected the token (401). Check TRADIER_TOKEN / base URL.")
    if resp.status_code == 429:
        raise TradierError("Tradier rate limit hit (429). Try again shortly.")
    resp.raise_for_status()
    return resp.json()


def _as_list(node) -> list:
    """Tradier returns a single object when there's one result, a list when many."""
    if node is None:
        return []
    return node if isinstance(node, list) else [node]


def _quote(ticker: str) -> dict:
    data = _get("/markets/quotes", {"symbols": ticker.upper(), "greeks": "false"})
    quotes = (data.get("quotes") or {}).get("quote")
    items = _as_list(quotes)
    if not items:
        return {}
    return items[0]


def _quote_price(q: dict) -> float:
    for key in ("last", "close", "prevclose"):
        v = q.get(key)
        if v not in (None, 0):
            return float(v)
    return 0.0


def get_stock_info(ticker: str) -> dict:
    q = _quote(ticker)
    price = _quote_price(q)
    # Tradier does not expose GICS sector; benchmark comparison falls back to SPY.
    sector = 'Unknown'
    return {
        'ticker': ticker.upper(),
        'name': q.get('description') or ticker.upper(),
        'price': price,
        'sector': sector,
        'sector_etf': SECTOR_ETF_MAP.get(sector, 'SPY'),
    }


def get_price(ticker: str) -> float:
    return _quote_price(_quote(ticker))


def get_expiration_for_timeframe(ticker: str, timeframe: str) -> str | None:
    data = _get(
        "/markets/options/expirations",
        {"symbol": ticker.upper(), "includeAllRoots": "true", "strikes": "false"},
    )
    node = (data.get("expirations") or {}).get("date")
    expirations = _as_list(node)
    if not expirations:
        return None
    target = datetime.today() + timedelta(days=TIMEFRAME_DAYS[timeframe])
    exp_dates = [datetime.strptime(e, '%Y-%m-%d') for e in expirations]
    closest = min(exp_dates, key=lambda d: abs((d - target).days))
    return closest.strftime('%Y-%m-%d')


def _chain_df(options: list, option_type: str) -> pd.DataFrame:
    """Build a DataFrame matching the columns the rest of the app expects
    (strike, bid, ask, impliedVolatility, volume, openInterest)."""
    rows = []
    for o in options:
        if o.get("option_type") != option_type:
            continue
        greeks = o.get("greeks") or {}
        iv = greeks.get("mid_iv")
        if iv in (None, 0):
            iv = greeks.get("smv_vol")  # ORATS smoothed vol fallback
        rows.append({
            "strike": float(o.get("strike") or 0),
            "bid": _f(o.get("bid")),
            "ask": _f(o.get("ask")),
            "impliedVolatility": _f(iv),
            "volume": _f(o.get("volume")) or 0,
            "openInterest": _f(o.get("open_interest")) or 0,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("strike").reset_index(drop=True)
    return df


def get_options_chain(
    ticker: str, expiration: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = _get(
        "/markets/options/chains",
        {"symbol": ticker.upper(), "expiration": expiration, "greeks": "true"},
    )
    options = _as_list((data.get("options") or {}).get("option"))
    calls = _chain_df(options, "call")
    puts = _chain_df(options, "put")
    return calls, puts


def get_historical_drift(ticker: str, lookback_days: int = 30) -> float | None:
    """Annualized drift estimated from recent daily simple returns (252-day convention)."""
    try:
        end = datetime.today()
        start = end - timedelta(days=lookback_days + 15)
        data = _get(
            "/markets/history",
            {
                "symbol": ticker.upper(),
                "interval": "daily",
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
            },
        )
        days = _as_list((data.get("history") or {}).get("day"))
        closes = pd.Series([float(d["close"]) for d in days if d.get("close") is not None])
        if len(closes) < 5:
            return None
        returns = closes.pct_change().dropna().tail(lookback_days)
        return float(returns.mean() * 252)
    except Exception:
        return None


def get_risk_free_rate(fred_api_key: str | None = None) -> float:
    if fred_api_key:
        try:
            from fredapi import Fred
            series = Fred(api_key=fred_api_key).get_series(
                'TB3MS', observation_start=datetime.today() - timedelta(days=14)
            )
            return float(series.dropna().iloc[-1]) / 100
        except Exception:
            pass
    return 0.0525


def _f(v) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
