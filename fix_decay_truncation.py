"""
Decay/Truncation Fix (fallback from vector_neut and group_neutralize,
both inaccessible on this account tier)
-------------------------------------------------------------------------
Same original expression that scored Sharpe 1.54 (group_rank(ts_rank(
exercisable_options_avg_exercise_price_2, 5), subindustry)), failing
LOW_SUB_UNIVERSE_SHARPE narrowly (0.6 vs 0.67). This tests decay and
truncation combinations instead — both confirmed accessible (every
simulation tonight has used them), unlike the neutralization operators.

Higher decay smooths the signal over more days, which can reduce how
much a handful of names dominate the resulting positions.

Usage:
    python fix_decay_truncation.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "exercisable_options_avg_exercise_price_2"
WINDOW = 5  # the window that gave Sharpe 1.54 originally
NEUTRALIZATION = "SUBINDUSTRY"
DECAYS = [6, 10, 15, 20]
TRUNCATIONS = [0.08, 0.04, 0.02]


def generate_candidates() -> list:
    candidates = []
    expr = f"group_rank(ts_rank({FIELD}, {WINDOW}), subindustry)"

    for decay in DECAYS:
        for trunc in TRUNCATIONS:
            candidates.append({
                "expression": expr,
                "template": "decay_truncation_fix",
                "field": FIELD,
                "field_type": "options",
                "window": WINDOW,
                "neutralization": NEUTRALIZATION,
                "universe": "TOP3000",
                "region": "USA",
                "delay": 1,
                "decay": decay,
                "truncation": trunc,
                "source_cluster": "fix_leKOMONA_decay_truncation",
            })

    print(f"Generated {len(candidates)} decay/truncation combinations.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [decay={c['decay']}, trunc={c['truncation']}] {c['expression']}")