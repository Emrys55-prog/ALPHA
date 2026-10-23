"""
Vector-Neutralization Fix
------------------------------
leKOMONA (group_rank(ts_rank(exercisable_options_avg_exercise_price_2, 5),
subindustry)) failed LOW_SUB_UNIVERSE_SHARPE narrowly (0.6 vs 0.67 needed).
Per documented BRAIN technique: this check measures whether the edge is
concentrated in a few (often large-cap-dominated) names. vector_neut(signal,
cap) directly strips the market-cap-driven component of the signal before
ranking — a targeted fix, not the blunt truncation/backfill approach that
failed on operating_income earlier tonight.

Usage:
    python fix_vector_neut.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "exercisable_options_avg_exercise_price_2"
WINDOWS = [3, 5, 8]
NEUTRALIZATION = "SUBINDUSTRY"  # confirmed via check_settings.py against leKOMONA


def generate_candidates() -> list:
    candidates = []

    for window in WINDOWS:
        # Primary fix: vector_neut against cap before ranking
        candidates.append({
            "expression": f"group_rank(vector_neut(ts_rank({FIELD}, {window}), cap), subindustry)",
            "template": "vector_neut_cap",
            "field": FIELD,
            "field_type": "options",
            "window": window,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 6,
            "truncation": 0.08,
            "source_cluster": "fix_leKOMONA_vector_neut",
        })
        # Combined: vector_neut + lower truncation, in case both help
        candidates.append({
            "expression": f"group_rank(vector_neut(ts_rank({FIELD}, {window}), cap), subindustry)",
            "template": "vector_neut_cap_lowtrunc",
            "field": FIELD,
            "field_type": "options",
            "window": window,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 6,
            "truncation": 0.03,
            "source_cluster": "fix_leKOMONA_vector_neut",
        })

    print(f"Generated {len(candidates)} vector-neutralization fix candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [{c['template']}, trunc={c['truncation']}] {c['expression']}")