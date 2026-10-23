"""
Concentration Fix Generator
-------------------------------
wpZoZXX2 (rank(-ts_delta(authorized_option_shares_outstanding_count, 20)))
passed LOW_SUB_UNIVERSE_SHARPE cleanly (1.02) but failed CONCENTRATED_WEIGHT
(0.48 vs limit 0.10) — likely because this field is sparsely reported,
leaving most stocks tied while a handful of real changes get extreme rank
values and outsized weight.

Two fixes tested here:
  1. Lower truncation (0.08 -> 0.02/0.04) — caps max weight per position
     directly, regardless of the underlying tie structure.
  2. ts_backfill the field before ranking — carries the last known value
     forward across reporting gaps, reducing artificial ties.

Usage:
    python fix_concentration.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "authorized_option_shares_outstanding_count"
WINDOW = 20  # the window that worked (Sharpe 1.71, Fitness 2.8)
NEUTRALIZATION = "SUBINDUSTRY"  # confirmed via check_settings.py against wpZoZXX2 —
                                 # the earlier NONE assumption was wrong, which is
                                 # why the first attempt at this fix looked broken
BACKFILL_PERIODS = [60, 120]
TRUNCATIONS = [0.02, 0.04, 0.08]  # 0.08 is the original default, kept as baseline


def generate_candidates() -> list[dict]:
    candidates = []

    # Fix 1: same expression, lower truncation only
    for trunc in TRUNCATIONS:
        candidates.append({
            "expression": f"rank(-ts_delta({FIELD}, {WINDOW}))",
            "template": "truncation_fix",
            "field": FIELD,
            "field_type": "fundamental",
            "window": WINDOW,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "truncation": trunc,
            "source_cluster": "share_issuance_concentration_fix",
        })

    # Fix 2: backfill the sparse field before delta, at default truncation
    for bf in BACKFILL_PERIODS:
        candidates.append({
            "expression": f"rank(-ts_delta(ts_backfill({FIELD}, {bf}), {WINDOW}))",
            "template": "backfill_fix",
            "field": FIELD,
            "field_type": "fundamental",
            "window": WINDOW,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "truncation": 0.08,
            "source_cluster": "share_issuance_concentration_fix",
        })

    # Fix 3: both combined — backfill AND lower truncation
    for bf in BACKFILL_PERIODS:
        for trunc in [0.02, 0.04]:
            candidates.append({
                "expression": f"rank(-ts_delta(ts_backfill({FIELD}, {bf}), {WINDOW}))",
                "template": "backfill_and_truncation_fix",
                "field": FIELD,
                "field_type": "fundamental",
                "window": WINDOW,
                "neutralization": NEUTRALIZATION,
                "universe": "TOP3000",
                "region": "USA",
                "delay": 1,
                "truncation": trunc,
                "source_cluster": "share_issuance_concentration_fix",
            })

    print(f"Generated {len(candidates)} concentration-fix candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()

    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")

    print("Preview:")
    for c in candidates:
        print(f"  [{c['template']}, trunc={c['truncation']}] {c['expression']}")