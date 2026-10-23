"""
Implied Volatility Decay Sweep
------------------------------------
group_rank(ts_rank(implied_volatility_mean_150, 6), subindustry) peaked
at Sharpe 2.15, Fitness 0.97 — window tuning alone plateaued just under
the Fitness bar. Decay hasn't been tried yet (every earlier candidate
used the default of 6) — it directly affects turnover smoothing, which
feeds into the Fitness calculation, so it's a genuinely different lever
than window size.

Usage:
    python fix_impliedvol_decay.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "implied_volatility_mean_150"
WINDOW = 6  # the peak from the window sweep
DECAYS = [0, 2, 4, 8, 10, 15, 20]
NEUTRALIZATION = "SUBINDUSTRY"


def generate_candidates() -> list:
    candidates = []
    for decay in DECAYS:
        candidates.append({
            "expression": f"group_rank(ts_rank({FIELD}, {WINDOW}), subindustry)",
            "template": "impliedvol_decay_fix",
            "field": FIELD,
            "field_type": "options",
            "window": WINDOW,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": decay,
            "truncation": 0.08,
            "source_cluster": "fix_impliedvol_decay",
        })

    print(f"Generated {len(candidates)} decay-sweep candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [decay={c['decay']}] {c['expression']}")