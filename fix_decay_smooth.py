"""
Decay-Smoothing Concentration Fix
--------------------------------------
Neither lowering truncation nor ts_backfill fixed CONCENTRATED_WEIGHT for
rank(-ts_delta(authorized_option_shares_outstanding_count, 20)) — makes
sense, since this field is a rare corporate-action event (option-share
authorization changes), so on any given day only a handful of stocks show
a real change. Truncation caps position SIZE but doesn't fix the fact
that few stocks have any signal at all on a given day.

This tries a different angle: wrap the delta in ts_decay_linear, so a
detected change's influence gets spread across several subsequent days
instead of spiking sharply on the one day it's detected. Same underlying
information, smoother position sizing over time.

Usage:
    python fix_decay_smooth.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

FIELD = "authorized_option_shares_outstanding_count"
DELTA_WINDOW = 20  # confirmed best window from earlier testing
DECAY_WINDOWS = [5, 8, 10, 15, 20]
NEUTRALIZATION = "SUBINDUSTRY"  # confirmed via check_settings.py against wpZoZXX2


def generate_candidates() -> list[dict]:
    candidates = []

    for decay in DECAY_WINDOWS:
        candidates.append({
            "expression": f"rank(-ts_decay_linear(ts_delta({FIELD}, {DELTA_WINDOW}), {decay}))",
            "template": "decay_smooth_fix",
            "field": FIELD,
            "field_type": "fundamental",
            "window": DELTA_WINDOW,
            "decay_window": decay,
            "neutralization": NEUTRALIZATION,
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "truncation": 0.08,
            "source_cluster": "share_issuance_decay_smooth_fix",
        })

    print(f"Generated {len(candidates)} decay-smoothing candidates.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()

    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")

    print("Preview:")
    for c in candidates:
        print(f"  [decay={c['decay_window']}] {c['expression']}")