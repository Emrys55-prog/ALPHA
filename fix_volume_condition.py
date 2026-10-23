"""
Volume-Conditional Reversal Fix
------------------------------------
trade_when(volume > adv20, -ts_delta(close, 5), -1) hit Sharpe 1.42,
Fitness 0.94 — close miss, only short on Fitness. Testing nearby windows
and a couple of decay values to find a combination that pushes Fitness
over 1.0 without losing the Sharpe.

Usage:
    python fix_volume_conditional.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

WINDOWS = [3, 4, 6, 7, 8]  # 5 was the near-miss, testing around it
DECAYS = [2, 4, 6]
VOLUME_MULTIPLIERS = [1.0, 1.5]  # stricter trigger = fewer, higher-conviction
                                  # trades, often raises Fitness at some turnover cost


def generate_candidates() -> list:
    candidates = []
    for window in WINDOWS:
        for decay in DECAYS:
            for mult in VOLUME_MULTIPLIERS:
                condition = "volume > adv20" if mult == 1.0 else f"volume > (adv20 * {mult})"
                expr = f"trade_when({condition}, -ts_delta(close, {window}), -1)"
                candidates.append({
                    "expression": expr,
                    "template": "volume_conditional_fix",
                    "field": "close",
                    "field_type": "technique",
                    "window": window,
                    "neutralization": "SUBINDUSTRY",
                    "universe": "TOP3000",
                    "region": "USA",
                    "delay": 1,
                    "decay": decay,
                    "truncation": 0.08,
                    "source_cluster": "fix_volume_conditional",
                })

    print(f"Generated {len(candidates)} volume-conditional fix candidates "
          f"({len(WINDOWS)} windows x {len(DECAYS)} decays x {len(VOLUME_MULTIPLIERS)} volume thresholds).")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates[:6]:
        print(f"  [window={c['window']}, decay={c['decay']}] {c['expression']}")