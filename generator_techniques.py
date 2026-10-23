"""
Techniques Generator
------------------------
Unlike every other generator here, this doesn't vary the FIELD — it
implements three specific, documented BRAIN techniques found in public
worked examples (a WorldQuant seminar's notes and a GitHub alpha-examples
repo). Different mechanism from anything tried so far, so low
correlation risk with your existing alphas is likely.

1. Price reversal with NO neutralization — a documented finding that,
   for price reversion specifically, no neutralization outperforms
   subindustry (counter to the pattern that's worked for your fundamental
   alphas all night).
2. Volume-conditional close reversal — only trade the reversal signal
   on days where volume exceeds its 20-day average (trade_when), instead
   of trading it every day.
3. Volatility-regime regression reversion — only trade a regression-based
   mean-reversion signal when recent volatility is elevated.

Usage:
    python generator_techniques.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")


def generate_candidates() -> list:
    candidates = []

    # Technique 1: price reversal, NO neutralization, varying the
    # volatility-normalization window
    for std_window in [10, 20, 30]:
        for delay in [1, 2, 3]:
            expr = (f"rank(-(close - ts_delay(close, {delay})) / "
                     f"ts_delay(close, {delay}) / ts_std_dev(returns, {std_window}))")
            candidates.append({
                "expression": expr,
                "template": "price_reversal_no_neut",
                "field": "close",
                "field_type": "technique",
                "neutralization": "NONE",
                "universe": "TOP3000",
                "region": "USA",
                "delay": 1,
                "decay": 0,
                "truncation": 0.08,
                "source_cluster": "technique_price_reversal",
            })

    # Technique 2: volume-conditional close reversal
    for window in [3, 5, 8]:
        expr = f"trade_when(volume > adv20, -ts_delta(close, {window}), -1)"
        candidates.append({
            "expression": expr,
            "template": "volume_conditional_reversal",
            "field": "close",
            "field_type": "technique",
            "neutralization": "SUBINDUSTRY",
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 4,
            "truncation": 0.08,
            "source_cluster": "technique_volume_conditional",
        })

    # Technique 3: volatility-regime regression reversion
    for threshold in [0.5, 0.55, 0.6]:
        for reg_window in [126, 252]:
            expr = (f"trade_when(ts_rank(ts_std_dev(returns, 22), 252) > {threshold}, "
                     f"-ts_regression(returns, ts_delay(returns, 1), {reg_window}), -1)")
            candidates.append({
                "expression": expr,
                "template": "volatility_regime_reversion",
                "field": "returns",
                "field_type": "technique",
                "neutralization": "NONE",
                "universe": "TOP3000",
                "region": "USA",
                "delay": 1,
                "decay": 0,
                "truncation": 0.08,
                "source_cluster": "technique_volatility_regime",
            })

    print(f"Generated {len(candidates)} candidates across 3 techniques "
          f"(price reversal no-neut, volume-conditional reversal, "
          f"volatility-regime regression reversion).")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates[:5]:
        print(f"  [{c['template']}] {c['expression']}")