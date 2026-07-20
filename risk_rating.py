from __future__ import annotations
from dataclasses import dataclass, field

# ── Risk level thresholds (upper bound, label, color) ─────────────────────────
_LEVELS = [
    (20,  'Very Low',      '#4CAF50'),
    (35,  'Low',           '#8BC34A'),
    (50,  'Moderate',      '#FFC107'),
    (65,  'Moderate-High', '#FF9800'),
    (80,  'High',          '#FF5722'),
    (101, 'Very High',     '#F44336'),
]


@dataclass
class RiskProfile:
    score: int
    level: str
    color: str
    # each component: name -> (earned_points, max_points)
    components: dict[str, tuple[int, int]] = field(default_factory=dict)
    drivers: list[str] = field(default_factory=list)
    breakeven_pct: float | None = None   # % stock must move to break even


def score_to_level(score: int) -> tuple[str, str]:
    for threshold, label, color in _LEVELS:
        if score < threshold:
            return label, color
    return 'Very High', '#F44336'


def calculate_option_risk(
    delta:  float | None,
    theta:  float | None,
    vega:   float | None,
    iv:     float | None,
    ask:    float | None,
    flag:   str,
    strike: float | None = None,
    spot:   float | None = None,
) -> RiskProfile:
    """
    Score a long-option position on a 1–100 scale across four risk dimensions.

    Component weights
    -----------------
    Direction / probability   30 pts  — lower |delta| = higher chance of expiring worthless
    Theta burden              25 pts  — daily decay as % of ask; ceiling at 8 %/day
    IV level                  25 pts  — absolute IV; ceiling at 40 %
    Vega sensitivity          20 pts  — vega/ask per 1 % IV move; ceiling at 8 %
    """

    # ── Component 1: Direction / probability of profit (0–30) ────────────────
    if delta is not None:
        abs_d = abs(delta)
        dir_score = round((1.0 - abs_d) * 30)
    else:
        dir_score = 15

    # ── Component 2: Theta burden (0–25) ──────────────────────────────────────
    if theta is not None and ask and ask > 0:
        theta_pct = abs(theta) / ask
        theta_score = round(min(theta_pct / 0.08, 1.0) * 25)
    else:
        theta_score = 12

    # ── Component 3: IV level (0–25) ──────────────────────────────────────────
    if iv is not None and iv > 0:
        iv_score = round(min(iv / 0.40, 1.0) * 25)
    else:
        iv_score = 12

    # ── Component 4: Vega sensitivity (0–20) ──────────────────────────────────
    if vega is not None and ask and ask > 0:
        vega_pct = abs(vega) / ask
        vega_score = round(min(vega_pct / 0.08, 1.0) * 20)
    else:
        vega_score = 10

    score = max(1, min(100, dir_score + theta_score + iv_score + vega_score))
    level, color = score_to_level(score)

    # ── Top risk drivers (plain language, surface 0–2 most prominent) ─────────
    ranked = sorted(
        [('direction', dir_score, 30), ('theta', theta_score, 25),
         ('iv', iv_score, 25), ('vega', vega_score, 20)],
        key=lambda x: x[1] / x[2],
        reverse=True,
    )
    drivers: list[str] = []
    for name, s, max_s in ranked:
        if len(drivers) >= 2 or s / max_s < 0.45:
            continue
        if name == 'direction' and delta is not None:
            abs_d = abs(delta)
            if abs_d < 0.40:
                drivers.append(
                    f'OTM position (Δ={delta:.2f}) — ~{(1 - abs_d) * 100:.0f}% '
                    'probability of expiring worthless'
                )
            else:
                drivers.append(
                    f'ITM/ATM position (Δ={delta:.2f}) — strong directional exposure'
                )
        elif name == 'theta' and theta is not None and ask:
            drivers.append(
                f'Time decay of ${abs(theta):.3f}/day '
                f'({abs(theta) / ask * 100:.1f}% of option value per day)'
            )
        elif name == 'iv' and iv is not None:
            drivers.append(
                f'Implied volatility of {iv * 100:.1f}% — '
                'premium reflects high expected price swings'
            )
        elif name == 'vega' and vega is not None and ask:
            drivers.append(
                f'IV sensitivity: option moves ${abs(vega):.3f} per 1% change in '
                'implied volatility'
            )

    # ── Break-even stock move ──────────────────────────────────────────────────
    breakeven_pct = None
    if ask is not None and strike is not None and spot and spot > 0:
        be_price = (strike + ask) if flag == 'c' else (strike - ask)
        breakeven_pct = (be_price - spot) / spot * 100

    return RiskProfile(
        score=score,
        level=level,
        color=color,
        components={
            'direction': (dir_score,   30),
            'theta':     (theta_score, 25),
            'iv':        (iv_score,    25),
            'vega':      (vega_score,  20),
        },
        drivers=drivers,
        breakeven_pct=breakeven_pct,
    )


def tbill_profile(days: int, annual_rate: float) -> dict:
    """Fixed risk-free baseline — always scores 3/100."""
    return {
        'score':         3,
        'level':         'Very Low',
        'color':         '#4CAF50',
        'annual_rate':   annual_rate * 100,
        'period_return': annual_rate * (days / 365) * 100,
        'days':          days,
    }
