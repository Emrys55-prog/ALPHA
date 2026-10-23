"""
Machinery Equipment Window Fix
------------------------------------
group_rank(-ts_delta(gross_machinery_equipment_value_2, 5), subindustry)
hit Sharpe 1.33 but Fitness landed at 0.91, just short of 1.0. Testing
nearby windows to find one that holds the Sharpe while clearing Fitness.

Usage:
    python fix_machinery_window.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "gross_machinery_equipment_value_2"
WINDOWS = [10, 12, 15, 18]  # Fitness climbed steadily 3->8 (0.82->0.97) and
                              # hadn't clearly peaked yet — pushing further out
NEUTRALIZATION = "SUBINDUSTRY"


def generate_candidates() -> list:
    candidates = []
    for window in WINDOWS:
        candidates.append({
            "expression": f"group_rank(-ts_delta({FIELD}, {window}), subindustry)",
            "template": "machinery_window_fix",
            "field": FIELD,
            "field_type": "balance_sheet",
            "window": window,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 6,
            "truncation": 0.08,
            "source_cluster": "fix_machinery_window",
        })

    print(f"Generated {len(candidates)} window-fix candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [window={c['window']}] {c['expression']}")