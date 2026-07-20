from __future__ import annotations
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data import (
    get_stock_info,
    get_expiration_for_timeframe,
    get_options_chain,
    get_price,
    get_risk_free_rate,
    get_historical_drift,
    SECTOR_ETF_MAP,
)
from greeks import add_greeks_to_chain, get_atm_greeks, get_greeks_at_strike, probability_itm
from significance import assess_all, chain_signals as _chain_signals, GREEK_DESCRIPTIONS
from risk_rating import calculate_option_risk, tbill_profile
from scanner import fetch_sp500_df, run_scan, GICS_TO_SECTOR, MAX_WORKERS as SCAN_WORKERS

# ── Constants ──────────────────────────────────────────────────────────────────

GREEKS = ['delta', 'gamma', 'theta', 'vega', 'rho']
GREEK_LABELS = ['Delta', 'Gamma', 'Theta', 'Vega', 'Rho']

CHAIN_COLS = [
    'sel', 'moneyness', 'strike', 'bid', 'ask', 'impliedVolatility',
    'volume', 'openInterest', 'delta', 'gamma', 'theta', 'vega', 'rho', 'p_itm', 'signals',
]
CHAIN_RENAME = {
    'sel': '▶', 'moneyness': 'M', 'strike': 'Strike', 'bid': 'Bid', 'ask': 'Ask',
    'impliedVolatility': 'IV', 'volume': 'Volume', 'openInterest': 'OI',
    'delta': 'Delta', 'gamma': 'Gamma', 'theta': 'Theta', 'vega': 'Vega', 'rho': 'Rho',
    'p_itm': 'P(ITM)', 'signals': 'Signals',
}

GREEK_KEYS  = ['delta', 'gamma', 'theta', 'vega', 'rho']
GREEK_LABEL_MAP = {'delta': 'Delta', 'gamma': 'Gamma', 'theta': 'Theta', 'vega': 'Vega', 'rho': 'Rho'}

COLORS = {'ticker': '#2196F3', 'sector': '#FF9800', 'market': '#4CAF50'}

# ── Cached data fetchers ───────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def cached_stock_info(ticker: str) -> dict:
    return get_stock_info(ticker)

@st.cache_data(ttl=300)
def cached_expiration(ticker: str, timeframe: str) -> str | None:
    return get_expiration_for_timeframe(ticker, timeframe)

@st.cache_data(ttl=300)
def cached_options_chain(ticker: str, expiration: str) -> tuple:
    return get_options_chain(ticker, expiration)

@st.cache_data(ttl=300)
def cached_price(ticker: str) -> float:
    return get_price(ticker)

@st.cache_data(ttl=3600)
def cached_rfr(fred_key: str) -> float:
    return get_risk_free_rate(fred_key if fred_key else None)

@st.cache_data(ttl=300)
def cached_drift(ticker: str) -> float | None:
    return get_historical_drift(ticker)

@st.cache_data(ttl=86400)
def cached_sp500_df() -> pd.DataFrame:
    return fetch_sp500_df()

# ── Helpers ────────────────────────────────────────────────────────────────────

def prepare_chain(
    df: pd.DataFrame, S: float, exp: str, r: float, flag: str,
    selected_strike: float | None = None,
) -> pd.DataFrame:
    from datetime import datetime as _dt
    df_g = add_greeks_to_chain(df, S, exp, r, flag)
    lo = min(S * 0.80, selected_strike * 0.995) if selected_strike else S * 0.80
    hi = max(S * 1.20, selected_strike * 1.005) if selected_strike else S * 1.20
    df_g = df_g[(df_g['strike'] >= lo) & (df_g['strike'] <= hi)].copy()
    # Compute P(ITM) while IV is still on the 0–1 scale (before the *100 display scaling)
    exp_dt = _dt.strptime(exp, '%Y-%m-%d')
    t = max((exp_dt - _dt.now()).days / 365.0, 1 / 365)

    def _row_p_itm(row):
        p = probability_itm(
            flag, S, float(row['strike']), t, r,
            float(row.get('impliedVolatility') or 0),
        )
        return round(p * 100, 1) if p is not None else None

    df_g['p_itm'] = df_g.apply(_row_p_itm, axis=1)
    if 'impliedVolatility' in df_g.columns:
        df_g['impliedVolatility'] = df_g['impliedVolatility'] * 100
    df_g['signals'] = df_g.apply(
        lambda row: _chain_signals({k: row.get(k) for k in GREEK_KEYS}, flag), axis=1
    )
    if selected_strike is not None:
        df_g['sel'] = df_g['strike'].apply(
            lambda k: '▶' if abs(k - selected_strike) < 0.01 else ''
        )
    cols = [c for c in CHAIN_COLS if c in df_g.columns]
    return df_g[cols].rename(columns=CHAIN_RENAME)


def chain_column_config() -> dict:
    return {
        '▶':      st.column_config.TextColumn('▶', width='small', help='Currently selected strike'),
        'M':      st.column_config.TextColumn('M', width='small'),
        'Strike': st.column_config.NumberColumn('Strike', format='$%.2f'),
        'Bid':    st.column_config.NumberColumn('Bid', format='$%.2f'),
        'Ask':    st.column_config.NumberColumn('Ask', format='$%.2f'),
        'IV':     st.column_config.NumberColumn('IV %', format='%.1f'),
        'Volume': st.column_config.NumberColumn('Volume', format='%d'),
        'OI':     st.column_config.NumberColumn('OI', format='%d'),
        'Delta':  st.column_config.NumberColumn('Delta', format='%.4f'),
        'Gamma':  st.column_config.NumberColumn('Gamma', format='%.4f'),
        'Theta':  st.column_config.NumberColumn('Theta/day', format='%.4f'),
        'Vega':   st.column_config.NumberColumn('Vega', format='%.4f'),
        'Rho':    st.column_config.NumberColumn('Rho', format='%.4f'),
        'P(ITM)': st.column_config.NumberColumn(
            'P(ITM)', format='%.1f%%',
            help='Risk-neutral probability of expiring in-the-money — Black-Scholes N(d₂)',
        ),
        'Signals': st.column_config.TextColumn('Signals', help='🟠 High  🔴 Extreme — Greek flagged above normal range'),
    }


def fetch_comparison(
    ticker: str, stock_info: dict, timeframe: str, r: float,
    selected_strike: float | None = None,
) -> tuple[dict, dict]:
    """Returns (comp_calls, comp_puts); ticker uses selected_strike, benchmarks use ATM."""
    null = {k: None for k in GREEKS}
    sector_etf = stock_info['sector_etf']
    S = stock_info['price']

    def _greeks(sym: str, price: float, tf: str, flag: str, strike: float | None = None) -> dict:
        exp = cached_expiration(sym, tf)
        if not exp:
            return null
        try:
            calls, puts = cached_options_chain(sym, exp)
            chain = calls if flag == 'c' else puts
            if strike is not None:
                return get_greeks_at_strike(chain, price, strike, exp, r, flag)
            return get_atm_greeks(chain, price, exp, r, flag)
        except Exception:
            return null

    comp_calls, comp_puts = {}, {}
    for flag, comp in [('c', comp_calls), ('p', comp_puts)]:
        comp['ticker'] = _greeks(ticker, S, timeframe, flag, selected_strike)
        comp['sector'] = (
            _greeks(sector_etf, cached_price(sector_etf), timeframe, flag)
            if sector_etf and sector_etf != ticker else null
        )
        comp['market'] = (
            _greeks('SPY', cached_price('SPY'), timeframe, flag)
            if ticker != 'SPY' else null
        )

    return comp_calls, comp_puts


def build_chart(comp: dict, ticker_label: str, sector_label: str, flag: str) -> go.Figure:
    entities = [
        (ticker_label, 'ticker', COLORS['ticker']),
        (sector_label, 'sector', COLORS['sector']),
        ('SPY',        'market', COLORS['market']),
    ]
    fig = make_subplots(rows=1, cols=5, subplot_titles=GREEK_LABELS)

    for col_i, (greek, glabel) in enumerate(zip(GREEKS, GREEK_LABELS), start=1):
        for label, key, color in entities:
            val = comp.get(key, {}).get(greek)
            fig.add_trace(
                go.Bar(
                    name=label,
                    x=[glabel],
                    y=[val if val is not None else 0],
                    marker_color=color,
                    opacity=1.0 if val is not None else 0.25,
                    showlegend=(col_i == 1),
                    legendgroup=label,
                ),
                row=1, col=col_i,
            )

    opt = 'Calls' if flag == 'c' else 'Puts'
    fig.update_layout(
        title_text=f'ATM {opt} — {ticker_label} vs {sector_label} vs SPY',
        barmode='group',
        height=320,
        margin=dict(t=65, b=30, l=40, r=20),
        legend=dict(orientation='h', y=1.18, x=0.5, xanchor='center'),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
    )
    return fig


def build_comparison_table(comp: dict, ticker_label: str, sector_label: str) -> pd.DataFrame:
    return pd.DataFrame({
        'Greek': GREEK_LABELS,
        ticker_label:  [comp.get('ticker', {}).get(g) for g in GREEKS],
        sector_label:  [comp.get('sector', {}).get(g) for g in GREEKS],
        'SPY':         [comp.get('market', {}).get(g) for g in GREEKS],
    }).set_index('Greek')


# ── Significance panel ────────────────────────────────────────────────────────

def _badge_html(color: str, text: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 10px;'
        f'border-radius:12px;font-size:0.82em;font-weight:600;'
        f'display:inline-block;margin:2px 0">{text}</span>'
    )


def render_significance_panel(greeks: dict, flag: str) -> None:
    assessments = assess_all(greeks, flag)

    # Legend
    st.markdown(
        ' &nbsp; '.join(
            _badge_html(c, l)
            for c, l in [
                ('#F44336', '🔴 Extreme'),
                ('#FF9800', '🟠 High'),
                ('#2196F3', '🔵 Notable'),
                ('#4CAF50', '🟢 Normal'),
                ('#9E9E9E', '⚪ Low'),
            ]
        ),
        unsafe_allow_html=True,
    )
    st.write('')

    cols = st.columns(5)
    for col, key in zip(cols, GREEK_KEYS):
        val = greeks.get(key)
        a = assessments.get(key)
        label = GREEK_LABEL_MAP[key]
        with col:
            if val is None or a is None:
                st.metric(label, 'N/A')
                st.caption(GREEK_DESCRIPTIONS[key])
                continue

            st.metric(label, f'{val:.4f}')
            st.markdown(_badge_html(a.color, a.badge), unsafe_allow_html=True)
            st.caption(GREEK_DESCRIPTIONS[key])
            with st.expander('What does this mean?'):
                st.markdown(f'**{a.headline}**')
                st.write(a.detail)


# ── Probability of expiring ITM ──────────────────────────────────────────────

def _prob_color(prob: float) -> str:
    if prob >= 0.65: return '#4CAF50'
    if prob >= 0.45: return '#FFC107'
    if prob >= 0.25: return '#FF9800'
    return '#F44336'


def _prob_label(prob: float) -> str:
    pct = prob * 100
    if pct >= 65: return f'Likely  {pct:.0f}%'
    if pct >= 45: return f'Toss-up  {pct:.0f}%'
    if pct >= 25: return f'Unlikely  {pct:.0f}%'
    return f'Very Unlikely  {pct:.0f}%'


def render_prob_section(
    ticker: str,
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    S: float,
    selected_strike: float,
    exp: str,
    r: float,
    hist_drift: float | None,
) -> None:
    from datetime import datetime as _dt

    exp_dt = _dt.strptime(exp, '%Y-%m-%d')
    t = max((exp_dt - _dt.now()).days / 365.0, 1 / 365)

    def _get_iv(df: pd.DataFrame, flag: str) -> float | None:
        if df.empty:
            return None
        df_g = add_greeks_to_chain(df, S, exp, r, flag)
        idx = (df_g['strike'] - selected_strike).abs().idxmin()
        iv = float(df_g.loc[idx].get('impliedVolatility') or 0)
        return iv if iv > 0 else None

    iv_c = _get_iv(calls, 'c')
    iv_p = _get_iv(puts, 'p')

    rn_c  = probability_itm('c', S, selected_strike, t, r, iv_c) if iv_c else None
    rn_p  = probability_itm('p', S, selected_strike, t, r, iv_p) if iv_p else None
    trd_c = probability_itm('c', S, selected_strike, t, r, iv_c, hist_drift) if (iv_c and hist_drift is not None) else None
    trd_p = probability_itm('p', S, selected_strike, t, r, iv_p, hist_drift) if (iv_p and hist_drift is not None) else None

    pct_diff = (selected_strike - S) / S
    if abs(pct_diff) <= 0.005:
        moneyness_note = 'at-the-money'
    elif selected_strike > S:
        moneyness_note = 'OTM for calls · ITM for puts'
    else:
        moneyness_note = 'ITM for calls · OTM for puts'

    st.subheader(f'Probability of Expiring ITM — ${selected_strike:.2f} Strike')
    st.caption(
        f'Likelihood the stock price reaches **${selected_strike:.2f}** by **{exp}** '
        f'({moneyness_note}).  Current price: **${S:.2f}**'
    )
    if hist_drift is not None:
        trend_dir = 'bullish' if hist_drift > 0 else 'bearish'
        st.caption(
            f'{ticker} 30-day trend: **{hist_drift * 100:+.1f}% annualized** ({trend_dir})  ·  '
            f'Risk-free rate: **{r * 100:.2f}%**'
        )

    c_col, p_col = st.columns(2)

    def _prob_card(col, label: str, flag: str, rn_prob, trend_prob) -> None:
        with col:
            st.markdown(f'##### {label}')
            if rn_prob is None:
                st.info('Insufficient data for this strike.')
                return
            color = _prob_color(rn_prob)
            st.markdown(
                f'<div style="font-size:2.4em;font-weight:700;color:{color};line-height:1.0">'
                f'{rn_prob * 100:.1f}'
                f'<span style="font-size:0.42em;color:#888;font-weight:400"> %</span></div>',
                unsafe_allow_html=True,
            )
            bar_w = max(int(rn_prob * 100), 2)
            st.markdown(
                f'<div style="background:#e0e0e0;border-radius:6px;height:12px;'
                f'overflow:hidden;margin:4px 0 10px">'
                f'<div style="background:{color};height:100%;width:{bar_w}%"></div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(_pill(color, _prob_label(rn_prob)), unsafe_allow_html=True)
            st.write('')
            st.markdown(f'**Market-implied (N(d₂)):** {rn_prob * 100:.1f}%')
            if trend_prob is not None:
                delta_pts = (trend_prob - rn_prob) * 100
                sign = '+' if delta_pts >= 0 else ''
                st.markdown(
                    f'**30-day trend adjustment:** {trend_prob * 100:.1f}%  '
                    f'<span style="color:#888;font-size:0.9em">({sign}{delta_pts:.1f} pts vs market-implied)</span>',
                    unsafe_allow_html=True,
                )
            is_otm = (flag == 'c' and selected_strike > S) or (flag == 'p' and selected_strike < S)
            if is_otm:
                move_dir = 'up' if flag == 'c' else 'down'
                move_amt = abs(selected_strike - S)
                move_pct = move_amt / S * 100
                st.caption(
                    f'Stock must move **{move_dir} ${move_amt:.2f} ({move_pct:.1f}%)** '
                    f'from ${S:.2f} to reach this strike at expiry.'
                )

    _prob_card(c_col, 'Call — P(Expires ITM)', 'c', rn_c, trd_c)
    _prob_card(p_col, 'Put — P(Expires ITM)',  'p', rn_p, trd_p)

    with st.expander('How are these probabilities calculated?'):
        st.markdown(
            '**Market-implied probability** uses N(d₂) from the Black-Scholes model, '
            'where d₂ = (ln(S/K) + (r − ½σ²)t) / (σ√t). '
            'This is the risk-neutral probability derived from the option\'s implied volatility — '
            'what options markets collectively price in based on current rates and expected volatility.\n\n'
            '**Trend adjustment** replaces the risk-free rate with the stock\'s annualized '
            '30-day historical drift (μ). A bullish recent trend raises the call probability; '
            'a bearish trend raises the put probability.\n\n'
            '> These are theoretical estimates assuming a lognormal price distribution and '
            'constant volatility. Real outcomes depend on market conditions, liquidity, and '
            'events not captured by the model. Calls and puts at the same strike are '
            'complementary: P(call ITM) + P(put ITM) ≈ 100%.'
        )


# ── Overall risk rating ───────────────────────────────────────────────────────

def _row_data_at_strike(
    df: pd.DataFrame, S: float, strike: float, exp: str, r: float, flag: str
) -> dict | None:
    """Return greeks + ask + iv for the chain row closest to `strike`."""
    if df.empty:
        return None
    df_g = add_greeks_to_chain(df, S, exp, r, flag)
    idx = (df_g['strike'] - strike).abs().idxmin()
    row = df_g.loc[idx]
    return {
        'delta':  row.get('delta'),
        'theta':  row.get('theta'),
        'vega':   row.get('vega'),
        'ask':    float(row.get('ask') or 0) or None,
        'iv':     float(row.get('impliedVolatility') or 0) or None,
        'strike': float(row.get('strike', strike)),
    }


def _atm_row_data(df: pd.DataFrame, S: float, exp: str, r: float, flag: str) -> dict | None:
    return _row_data_at_strike(df, S, S, exp, r, flag)


def _score_bar_html(score: int, color: str) -> str:
    width = max(score, 3)
    return (
        f'<div style="background:#e0e0e0;border-radius:6px;height:14px;overflow:hidden;margin:4px 0 10px">'
        f'<div style="background:{color};height:100%;width:{width}%"></div></div>'
    )


def _pill(color: str, text: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:3px 12px;border-radius:12px;'
        f'font-size:0.85em;font-weight:600;display:inline-block">{text}</span>'
    )


def _render_rating_card(
    title: str,
    subtitle: str,
    profile,            # RiskProfile or dict (for T-bill)
    extra_lines: list[str],
    comparison_note: str | None = None,
) -> None:
    is_tbill = isinstance(profile, dict)
    score = profile['score'] if is_tbill else profile.score
    level = profile['level'] if is_tbill else profile.level
    color = profile['color'] if is_tbill else profile.color

    st.markdown(f'#### {title}')
    st.caption(subtitle)
    st.markdown(
        f'<div style="font-size:2.6em;font-weight:700;color:{color};line-height:1.1">'
        f'{score}<span style="font-size:0.38em;color:#888;font-weight:400"> / 100</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(_score_bar_html(score, color), unsafe_allow_html=True)
    st.markdown(_pill(color, level), unsafe_allow_html=True)
    st.write('')

    for line in extra_lines:
        st.markdown(line)

    if comparison_note:
        st.info(comparison_note)

    if not is_tbill and profile.components:
        comp_labels = {
            'direction': 'Direction / Probability',
            'theta':     'Theta Burden',
            'iv':        'IV Level',
            'vega':      'Vega Sensitivity',
        }
        with st.expander('Score breakdown'):
            for name, (earned, max_pts) in profile.components.items():
                pct = int(earned / max_pts * 100)
                bar_w = max(pct, 3)
                label = comp_labels.get(name, name)
                st.markdown(
                    f'**{label}** — {earned}/{max_pts} pts &nbsp;'
                    f'<span style="background:#e0e0e0;border-radius:4px;height:10px;'
                    f'display:inline-block;width:80px;vertical-align:middle">'
                    f'<span style="background:#607D8B;border-radius:4px;height:10px;'
                    f'display:inline-block;width:{bar_w}%"></span></span>',
                    unsafe_allow_html=True,
                )


def render_risk_rating(
    ticker: str,
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    S: float,
    exp: str,
    r: float,
    timeframe: str,
    selected_strike: float | None = None,
) -> None:
    from datetime import datetime

    days = max((datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days, 1)
    t_profile = tbill_profile(days, r)

    exp_spy = cached_expiration('SPY', timeframe)
    spy_calls_chain = spy_puts_chain = None
    spy_S = None
    if exp_spy:
        try:
            spy_calls_chain, spy_puts_chain = cached_options_chain('SPY', exp_spy)
            spy_S = cached_price('SPY')
        except Exception:
            pass

    rating_c, rating_p = st.tabs(['Calls', 'Puts'])

    for tab, df, flag, spy_df in [
        (rating_c, calls, 'c', spy_calls_chain),
        (rating_p, puts,  'p', spy_puts_chain),
    ]:
        with tab:
            opt_type = 'Call' if flag == 'c' else 'Put'
            target_strike = selected_strike if selected_strike is not None else S
            ticker_data = _row_data_at_strike(df, S, target_strike, exp, r, flag)
            if ticker_data is None:
                st.info('No option data available for risk rating.')
                continue

            ticker_profile = calculate_option_risk(
                delta=ticker_data['delta'], theta=ticker_data['theta'],
                vega=ticker_data['vega'],  iv=ticker_data['iv'],
                ask=ticker_data['ask'],    flag=flag,
                strike=ticker_data['strike'], spot=S,
            )

            spy_profile = None
            if spy_df is not None and spy_S:
                spy_data = _atm_row_data(spy_df, spy_S, exp_spy, r, flag)
                if spy_data:
                    spy_profile = calculate_option_risk(
                        delta=spy_data['delta'], theta=spy_data['theta'],
                        vega=spy_data['vega'],  iv=spy_data['iv'],
                        ask=spy_data['ask'],    flag=flag,
                        strike=spy_data['strike'], spot=spy_S,
                    )

            c1, c2, c3 = st.columns(3)

            # ── Ticker card ──────────────────────────────────────────────
            with c1:
                lines = []
                if ticker_profile.drivers:
                    lines.append('**Primary risk drivers:**')
                    lines += [f'• {d}' for d in ticker_profile.drivers]
                if ticker_profile.breakeven_pct is not None:
                    be = ticker_profile.breakeven_pct
                    dir_word = 'up' if be > 0 else 'down'
                    lines.append(
                        f'**Break-even:** stock must move **{dir_word} {abs(be):.1f}%** by expiry'
                    )
                _render_rating_card(
                    f'{ticker} ATM {opt_type}',
                    f'Expiry {exp}',
                    ticker_profile,
                    lines,
                )

            # ── SPY card ─────────────────────────────────────────────────
            with c2:
                if spy_profile:
                    lines = []
                    if spy_profile.drivers:
                        lines.append('**Primary risk drivers:**')
                        lines += [f'• {d}' for d in spy_profile.drivers]
                    if spy_profile.breakeven_pct is not None:
                        be = spy_profile.breakeven_pct
                        dir_word = 'up' if be > 0 else 'down'
                        lines.append(
                            f'**Break-even:** SPY must move **{dir_word} {abs(be):.1f}%** by expiry'
                        )
                    diff = ticker_profile.score - spy_profile.score
                    if diff > 5:
                        note = f'{ticker} carries **{diff} points more risk** than SPY for the same duration.'
                    elif diff < -5:
                        note = f'{ticker} carries **{abs(diff)} points less risk** than SPY.'
                    else:
                        note = f'{ticker} and SPY carry **similar risk** for this option type and duration.'
                    _render_rating_card(
                        f'SPY ATM {opt_type} (Market)',
                        f'Same duration — Expiry {exp_spy}',
                        spy_profile,
                        lines,
                        comparison_note=note,
                    )
                else:
                    st.markdown(f'#### SPY ATM {opt_type} (Market)')
                    st.info('SPY comparison data unavailable.')

            # ── T-bill card ──────────────────────────────────────────────
            with c3:
                tbill_lines = [
                    f'**Annualized yield:** {t_profile["annual_rate"]:.2f}%',
                    f'**Return over {days} days:** {t_profile["period_return"]:.3f}%',
                    '**Guaranteed** — no market, credit, or volatility risk.',
                    f'The option must gain more than **{t_profile["period_return"]:.3f}%** '
                    f'over {days} days just to match this risk-free return.',
                ]
                _render_rating_card(
                    f'{days}-Day T-Bill',
                    'Risk-free baseline — held to maturity',
                    t_profile,
                    tbill_lines,
                )


# ── Tab renderer ───────────────────────────────────────────────────────────────

def render_tab(timeframe: str, ticker: str, stock_info: dict, r: float) -> None:
    try:
        exp = cached_expiration(ticker, timeframe)
    except Exception:
        st.warning(f'Could not load expirations for **{ticker}**.')
        return

    if not exp:
        st.warning(f'No options expiration found near the {timeframe} window for **{ticker}**.')
        return

    st.caption(f'Expiration: **{exp}**')

    S = stock_info['price']
    sector_etf = stock_info['sector_etf']
    sector_label = sector_etf if sector_etf != ticker else 'N/A'
    hist_drift = cached_drift(ticker)

    try:
        calls, puts = cached_options_chain(ticker, exp)
    except Exception:
        st.error('Failed to load options chain data.')
        return

    # ── Strike selector ──────────────────────────────────────────────────────
    all_strikes = sorted(set(
        list(calls['strike'].dropna() if not calls.empty else []) +
        list(puts['strike'].dropna() if not puts.empty else [])
    ))
    if all_strikes:
        atm_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - S))
        selected_strike = st.selectbox(
            'Select Strike to Analyze',
            options=all_strikes,
            index=atm_idx,
            format_func=lambda x: f'${x:.2f}',
            key=f'strike_{ticker}_{timeframe}',
        )
        dist_pct = (selected_strike - S) / S * 100
        st.caption(f'{dist_pct:+.1f}% from current price (${S:.2f})')
    else:
        selected_strike = S

    # ── Chain tables (Calls | Puts) ──────────────────────────────────────────
    col_c, col_p = st.columns(2)
    col_cfg = chain_column_config()

    with col_c:
        st.subheader('Calls')
        if not calls.empty:
            st.dataframe(
                prepare_chain(calls, S, exp, r, 'c', selected_strike),
                column_config=col_cfg,
                width='stretch',
                hide_index=True,
                height=420,
            )
        else:
            st.info('No call options available.')

    with col_p:
        st.subheader('Puts')
        if not puts.empty:
            st.dataframe(
                prepare_chain(puts, S, exp, r, 'p', selected_strike),
                column_config=col_cfg,
                width='stretch',
                hide_index=True,
                height=420,
            )
        else:
            st.info('No put options available.')

    # ── Risk Analysis ────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f'Risk Analysis — ${selected_strike:.2f} Strike')
    st.caption(
        'Significance ratings for the selected strike at this expiration. '
        'Expand any Greek card to learn what the current value means for your trade.'
    )

    null_greeks = {k: None for k in GREEK_KEYS}
    sel_calls_g = get_greeks_at_strike(calls, S, selected_strike, exp, r, 'c') if not calls.empty else null_greeks
    sel_puts_g  = get_greeks_at_strike(puts,  S, selected_strike, exp, r, 'p') if not puts.empty  else null_greeks

    risk_tab_c, risk_tab_p = st.tabs(['Calls', 'Puts'])
    with risk_tab_c:
        render_significance_panel(sel_calls_g, 'c')
    with risk_tab_p:
        render_significance_panel(sel_puts_g, 'p')

    # ── Probability of Expiring ITM ──────────────────────────────────────────
    st.divider()
    render_prob_section(ticker, calls, puts, S, selected_strike, exp, r, hist_drift)

    # ── Overall Risk Rating ──────────────────────────────────────────────────
    st.divider()
    st.subheader('Overall Risk Rating')
    st.caption(
        f'Composite 1–100 score for the ${selected_strike:.2f} strike, benchmarked against '
        'a comparable SPY option and the equivalent T-bill.'
    )
    render_risk_rating(ticker, calls, puts, S, exp, r, timeframe, selected_strike)

    # ── Greeks vs Market ─────────────────────────────────────────────────────
    st.divider()
    st.subheader(f'Greeks vs Market — ${selected_strike:.2f} Strike')

    with st.spinner('Fetching comparison data…'):
        comp_calls, comp_puts = fetch_comparison(ticker, stock_info, timeframe, r, selected_strike)

    cmp_tab_c, cmp_tab_p = st.tabs(['Calls', 'Puts'])

    def _render_comparison(comp: dict, flag: str) -> None:
        st.plotly_chart(
            build_chart(comp, ticker, sector_label, flag),
            width='stretch',
        )
        tbl = build_comparison_table(comp, ticker, sector_label)
        st.dataframe(
            tbl.map(lambda v: f'{v:.4f}' if pd.notna(v) else 'N/A'),
            width='stretch',
        )

    with cmp_tab_c:
        _render_comparison(comp_calls, 'c')
    with cmp_tab_p:
        _render_comparison(comp_puts, 'p')


# ── S&P 500 Screener ──────────────────────────────────────────────────────────

_RISK_LEVEL_ORDER = {
    'Very Low': 0, 'Low': 1, 'Moderate': 2,
    'Moderate-High': 3, 'High': 4, 'Very High': 5,
}
_RISK_COLORS = {
    'Very Low': '#4CAF50', 'Low': '#8BC34A', 'Moderate': '#FFC107',
    'Moderate-High': '#FF9800', 'High': '#FF5722', 'Very High': '#F44336',
}


def _sector_card(ticker: str, name: str, sector: str, sector_etf: str,
                 avg_score: float, call_level: str, vs_sector: float | None,
                 iv_pct: float, prob_c: float | None) -> str:
    color = _RISK_COLORS.get(call_level, '#9E9E9E')
    vs_color = '#4CAF50' if (vs_sector or 0) < 0 else '#FF9800' if (vs_sector or 0) < 8 else '#F44336'
    vs_text = f'{vs_sector:+.1f} vs {sector_etf}' if vs_sector is not None else 'N/A'
    prob_text = f'P(Call ITM): {prob_c:.1f}%' if prob_c else ''
    return (
        f'<div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px 14px;margin-bottom:10px">'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
        f'<span style="font-size:1.25em;font-weight:700">{ticker}</span>'
        f'<span style="color:{vs_color};font-weight:600;font-size:0.95em">{vs_text}</span>'
        f'</div>'
        f'<div style="font-size:0.82em;color:#666;margin-bottom:4px">{name[:42]}</div>'
        f'<div style="display:flex;gap:8px;align-items:center">'
        f'<span style="background:{color};color:#fff;padding:2px 9px;border-radius:10px;'
        f'font-size:0.78em;font-weight:600">{call_level}</span>'
        f'<span style="font-size:0.82em;color:#888">Score {avg_score:.0f} · IV {iv_pct:.1f}%</span>'
        f'</div>'
        f'<div style="font-size:0.80em;color:#aaa;margin-top:3px">{prob_text}</div>'
        f'</div>'
    )


def render_screener(r: float) -> None:
    st.title('S&P 500 Options Risk Screener')
    st.caption(
        'Autonomously scans S&P 500 stocks — ATM calls & puts at the nearest '
        '1-month expiration — and ranks them by lowest risk relative to their sector ETF baseline.'
    )

    with st.spinner('Loading S&P 500 ticker list…'):
        sp500_df = cached_sp500_df()

    gics_sectors = sorted(sp500_df['wiki_sector'].dropna().unique().tolist())
    sector_options = ['All Sectors'] + gics_sectors

    st.divider()
    cfg_col1, cfg_col2, cfg_col3 = st.columns([3, 1, 1])
    with cfg_col1:
        sector_filter = st.selectbox(
            'Sector to scan',
            options=sector_options,
            help='Narrowing to one sector drastically reduces scan time.',
        )
    with cfg_col2:
        if sector_filter == 'All Sectors':
            ticker_subset = sp500_df['ticker'].tolist()
        else:
            ticker_subset = sp500_df[sp500_df['wiki_sector'] == sector_filter]['ticker'].tolist()
        n = len(ticker_subset)
        st.metric('Tickers', n)
    with cfg_col3:
        est_min = max(1, round(n / SCAN_WORKERS * 2 / 60))
        st.metric('Est. time', f'~{est_min} min')

    scan_key = f'scan_results_{sector_filter}'
    ts_key   = f'scan_ts_{sector_filter}'
    has_results = scan_key in st.session_state

    if has_results:
        st.caption(f'Last scan: **{st.session_state[ts_key]}** — click Refresh to re-run.')

    run_label = 'Refresh Scan' if has_results else 'Run Scan'
    if st.button(run_label, type='primary'):
        prog_bar   = st.progress(0.0)
        prog_text  = st.empty()

        def _cb(done: int, total: int, t: str) -> None:
            prog_bar.progress(done / total)
            prog_text.caption(f'Scanning {done}/{total} — {t}')

        results, etf_scores = run_scan(r, ticker_subset, _cb)

        prog_bar.empty()
        prog_text.empty()

        for res in results:
            etf = res['sector_etf']
            base = etf_scores.get(etf)
            res['vs_sector'] = round(res['avg_score'] - base, 1) if base is not None else None

        results.sort(key=lambda x: (x['vs_sector'] is None, x.get('vs_sector') or 0))

        st.session_state[scan_key]          = results
        st.session_state[ts_key]            = datetime.now().strftime('%Y-%m-%d %H:%M')
        st.session_state['scan_etf_scores'] = etf_scores
        st.rerun()

    if not has_results:
        st.info(
            'Select a sector (or leave as All Sectors) then click **Run Scan**. '
            'Results are cached — you only need to re-run when you want fresh data.'
        )
        return

    results: list[dict] = st.session_state[scan_key]
    etf_scores: dict[str, float] = st.session_state.get('scan_etf_scores', {})

    if not results:
        st.warning('No results — try a different sector or check your data connection.')
        return

    st.divider()

    # ── Top picks — lowest risk vs sector ────────────────────────────────────
    st.subheader('Lowest Risk Relative to Sector')
    st.caption(
        'Cards below show the safest ATM 1-month options in each sector, '
        'measured against the sector ETF baseline. Negative **vs Sector** = '
        'lower risk than the ETF — highlighted green.'
    )

    # Best per sector (lowest vs_sector)
    sector_best: dict[str, dict] = {}
    for res in results:
        s = res['sector']
        vs = res.get('vs_sector')
        if vs is None:
            continue
        if s not in sector_best or vs < sector_best[s].get('vs_sector', float('inf')):
            sector_best[s] = res

    best_list = sorted(sector_best.values(), key=lambda x: x.get('vs_sector') or 0)
    card_cols = st.columns(4)
    for i, res in enumerate(best_list):
        with card_cols[i % 4]:
            st.markdown(
                _sector_card(
                    res['ticker'], res['name'], res['sector'], res['sector_etf'],
                    res['avg_score'], res['call_level'], res.get('vs_sector'),
                    res['iv_pct'], res.get('prob_itm_c'),
                ),
                unsafe_allow_html=True,
            )

    # ── Sector baseline table ─────────────────────────────────────────────────
    st.divider()
    with st.expander('Sector ETF Baselines', expanded=False):
        etf_rows = []
        for sector, etf in sorted(SECTOR_ETF_MAP.items()):
            score = etf_scores.get(etf)
            etf_rows.append({'Sector': sector, 'ETF': etf, 'ATM 1M Risk Score': score})
        etf_rows.append({'Sector': 'Market', 'ETF': 'SPY', 'ATM 1M Risk Score': etf_scores.get('SPY')})
        st.dataframe(
            pd.DataFrame(etf_rows),
            hide_index=True,
            width='stretch',
            column_config={
                'ATM 1M Risk Score': st.column_config.NumberColumn(format='%.1f'),
            },
        )

    # ── Full results table ────────────────────────────────────────────────────
    st.divider()
    st.subheader(f'All Results — {len(results)} stocks')

    result_sectors = sorted({r['sector'] for r in results})
    tbl_sector = st.selectbox('Filter by sector', ['All'] + result_sectors, key='screener_tbl_sector')
    filtered = results if tbl_sector == 'All' else [r for r in results if r['sector'] == tbl_sector]

    n_show = st.slider('Rows to display', 10, min(200, len(filtered)), min(50, len(filtered)), key='screener_n_rows')

    df_tbl = pd.DataFrame([{
        'Ticker':       r['ticker'],
        'Company':      r['name'][:38],
        'Sector':       r['sector'],
        'Score':        r['avg_score'],
        'Level':        r['call_level'],
        'vs Sector ETF': r.get('vs_sector'),
        'IV %':         r['iv_pct'],
        'P(Call ITM)':  r.get('prob_itm_c'),
        'P(Put ITM)':   r.get('prob_itm_p'),
        'Expiry':       r['expiration'],
    } for r in filtered[:n_show]])

    st.dataframe(
        df_tbl,
        hide_index=True,
        width='stretch',
        height=580,
        column_config={
            'Score':   st.column_config.NumberColumn('Risk Score', format='%.1f'),
            'vs Sector ETF': st.column_config.NumberColumn(
                'vs Sector ETF', format='%+.1f',
                help='Stock avg risk score minus sector ETF score. Negative = safer than the ETF.',
            ),
            'IV %':          st.column_config.NumberColumn(format='%.1f%%'),
            'P(Call ITM)':   st.column_config.NumberColumn(format='%.1f%%'),
            'P(Put ITM)':    st.column_config.NumberColumn(format='%.1f%%'),
        },
    )

    st.caption(
        'Score = average of call + put ATM risk scores (1–100). '
        'Sorted by vs Sector ETF ascending — most negative = lowest risk relative to sector benchmark.'
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title='Options Guru', page_icon='📈', layout='wide')

    with st.sidebar:
        st.title('📈 Options Guru')
        st.caption('Options Greeks & market comparison')
        st.divider()

        view = st.radio(
            'Mode',
            ['Stock Analysis', 'S&P 500 Screener'],
            label_visibility='collapsed',
        )
        st.divider()

        fred_key = st.text_input(
            'FRED API Key (optional)',
            type='password',
            help='Free key at fred.stlouisfed.org for live US Treasury rates.',
        ).strip()

        if view == 'Stock Analysis':
            ticker_input = st.text_input(
                'Ticker Symbol',
                placeholder='e.g. AAPL, TSLA, NVDA',
                max_chars=10,
            ).strip().upper()
            analyze = st.button('Analyze', type='primary', use_container_width=True)
        else:
            ticker_input = ''
            analyze = False

        st.divider()
        st.caption('Data: Yahoo Finance\nGreeks: Black-Scholes (py_vollib)\nRate: FRED / 5.25% fallback')

    if 'ticker' not in st.session_state:
        st.session_state['ticker'] = ''
        st.session_state['fred_key'] = ''

    r = cached_rfr(fred_key)

    # ── Screener view ─────────────────────────────────────────────────────────
    if view == 'S&P 500 Screener':
        render_screener(r)
        return

    # ── Stock Analysis view ───────────────────────────────────────────────────
    if analyze and ticker_input:
        st.session_state['ticker'] = ticker_input
        st.session_state['fred_key'] = fred_key

    if not st.session_state['ticker']:
        st.title('Options Guru')
        st.markdown(
            'Enter a ticker in the sidebar and click **Analyze** to view '
            'options Greeks for the 5-day, 1-month, and 3-month expirations, '
            'with ATM comparisons against the sector ETF and SPY.'
        )
        return

    ticker = st.session_state['ticker']
    fred_key = st.session_state['fred_key']

    try:
        with st.spinner(f'Loading {ticker}…'):
            stock_info = cached_stock_info(ticker)
    except Exception:
        st.error(f'Failed to load data for **{ticker}**. Check the symbol and try again.')
        return

    if stock_info['price'] == 0:
        st.error(f'No price found for **{ticker}**. Is the ticker valid?')
        return

    # ── Header ────────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    with c1:
        st.title(f'{stock_info["name"]}  ({ticker})')
    with c2:
        st.metric('Price', f'${stock_info["price"]:,.2f}')
    with c3:
        st.metric('Sector', stock_info['sector'])
    with c4:
        st.metric('Sector ETF', stock_info['sector_etf'])

    rfr_source = 'FRED TB3MS' if fred_key else 'fallback — add FRED key for live rate'
    st.caption(f'Risk-free rate: **{r * 100:.2f}%** ({rfr_source})')
    st.divider()

    # ── Timeframe tabs ────────────────────────────────────────────────────────
    tab5d, tab1m, tab3m = st.tabs(['5-Day', '1-Month', '3-Month'])

    with tab5d:
        render_tab('5d', ticker, stock_info, r)
    with tab1m:
        render_tab('1m', ticker, stock_info, r)
    with tab3m:
        render_tab('3m', ticker, stock_info, r)


if __name__ == '__main__':
    main()
