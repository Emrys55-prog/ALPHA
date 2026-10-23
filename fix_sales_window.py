"""
Sales Window Fix
-------------------
blbAxE9p (group_rank(-ts_delta(sales, 5), subindustry), Sharpe 1.9) failed
LOW_SUB_UNIVERSE_SHARPE narrowly (0.76 vs 0.82 needed) — a much closer
miss than the operating_income case, and the window-3 sibling
(KPNZmO31) already passed cleanly and went ACTIVE. This tests nearby
windows to find one that keeps a strong headline Sharpe while also
clearing the sub-universe bar, confirmed at the correct SUBINDUSTRY
neutralization (via check_settings.py against blbAxE9p).

Usage:
    python fix_sales_window.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "sales"
WINDOWS = [4, 6, 7, 8, 10]  # 3 is already ACTIVE (KPNZmO31), 5 was the near-miss —
                             # testing the gap between them, not re-testing what's confirmed
NEUTRALIZATION = "SUBINDUSTRY"  # confirmed via check_settings.py


def generate_candidates() -> list[dict]:
    candidates = []
    for window in WINDOWS:
        candidates.append({
            "expression": f"group_rank(-ts_delta({FIELD}, {window}), subindustry)",
            "template": "window_fix",
            "field": FIELD,
            "field_type": "fundamental",
            "window": window,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "truncation": 0.08,
            "source_cluster": "sales_window_fix",
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