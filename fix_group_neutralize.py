"""
Group-Neutralize Fix (fallback from vector_neut, which errored as
"inaccessible or unknown operator" on this account tier)
-------------------------------------------------------------------------
Same goal as the vector_neut attempt: strip out the component of the
signal driven by company size/group membership before ranking, to fix
leKOMONA's narrow LOW_SUB_UNIVERSE_SHARPE miss (0.6 vs 0.67).
group_neutralize is the more basic, widely-accessible neutralization
operator — reassigns alpha <- alpha - mean(alpha) within each group.

Usage:
    python fix_group_neutralize.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "exercisable_options_avg_exercise_price_2"
WINDOWS = [3, 5, 8]
NEUTRALIZATION = "SUBINDUSTRY"


def generate_candidates() -> list:
    candidates = []

    for window in WINDOWS:
        # Fix 1: group_neutralize by subindustry before the outer ranking
        candidates.append({
            "expression": f"group_rank(group_neutralize(ts_rank({FIELD}, {window}), subindustry), subindustry)",
            "template": "group_neutralize_subind",
            "field": FIELD,
            "field_type": "options",
            "window": window,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 6,
            "truncation": 0.08,
            "source_cluster": "fix_leKOMONA_group_neutralize",
        })
        # Fix 2: same, but neutralize by market instead (broader group)
        candidates.append({
            "expression": f"group_rank(group_neutralize(ts_rank({FIELD}, {window}), market), subindustry)",
            "template": "group_neutralize_market",
            "field": FIELD,
            "field_type": "options",
            "window": window,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 6,
            "truncation": 0.08,
            "source_cluster": "fix_leKOMONA_group_neutralize",
        })

    print(f"Generated {len(candidates)} group-neutralize fix candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [{c['template']}] {c['expression']}")
        