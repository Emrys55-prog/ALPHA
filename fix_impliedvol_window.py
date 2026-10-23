"""
Implied Volatility Window Sweep
------------------------------------
group_rank(ts_rank(implied_volatility_mean_150, 8), subindustry) hit
Sharpe 1.99 (best raw Sharpe of the session) but Fitness landed at 0.91.
Sweeping nearby windows to find the real peak, same diagnostic approach
that worked for the machinery-equipment field.

Usage:
    python fix_impliedvol_window.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "implied_volatility_mean_150"
WINDOWS = [3, 5, 6, 7, 10, 12, 15]  # 8 was the near-miss, bracket it both ways
NEUTRALIZATION = "SUBINDUSTRY"


def generate_candidates() -> list:
    candidates = []
    for window in WINDOWS:
        candidates.append({
            "expression": f"group_rank(ts_rank({FIELD}, {window}), subindustry)",
            "template": "impliedvol_window_fix",
            "field": FIELD,
            "field_type": "options",
            "window": window,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 6,
            "truncation": 0.08,
            "source_cluster": "fix_impliedvol_window",
        })

    print(f"Generated {len(candidates)} window-sweep candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [window={c['window']}] {c['expression']}")