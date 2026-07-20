from __future__ import annotations
import concurrent.futures
from datetime import datetime
from typing import Callable

import pandas as pd

from data import (
    get_stock_info,
    get_expiration_for_timeframe,
    get_options_chain,
    SECTOR_ETF_MAP,
)
from greeks import add_greeks_to_chain, probability_itm
from risk_rating import calculate_option_risk

SCAN_TIMEFRAME = '1m'
MAX_WORKERS = 6
TICKER_TIMEOUT = 20  # seconds per ticker before giving up

# Representative S&P 500 tickers — used when Wikipedia is unreachable
_FALLBACK: list[tuple[str, str]] = [
    # Information Technology
    ('AAPL', 'Information Technology'), ('MSFT', 'Information Technology'),
    ('NVDA', 'Information Technology'), ('AVGO', 'Information Technology'),
    ('AMD', 'Information Technology'), ('INTC', 'Information Technology'),
    ('CRM', 'Information Technology'), ('ORCL', 'Information Technology'),
    ('IBM', 'Information Technology'), ('QCOM', 'Information Technology'),
    ('TXN', 'Information Technology'), ('MU', 'Information Technology'),
    # Financials
    ('JPM', 'Financials'), ('BAC', 'Financials'), ('WFC', 'Financials'),
    ('GS', 'Financials'), ('MS', 'Financials'), ('V', 'Financials'),
    ('MA', 'Financials'), ('AXP', 'Financials'), ('BLK', 'Financials'),
    ('SCHW', 'Financials'), ('C', 'Financials'),
    # Health Care
    ('JNJ', 'Health Care'), ('UNH', 'Health Care'), ('PFE', 'Health Care'),
    ('ABBV', 'Health Care'), ('MRK', 'Health Care'), ('TMO', 'Health Care'),
    ('ABT', 'Health Care'), ('LLY', 'Health Care'), ('DHR', 'Health Care'),
    ('BMY', 'Health Care'), ('AMGN', 'Health Care'), ('GILD', 'Health Care'),
    # Consumer Discretionary
    ('AMZN', 'Consumer Discretionary'), ('TSLA', 'Consumer Discretionary'),
    ('HD', 'Consumer Discretionary'), ('MCD', 'Consumer Discretionary'),
    ('NKE', 'Consumer Discretionary'), ('TGT', 'Consumer Discretionary'),
    ('SBUX', 'Consumer Discretionary'), ('LOW', 'Consumer Discretionary'),
    ('GM', 'Consumer Discretionary'), ('F', 'Consumer Discretionary'),
    # Consumer Staples
    ('PG', 'Consumer Staples'), ('KO', 'Consumer Staples'), ('PEP', 'Consumer Staples'),
    ('WMT', 'Consumer Staples'), ('COST', 'Consumer Staples'), ('PM', 'Consumer Staples'),
    ('MO', 'Consumer Staples'), ('CL', 'Consumer Staples'), ('GIS', 'Consumer Staples'),
    # Industrials
    ('CAT', 'Industrials'), ('BA', 'Industrials'), ('HON', 'Industrials'),
    ('GE', 'Industrials'), ('RTX', 'Industrials'), ('LMT', 'Industrials'),
    ('DE', 'Industrials'), ('MMM', 'Industrials'), ('UPS', 'Industrials'),
    ('FDX', 'Industrials'), ('NOC', 'Industrials'),
    # Energy
    ('XOM', 'Energy'), ('CVX', 'Energy'), ('COP', 'Energy'), ('EOG', 'Energy'),
    ('SLB', 'Energy'), ('MPC', 'Energy'), ('VLO', 'Energy'), ('OXY', 'Energy'),
    ('PSX', 'Energy'),
    # Utilities
    ('NEE', 'Utilities'), ('DUK', 'Utilities'), ('SO', 'Utilities'),
    ('D', 'Utilities'), ('AEP', 'Utilities'), ('EXC', 'Utilities'),
    ('PCG', 'Utilities'), ('XEL', 'Utilities'),
    # Real Estate
    ('AMT', 'Real Estate'), ('PLD', 'Real Estate'), ('SPG', 'Real Estate'),
    ('EQIX', 'Real Estate'), ('PSA', 'Real Estate'), ('O', 'Real Estate'),
    # Materials
    ('LIN', 'Materials'), ('APD', 'Materials'), ('SHW', 'Materials'),
    ('FCX', 'Materials'), ('NEM', 'Materials'), ('DOW', 'Materials'),
    # Communication Services
    ('GOOGL', 'Communication Services'), ('META', 'Communication Services'),
    ('NFLX', 'Communication Services'), ('DIS', 'Communication Services'),
    ('CMCSA', 'Communication Services'), ('T', 'Communication Services'),
    ('VZ', 'Communication Services'), ('CHTR', 'Communication Services'),
]

# Wikipedia GICS sector names → yfinance / SECTOR_ETF_MAP keys
GICS_TO_SECTOR: dict[str, str] = {
    'Information Technology': 'Technology',
    'Financials':             'Financial Services',
    'Health Care':            'Healthcare',
    'Consumer Discretionary': 'Consumer Cyclical',
    'Consumer Staples':       'Consumer Defensive',
    'Industrials':            'Industrials',
    'Energy':                 'Energy',
    'Utilities':              'Utilities',
    'Real Estate':            'Real Estate',
    'Materials':              'Basic Materials',
    'Communication Services': 'Communication Services',
}

SECTOR_TO_GICS = {v: k for k, v in GICS_TO_SECTOR.items()}


def fetch_sp500_df() -> pd.DataFrame:
    """Returns a DataFrame with columns: ticker, wiki_sector.

    Attempts Wikipedia first; falls back to the built-in representative list.
    wiki_sector uses GICS names (e.g. 'Information Technology').
    """
    try:
        df = pd.read_html(
            'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
            attrs={'id': 'constituents'},
        )[0]
        out = (
            df[['Symbol', 'GICS Sector']]
            .rename(columns={'Symbol': 'ticker', 'GICS Sector': 'wiki_sector'})
            .copy()
        )
        out['ticker'] = out['ticker'].str.replace('.', '-', regex=False).str.strip()
        out['wiki_sector'] = out['wiki_sector'].str.strip()
        return out.reset_index(drop=True)
    except Exception:
        rows = [(t, s) for t, s in _FALLBACK]
        return pd.DataFrame(rows, columns=['ticker', 'wiki_sector'])


def _scan_one(ticker: str, r: float) -> dict | None:
    """Compute ATM 1-month options risk profile for a single ticker.
    Returns None on any failure so the caller can silently skip it.
    """
    try:
        info = get_stock_info(ticker)
        S = float(info.get('price') or 0)
        if S <= 0:
            return None

        exp = get_expiration_for_timeframe(ticker, SCAN_TIMEFRAME)
        if not exp:
            return None

        calls, puts = get_options_chain(ticker, exp)
        if calls.empty and puts.empty:
            return None

        exp_dt = datetime.strptime(exp, '%Y-%m-%d')
        t = max((exp_dt - datetime.now()).days / 365.0, 1 / 365)

        def _row_data(df: pd.DataFrame, flag: str) -> dict | None:
            if df.empty:
                return None
            df_g = add_greeks_to_chain(df, S, exp, r, flag)
            if df_g.empty:
                return None
            idx = (df_g['strike'] - S).abs().idxmin()
            row = df_g.loc[idx]
            ask = float(row.get('ask') or 0) or None
            iv  = float(row.get('impliedVolatility') or 0) or None
            return {
                'delta':  row.get('delta'),
                'theta':  row.get('theta'),
                'vega':   row.get('vega'),
                'ask':    ask,
                'iv':     iv,
                'strike': float(row.get('strike', S)),
            }

        row_c = _row_data(calls, 'c')
        row_p = _row_data(puts, 'p')
        if not row_c or not row_p:
            return None

        profile_c = calculate_option_risk(
            row_c['delta'], row_c['theta'], row_c['vega'],
            row_c['iv'], row_c['ask'], 'c',
            strike=row_c['strike'], spot=S,
        )
        profile_p = calculate_option_risk(
            row_p['delta'], row_p['theta'], row_p['vega'],
            row_p['iv'], row_p['ask'], 'p',
            strike=row_p['strike'], spot=S,
        )

        prob_c = probability_itm('c', S, S, t, r, row_c['iv']) if row_c['iv'] else None
        prob_p = probability_itm('p', S, S, t, r, row_p['iv']) if row_p['iv'] else None
        iv_pct = ((row_c['iv'] or 0) + (row_p['iv'] or 0)) / 2 * 100

        return {
            'ticker':     ticker,
            'name':       info.get('name', ticker),
            'sector':     info.get('sector', 'Unknown'),
            'sector_etf': info.get('sector_etf', 'SPY'),
            'price':      S,
            'expiration': exp,
            'call_score': profile_c.score,
            'call_level': profile_c.level,
            'put_score':  profile_p.score,
            'put_level':  profile_p.level,
            'avg_score':  round((profile_c.score + profile_p.score) / 2, 1),
            'iv_pct':     round(iv_pct, 1),
            'prob_itm_c': round(prob_c * 100, 1) if prob_c else None,
            'prob_itm_p': round(prob_p * 100, 1) if prob_p else None,
        }
    except Exception:
        return None


def run_scan(
    r: float,
    tickers: list[str],
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> tuple[list[dict], dict[str, float]]:
    """Scan tickers + sector ETFs concurrently, returning results and ETF baseline scores.

    Args:
        r           : risk-free rate
        tickers     : list of tickers to scan
        progress_cb : called with (done, total, current_ticker) after each completion

    Returns:
        results        : one dict per successfully scanned ticker (ordered as submitted)
        etf_avg_scores : {sector_etf_ticker: avg_risk_score}
    """
    etf_list = list(set(SECTOR_ETF_MAP.values()) | {'SPY'})
    # Scan ETFs alongside tickers; dedup while preserving ticker order
    all_tickers = list(dict.fromkeys(tickers + etf_list))

    raw: dict[str, dict | None] = {}
    done = 0
    total = len(all_tickers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_scan_one, t, r): t for t in all_tickers}
        for future in concurrent.futures.as_completed(futures):
            t_key = futures[future]
            done += 1
            try:
                raw[t_key] = future.result(timeout=TICKER_TIMEOUT)
            except Exception:
                raw[t_key] = None
            if progress_cb:
                progress_cb(done, total, t_key)

    etf_scores: dict[str, float] = {
        etf: raw[etf]['avg_score']
        for etf in etf_list
        if raw.get(etf)
    }

    results = [raw[t] for t in tickers if raw.get(t)]
    return results, etf_scores
