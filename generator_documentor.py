"""
Documented Formulas Generator
----------------------------------
Implements three fully-specified alpha formulas found via research,
reported as passing all BRAIN in-sample checks. Uses confirmed-real
operator names (ts_decay_linear, ts_av_diff — verified against BRAIN's
actual operator list, not the unverified 'decay_linear' naming from an
untrusted pasted source).

All three are price/volume based (except the debt composite), making
them structurally different from every fundamental-ratio alpha run
tonight — genuine diversification, not just a new field.

1. VWAP Decay Reversal: rank(ts_decay_linear(close/vwap, N))
2. Returns-Volume Momentum: rank(ts_decay_linear(returns*volume/adv20, N))
3. Debt-Momentum Composite: rank(ts_av_diff(close, N)) + rank(debt_field/cap)
   (using fn_debt_instrument_face_amount_a/cap as a stand-in for
   'enterprise_value', which isn't a raw BRAIN field — it's normally
   computed, not looked up directly)

Usage:
    python generator_documented.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")
DEBT_FIELD = "fn_debt_instrument_face_amount_a"  # already confirmed real and working


def generate_candidates() -> list:
    candidates = []

    # 1. VWAP Decay Reversal
    for window in [5, 10, 15, 20]:
        expr = f"-1 * rank(ts_decay_linear(close / vwap, {window}))"
        candidates.append({
            "expression": expr,
            "template": "vwap_decay_reversal",
            "field": "close",
            "field_type": "price_volume",
            "neutralization": "SUBINDUSTRY",
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 0,
            "truncation": 0.08,
            "source_cluster": "documented_vwap_decay",
        })

    # 2. Returns-Volume Momentum
    for window in [3, 5, 8, 10]:
        expr = f"-1 * rank(ts_decay_linear(returns * volume / adv20, {window}))"
        candidates.append({
            "expression": expr,
            "template": "returns_volume_momentum",
            "field": "returns",
            "field_type": "price_volume",
            "neutralization": "MARKET",
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 0,
            "truncation": 0.08,
            "source_cluster": "documented_returns_volume",
        })

    # 3. Debt-Momentum Composite
    for window in [5, 10, 20]:
        expr = f"rank(ts_av_diff(close, {window})) + rank({DEBT_FIELD}/cap)"
        candidates.append({
            "expression": expr,
            "template": "debt_momentum_composite",
            "field": DEBT_FIELD,
            "field_type": "composite",
            "neutralization": "INDUSTRY",
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 0,
            "truncation": 0.08,
            "source_cluster": "documented_debt_momentum",
        })

    print(f"Generated {len(candidates)} candidates across 3 documented formulas.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [{c['template']}] {c['expression']}")
        