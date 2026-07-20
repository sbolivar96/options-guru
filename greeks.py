from __future__ import annotations
import math
import pandas as pd
from datetime import datetime


def _safe(fn, *args) -> float | None:
    try:
        return round(float(fn(*args)), 4)
    except Exception:
        return None


def compute_greeks(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> dict:
    from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega, rho

    if sigma <= 0 or t <= 0 or S <= 0 or K <= 0:
        return {k: None for k in ['delta', 'gamma', 'theta', 'vega', 'rho']}
    return {
        'delta': _safe(delta, flag, S, K, t, r, sigma),
        'gamma': _safe(gamma, flag, S, K, t, r, sigma),
        'theta': _safe(theta, flag, S, K, t, r, sigma),
        'vega':  _safe(vega,  flag, S, K, t, r, sigma),
        'rho':   _safe(rho,   flag, S, K, t, r, sigma),
    }


def _moneyness(K: float, S: float, flag: str) -> str:
    pct = (K - S) / S
    if abs(pct) <= 0.005:
        return 'ATM'
    if flag == 'c':
        return 'ITM' if K < S else 'OTM'
    return 'ITM' if K > S else 'OTM'


def add_greeks_to_chain(
    df: pd.DataFrame, S: float, expiration: str, r: float, flag: str
) -> pd.DataFrame:
    if df.empty:
        return df
    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    t = max((exp_date - datetime.now()).days / 365.0, 1 / 365)
    df = df.copy().reset_index(drop=True)
    rows = [
        compute_greeks(flag, S, float(row['strike']), t, r, float(row.get('impliedVolatility') or 0))
        for _, row in df.iterrows()
    ]
    result = pd.concat([df, pd.DataFrame(rows)], axis=1)
    result['moneyness'] = result['strike'].apply(lambda k: _moneyness(float(k), S, flag))
    return result.sort_values('strike').reset_index(drop=True)


def get_greeks_at_strike(
    df: pd.DataFrame, S: float, strike: float, expiration: str, r: float, flag: str
) -> dict[str, float | None]:
    null = {k: None for k in ['delta', 'gamma', 'theta', 'vega', 'rho']}
    if df.empty:
        return null
    df_g = add_greeks_to_chain(df, S, expiration, r, flag)
    idx = (df_g['strike'] - strike).abs().idxmin()
    row = df_g.loc[idx]
    return {g: row.get(g) for g in null}


def get_atm_greeks(
    df: pd.DataFrame, S: float, expiration: str, r: float, flag: str
) -> dict[str, float | None]:
    return get_greeks_at_strike(df, S, S, expiration, r, flag)


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def probability_itm(
    flag: str, S: float, K: float, t: float, r: float, sigma: float,
    drift: float | None = None,
) -> float | None:
    """N(d2) probability of expiring in-the-money.

    drift=None  → risk-neutral (uses r as the drift term)
    drift=float → real-world (uses historical annualized drift)
    Returns a value in [0, 1], or None if inputs are invalid.
    """
    try:
        if sigma <= 0 or t <= 0 or S <= 0 or K <= 0:
            return None
        mu = r if drift is None else drift
        d2 = (math.log(S / K) + (mu - 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
        prob = _norm_cdf(d2) if flag == 'c' else _norm_cdf(-d2)
        return round(prob, 4)
    except Exception:
        return None
