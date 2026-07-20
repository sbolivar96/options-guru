from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Level = Literal['low', 'normal', 'notable', 'high', 'extreme']

_COLORS: dict[Level, str] = {
    'low':     '#9E9E9E',
    'normal':  '#4CAF50',
    'notable': '#2196F3',
    'high':    '#FF9800',
    'extreme': '#F44336',
}

_LABELS: dict[Level, str] = {
    'low':     '⚪ Low',
    'normal':  '🟢 Normal',
    'notable': '🔵 Notable',
    'high':    '🟠 High',
    'extreme': '🔴 Extreme',
}

# One-line definition of each Greek — always shown to new traders
GREEK_DESCRIPTIONS: dict[str, str] = {
    'delta': 'How much the option price moves per $1 change in the stock.',
    'gamma': 'How quickly delta itself changes as the stock price moves.',
    'theta': 'Daily time decay — dollars lost each calendar day from time passing.',
    'vega':  "Sensitivity to a 1% change in implied volatility (the market's forecast of future swings).",
    'rho':   'Sensitivity to a 1% change in the risk-free interest rate.',
}


@dataclass
class Assessment:
    level: Level
    headline: str   # one-line summary of what this level means
    detail: str     # 2-4 sentence plain-language explanation for new traders

    @property
    def color(self) -> str:
        return _COLORS[self.level]

    @property
    def badge(self) -> str:
        return _LABELS[self.level]

    @property
    def is_flagged(self) -> bool:
        return self.level in ('high', 'extreme')


# ── Per-Greek assessments ──────────────────────────────────────────────────────

def assess_delta(value: float, flag: str) -> Assessment:
    abs_d = abs(value)
    direction = 'call' if flag == 'c' else 'put'
    move_dir  = 'upward' if flag == 'c' else 'downward'

    if abs_d >= 0.80:
        return Assessment(
            level='extreme',
            headline='Deep In-the-Money — Near-Stock Exposure',
            detail=(
                f'This {direction} has a delta of {value:.2f}, meaning it moves '
                f'~${abs_d:.0%} for every $1 the stock moves {move_dir}. '
                'It behaves almost like owning the stock itself, with very little '
                'time-value cushion. Gains and losses track the stock closely — '
                'capital at risk is high.'
            ),
        )
    elif abs_d >= 0.60:
        return Assessment(
            level='high',
            headline='In-the-Money — Strong Directional Exposure',
            detail=(
                f'Delta of {value:.2f} means this {direction} captures about {abs_d:.0%} '
                'of each $1 the stock moves. You have strong directional exposure — a $1 '
                f'adverse move costs roughly ${abs_d:.2f} on this option. '
                'Best suited for traders with high conviction on direction.'
            ),
        )
    elif abs_d >= 0.40:
        return Assessment(
            level='normal',
            headline='Near At-the-Money — Balanced Risk/Reward',
            detail=(
                f'Delta of {value:.2f} is typical for at-the-money options and represents '
                f'roughly {abs_d:.0%} participation in the stock\'s move. '
                'This is the most actively traded range and balances premium cost '
                'with directional leverage.'
            ),
        )
    elif abs_d >= 0.15:
        return Assessment(
            level='notable',
            headline='Out-of-the-Money — Lower Probability, Higher Leverage',
            detail=(
                f'Delta of {value:.2f} indicates an out-of-the-money {direction}. '
                'The stock needs a significant move to make this profitable at expiration. '
                'Lower cost but lower probability of profit — often used for speculative '
                'bets or as cheap protection against large moves.'
            ),
        )
    else:
        return Assessment(
            level='low',
            headline='Deep Out-of-the-Money — Very Low Probability',
            detail=(
                f'Delta of {value:.2f} is very low — the stock needs a large move '
                'for this option to have value at expiration. Very cheap to buy, '
                'but the probability of finishing in-the-money is slim. '
                'High risk of losing the entire premium paid.'
            ),
        )


def assess_gamma(value: float) -> Assessment:
    if value >= 0.060:
        return Assessment(
            level='extreme',
            headline='Extreme Gamma — Rapid Delta Acceleration',
            detail=(
                f'Gamma of {value:.4f} is very high, typical for near-expiry '
                'at-the-money options. Delta is shifting rapidly — a small stock '
                'move causes a large change in how much the option responds to '
                'further moves. This amplifies both gains and losses unpredictably. '
                'Option sellers face the most danger here (known as "short gamma risk").'
            ),
        )
    elif value >= 0.030:
        return Assessment(
            level='high',
            headline='Elevated Gamma — Accelerating Price Sensitivity',
            detail=(
                f'Gamma of {value:.4f} is above average. For every $1 the stock moves, '
                f'delta shifts by ~{value:.2f}. Buyers benefit — delta grows in their favor '
                'as the option moves in-the-money. Sellers bear increasing risk as '
                'the option nears the strike price.'
            ),
        )
    elif value >= 0.010:
        return Assessment(
            level='normal',
            headline='Normal Gamma — Stable Price Sensitivity',
            detail=(
                f'Gamma of {value:.4f} is within the typical range. Delta is changing '
                'at a moderate, predictable pace. No unusual acceleration of risk — '
                'the option responds to stock moves in a fairly stable way.'
            ),
        )
    elif value >= 0.003:
        return Assessment(
            level='notable',
            headline='Low Gamma — Slow Delta Response',
            detail=(
                f'Gamma of {value:.4f} is relatively low, common for deep in- or '
                'out-of-the-money options, or options with a long time until expiration. '
                'Delta changes slowly, so the option\'s price sensitivity is fairly fixed '
                'for small stock moves.'
            ),
        )
    else:
        return Assessment(
            level='low',
            headline='Very Low Gamma — Nearly Fixed Delta',
            detail=(
                f'Gamma of {value:.4f} is very small — delta is nearly constant regardless '
                'of small stock moves. Common for deep out-of-the-money options or '
                'long-dated LEAPs where time to expiry dominates the pricing.'
            ),
        )


def assess_theta(value: float) -> Assessment:
    abs_t = abs(value)

    if abs_t >= 0.30:
        return Assessment(
            level='extreme',
            headline='Extreme Time Decay — Rapidly Losing Value',
            detail=(
                f'Theta of {value:.4f} means this option is losing ~${abs_t:.2f} '
                'per calendar day from time decay alone. Holding this option over a '
                f'3-day weekend costs ~${abs_t * 3:.2f}. Common for near-expiry '
                'at-the-money options. Buyers must see a quick, favorable stock move '
                'to overcome this daily drain.'
            ),
        )
    elif abs_t >= 0.10:
        return Assessment(
            level='high',
            headline='High Time Decay — Significant Daily Cost',
            detail=(
                f'Theta of {value:.4f} means approximately ${abs_t:.2f} is lost '
                'per day to time decay. Sellers benefit from collecting this; '
                'buyers need the stock to move in their favor relatively quickly. '
                'The closer to expiration, the faster theta accelerates.'
            ),
        )
    elif abs_t >= 0.03:
        return Assessment(
            level='normal',
            headline='Normal Time Decay',
            detail=(
                f'Theta of {value:.4f} represents typical decay of ~${abs_t:.2f}/day. '
                'Standard for most options contracts. Remember: time decay '
                'accelerates as expiration approaches, so check theta again '
                'in the final weeks before expiry.'
            ),
        )
    elif abs_t >= 0.01:
        return Assessment(
            level='notable',
            headline='Low Time Decay — Slow Erosion',
            detail=(
                f'Theta of {value:.4f} is low — only ~${abs_t:.2f} lost per day. '
                'Common for longer-dated options where time value erodes gradually. '
                'Less urgency for buyers to see a quick move, but monitor theta '
                'as expiration nears — it will accelerate.'
            ),
        )
    else:
        return Assessment(
            level='low',
            headline='Very Low Time Decay',
            detail=(
                f'Theta of {value:.4f} is negligible — barely any daily time decay. '
                'Typically seen in very long-dated options (LEAPs) or deep in-the-money '
                'options whose value is mostly intrinsic. Time decay is not a '
                'primary concern here.'
            ),
        )


def assess_vega(value: float) -> Assessment:
    if value >= 0.40:
        return Assessment(
            level='extreme',
            headline='Extreme Vega — Very High IV Sensitivity',
            detail=(
                f'Vega of {value:.4f} means a 1% change in implied volatility moves '
                f'this option by ~${value:.2f}. This option is highly sensitive to '
                'market-sentiment shifts. Watch for IV crush: after an earnings report '
                'or major announcement, volatility often collapses, causing large losses '
                'even if the stock moved in the right direction.'
            ),
        )
    elif value >= 0.20:
        return Assessment(
            level='high',
            headline='High Vega — Elevated IV Sensitivity',
            detail=(
                f'Vega of {value:.4f}: a 1% rise in implied volatility adds ~${value:.2f}; '
                'a 1% drop removes the same. Meaningful exposure to volatility swings. '
                'Watch for upcoming events (earnings, Fed decisions) that could trigger '
                'an IV spike before the event and a crush immediately after.'
            ),
        )
    elif value >= 0.05:
        return Assessment(
            level='normal',
            headline='Normal Vega — Moderate IV Sensitivity',
            detail=(
                f'Vega of {value:.4f} is typical — a 1% IV change moves the option '
                f'~${value:.2f}. Standard volatility sensitivity. IV tends to rise before '
                'major events and fall after, so be aware of any upcoming catalysts '
                'that could move implied volatility.'
            ),
        )
    else:
        return Assessment(
            level='low',
            headline='Low Vega — Minimal IV Sensitivity',
            detail=(
                f'Vega of {value:.4f} is low — implied volatility changes have little '
                'impact on this option\'s price. Common for deep in- or out-of-the-money '
                'options or very short-dated contracts. IV risk is not a primary concern here.'
            ),
        )


def assess_rho(value: float) -> Assessment:
    abs_r = abs(value)

    if abs_r >= 0.25:
        return Assessment(
            level='high',
            headline='High Rate Sensitivity',
            detail=(
                f'Rho of {value:.4f} means a 1% change in interest rates moves this '
                f'option ~${abs_r:.2f}. Long-dated options carry the most rate sensitivity. '
                'In a rising-rate environment, calls gain and puts lose from rho. '
                'If you\'re holding through a Federal Reserve meeting, this is worth noting.'
            ),
        )
    elif abs_r >= 0.08:
        return Assessment(
            level='notable',
            headline='Moderate Rate Sensitivity',
            detail=(
                f'Rho of {value:.4f} — a 1% rate change moves this option ~${abs_r:.2f}. '
                'A secondary concern compared to delta and theta, but relevant if holding '
                'through a Fed rate decision. For most short-term trades, rho is minor.'
            ),
        )
    else:
        return Assessment(
            level='normal',
            headline='Low Rate Sensitivity — Normal for Short-Term Options',
            detail=(
                f'Rho of {value:.4f} is low, as expected for short-dated contracts. '
                'Interest rate changes have minimal impact here. Rho matters most for '
                'long-dated options (LEAPs) in volatile rate environments.'
            ),
        )


# ── Convenience functions ──────────────────────────────────────────────────────

def assess_all(greeks: dict, flag: str) -> dict[str, Assessment]:
    dispatchers = {
        'delta': lambda v: assess_delta(v, flag),
        'gamma': assess_gamma,
        'theta': assess_theta,
        'vega':  assess_vega,
        'rho':   assess_rho,
    }
    return {
        key: dispatchers[key](val)
        for key, val in greeks.items()
        if val is not None and key in dispatchers
    }


def chain_signals(greeks: dict, flag: str) -> str:
    """Compact emoji flags for chain table rows — only surfaces high/extreme."""
    assessments = assess_all(greeks, flag)
    symbols = {'delta': 'Δ', 'gamma': 'Γ', 'theta': 'Θ', 'vega': 'V', 'rho': 'ρ'}
    flags = []
    for key, sym in symbols.items():
        a = assessments.get(key)
        if a and a.level == 'extreme':
            flags.append(f'🔴{sym}')
        elif a and a.level == 'high':
            flags.append(f'🟠{sym}')
    return ' '.join(flags)
