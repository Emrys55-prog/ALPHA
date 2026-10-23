"""
Accessible-Operators-Only Fix
----------------------------------
vector_neut and group_neutralize both errored as inaccessible on this
account tier. Falling back to confirmed-working tools only: the
account-level neutralization SETTING (not an in-expression operator —
this has worked in every successful simulation tonight), lower
truncation, and ts_backfill (already used successfully earlier for a
different sparse-field problem).

Tests exercisable_options_avg_exercise_price_2 across:
  - All 4 neutralization settings (not just SUBINDUSTRY)
  - Lower truncation (0.03 vs the original 0.08)
  - With and without ts_backfill, in case exercise-price data is
    sparse/infrequently updated like the option-shares field was

Usage:
    python fix_accessible.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "exercisable_options_avg_exercise_price_2"
WINDOW = 5  # the window that scored best originally (Sharpe 1.54)
NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY", "MARKET", "NONE"]
TRUNCATIONS = [0.08, 0.03]


def generate_candidates() -> list:
    candidates = []

    for neut in NEUTRALIZATIONS:
        for trunc in TRUNCATIONS:
            # Without backfill
            candidates.append({
                "expression": f"group_rank(ts_rank({FIELD}, {WINDOW}), subindustry)",
                "template": "accessible_neut_trunc",
                "field": FIELD,
                "field_type": "options",
                "window": WINDOW,
                "neutralization": neut,
                "universe": "TOP3000",
                "region": "USA",
                "delay": 1,
                "decay": 6,
                "truncation": trunc,
                "source_cluster": "fix_leKOMONA_accessible",
            })
            # With backfill, in case of sparsity
            candidates.append({
                "expression": f"group_rank(ts_rank(ts_backfill({FIELD}, 60), {WINDOW}), subindustry)",
                "template": "accessible_backfill",
                "field": FIELD,
                "field_type": "options",
                "window": WINDOW,
                "neutralization": neut,
                "universe": "TOP3000",
                "region": "USA",
                "delay": 1,
                "decay": 6,
                "truncation": trunc,
                "source_cluster": "fix_leKOMONA_accessible",
            })

    print(f"Generated {len(candidates)} accessible-operator fix candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [{c['template']}, neut={c['neutralization']}, trunc={c['truncation']}] {c['expression'][:60]}")