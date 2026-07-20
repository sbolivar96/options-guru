from __future__ import annotations
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


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


def get_stock_info(ticker: str) -> dict:
    t = yf.Ticker(ticker.upper())
    info = t.info
    hist = t.history(period='1d')
    price = (
        float(hist['Close'].iloc[-1]) if not hist.empty
        else float(info.get('regularMarketPrice') or 0)
    )
    sector = str(info.get('sector') or 'Unknown')
    return {
        'ticker': ticker.upper(),
        'name': info.get('longName', ticker.upper()),
        'price': price,
        'sector': sector,
        'sector_etf': SECTOR_ETF_MAP.get(sector, 'SPY'),
    }


def get_expiration_for_timeframe(ticker: str, timeframe: str) -> str | None:
    expirations = yf.Ticker(ticker.upper()).options
    if not expirations:
        return None
    target = datetime.today() + timedelta(days=TIMEFRAME_DAYS[timeframe])
    exp_dates = [datetime.strptime(e, '%Y-%m-%d') for e in expirations]
    closest = min(exp_dates, key=lambda d: abs((d - target).days))
    return closest.strftime('%Y-%m-%d')


def get_options_chain(
    ticker: str, expiration: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    chain = yf.Ticker(ticker.upper()).option_chain(expiration)
    return chain.calls, chain.puts


def get_price(ticker: str) -> float:
    t = yf.Ticker(ticker.upper())
    hist = t.history(period='1d')
    if not hist.empty:
        return float(hist['Close'].iloc[-1])
    return float(t.info.get('regularMarketPrice') or 0)


def get_historical_drift(ticker: str, lookback_days: int = 30) -> float | None:
    """Annualized drift estimated from recent daily simple returns (252-day convention)."""
    try:
        hist = yf.Ticker(ticker.upper()).history(period=f'{lookback_days + 10}d')
        closes = hist['Close'].dropna()
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
