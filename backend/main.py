"""
Options Guru — FastAPI backend.

Wraps the existing Options Guru analytics modules (data / greeks / significance /
risk_rating / scanner) as a JSON API that the Expo mobile app consumes.

The original modules live one directory up; we add the parent dir to sys.path so
this file can import them without any changes to the existing code.

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Then the mobile app (or a browser) can hit http://<your-lan-ip>:8000/docs
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

# ── Make the existing Options Guru modules importable ─────────────────────────
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Existing Options Guru logic — reused as-is
from data import (
    get_stock_info,
    get_expiration_for_timeframe,
    get_options_chain,
    get_price,
    get_risk_free_rate,
    get_historical_drift,
)
from greeks import add_greeks_to_chain, probability_itm
from significance import assess_all, chain_signals, GREEK_DESCRIPTIONS
from risk_rating import calculate_option_risk

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Options Guru API",
    version="1.0.0",
    description="JSON backend powering the Options Guru iOS (TestFlight) app.",
)

# Mobile apps send requests from arbitrary origins; allow all (read-only data API).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GREEK_KEYS = ["delta", "gamma", "theta", "vega", "rho"]
TIMEFRAMES = {"5d", "1m", "3m"}
FRED_KEY = os.environ.get("FRED_API_KEY", "")


def _rfr() -> float:
    """Cached-enough risk-free rate; falls back to a constant inside get_risk_free_rate."""
    return get_risk_free_rate(FRED_KEY or None)


def _years_to_exp(exp: str) -> float:
    exp_dt = datetime.strptime(exp, "%Y-%m-%d")
    return max((exp_dt - datetime.now()).days / 365.0, 1 / 365)


def _validate_flag(flag: str) -> str:
    flag = (flag or "c").lower()
    if flag not in ("c", "p"):
        raise HTTPException(400, "flag must be 'c' (call) or 'p' (put)")
    return flag


def _validate_timeframe(tf: str) -> str:
    if tf not in TIMEFRAMES:
        raise HTTPException(400, f"timeframe must be one of {sorted(TIMEFRAMES)}")
    return tf


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "options-guru-api", "time": datetime.utcnow().isoformat()}


@app.get("/api/stock/{ticker}")
def stock(ticker: str) -> dict:
    """Basic stock info + benchmark context for a ticker."""
    try:
        info = get_stock_info(ticker)
    except Exception as e:
        raise HTTPException(502, f"Could not fetch stock info: {e}")
    if not info or float(info.get("price") or 0) <= 0:
        raise HTTPException(404, f"No price data for '{ticker.upper()}'")
    info["risk_free_rate"] = _rfr()
    info["drift"] = get_historical_drift(ticker)
    return info


@app.get("/api/chain")
def chain(
    ticker: str = Query(..., description="Underlying ticker, e.g. AAPL"),
    timeframe: str = Query("1m", description="5d | 1m | 3m"),
    flag: str = Query("c", description="c (calls) or p (puts)"),
) -> dict:
    """Options chain (±20% around spot) with Greeks, P(ITM), and signal flags."""
    flag = _validate_flag(flag)
    timeframe = _validate_timeframe(timeframe)
    ticker = ticker.upper()

    info = get_stock_info(ticker)
    S = float(info.get("price") or 0)
    if S <= 0:
        raise HTTPException(404, f"No price data for '{ticker}'")

    exp = get_expiration_for_timeframe(ticker, timeframe)
    if not exp:
        raise HTTPException(404, f"No options expirations found for '{ticker}'")

    calls, puts = get_options_chain(ticker, exp)
    df = calls if flag == "c" else puts
    if df.empty:
        raise HTTPException(404, "Options chain is empty for this expiration")

    r = _rfr()
    t = _years_to_exp(exp)
    df_g = add_greeks_to_chain(df, S, exp, r, flag)
    lo, hi = S * 0.80, S * 1.20
    df_g = df_g[(df_g["strike"] >= lo) & (df_g["strike"] <= hi)].copy()

    rows = []
    for _, row in df_g.iterrows():
        iv = float(row.get("impliedVolatility") or 0)
        greeks = {k: row.get(k) for k in GREEK_KEYS}
        p = probability_itm(flag, S, float(row["strike"]), t, r, iv)
        rows.append({
            "strike": round(float(row["strike"]), 2),
            "moneyness": row.get("moneyness"),
            "bid": _num(row.get("bid")),
            "ask": _num(row.get("ask")),
            "iv": round(iv * 100, 1) if iv else None,
            "volume": _int(row.get("volume")),
            "openInterest": _int(row.get("openInterest")),
            **{k: _num(greeks.get(k)) for k in GREEK_KEYS},
            "p_itm": round(p * 100, 1) if p is not None else None,
            "signals": chain_signals(greeks, flag),
        })

    return {
        "ticker": ticker,
        "name": info.get("name", ticker),
        "sector": info.get("sector"),
        "price": round(S, 2),
        "expiration": exp,
        "flag": flag,
        "timeframe": timeframe,
        "rows": rows,
    }


@app.get("/api/analysis")
def analysis(
    ticker: str = Query(...),
    timeframe: str = Query("1m"),
    strike: float = Query(..., description="Strike to analyze"),
    flag: str = Query("c"),
) -> dict:
    """Full analysis of one contract: Greeks + significance, risk score, P(ITM)."""
    flag = _validate_flag(flag)
    timeframe = _validate_timeframe(timeframe)
    ticker = ticker.upper()

    info = get_stock_info(ticker)
    S = float(info.get("price") or 0)
    if S <= 0:
        raise HTTPException(404, f"No price data for '{ticker}'")

    exp = get_expiration_for_timeframe(ticker, timeframe)
    if not exp:
        raise HTTPException(404, f"No options expirations found for '{ticker}'")

    calls, puts = get_options_chain(ticker, exp)
    df = calls if flag == "c" else puts
    if df.empty:
        raise HTTPException(404, "Options chain is empty for this expiration")

    r = _rfr()
    t = _years_to_exp(exp)
    drift = get_historical_drift(ticker)

    df_g = add_greeks_to_chain(df, S, exp, r, flag)
    idx = (df_g["strike"] - strike).abs().idxmin()
    row = df_g.loc[idx]
    actual_strike = float(row["strike"])
    iv = float(row.get("impliedVolatility") or 0) or None
    ask = float(row.get("ask") or 0) or None
    greeks = {k: _num(row.get(k)) for k in GREEK_KEYS}

    # Greek significance (plain-language explanations)
    assessments = assess_all({k: v for k, v in greeks.items() if v is not None}, flag)
    significance = {
        key: {
            "value": greeks.get(key),
            "level": a.level,
            "badge": a.badge,
            "color": a.color,
            "headline": a.headline,
            "detail": a.detail,
            "description": GREEK_DESCRIPTIONS.get(key),
        }
        for key, a in assessments.items()
    }
    # Include Greeks that had no assessment (e.g. value None) with just the description
    for key in GREEK_KEYS:
        significance.setdefault(key, {
            "value": greeks.get(key),
            "level": None,
            "badge": None,
            "color": None,
            "headline": None,
            "detail": None,
            "description": GREEK_DESCRIPTIONS.get(key),
        })

    # Risk score
    profile = calculate_option_risk(
        greeks.get("delta"), greeks.get("theta"), greeks.get("vega"),
        iv, ask, flag, strike=actual_strike, spot=S,
    )

    # Probability of expiring ITM (risk-neutral + real-world drift)
    rn = probability_itm(flag, S, actual_strike, t, r, iv) if iv else None
    rw = probability_itm(flag, S, actual_strike, t, r, iv, drift) if (iv and drift is not None) else None

    return {
        "ticker": ticker,
        "name": info.get("name", ticker),
        "price": round(S, 2),
        "expiration": exp,
        "flag": flag,
        "strike": round(actual_strike, 2),
        "iv": round(iv * 100, 1) if iv else None,
        "bid": _num(row.get("bid")),
        "ask": _num(ask),
        "greeks": greeks,
        "significance": significance,
        "risk": {
            "score": profile.score,
            "level": profile.level,
            "color": profile.color,
            "components": {k: {"earned": v[0], "max": v[1]} for k, v in profile.components.items()},
            "drivers": profile.drivers,
            "breakeven_pct": _num(profile.breakeven_pct),
        },
        "probability": {
            "risk_neutral_pct": round(rn * 100, 1) if rn is not None else None,
            "real_world_pct": round(rw * 100, 1) if rw is not None else None,
            "drift": _num(drift),
        },
    }


@app.get("/api/scan")
def scan(limit: int = Query(40, ge=5, le=120, description="How many S&P names to scan")) -> dict:
    """Scan a slice of the S&P 500 for ATM 1-month risk profiles.

    Kept modest by default so a mobile request returns in a reasonable time.
    """
    # Imported lazily so a slow scanner import never blocks lighter endpoints.
    from scanner import fetch_sp500_df, run_scan

    r = _rfr()
    sp = fetch_sp500_df()
    tickers = sp["ticker"].head(limit).tolist()
    results, etf_scores = run_scan(r, tickers)
    results.sort(key=lambda x: x.get("avg_score", 999))
    return {"count": len(results), "results": results, "etf_scores": etf_scores}


# ── Small serialization helpers ───────────────────────────────────────────────
def _num(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else round(f, 4)  # drop NaN
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else int(f)
    except (TypeError, ValueError):
        return None
