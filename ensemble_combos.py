"""
Ensemble Combination Generator
-----------------------------------
Combines your best confirmed-real (but individually weak) signals from
two genuinely different balance-sheet categories — accrued_liabilities_total
(working capital) and the intangible-assets cluster (fixed assets) — on
the theory that averaging two real, low-correlation signals lifts the
combined Sharpe above either one alone.

Usage:
    python ensemble_combos.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")

# Best individual sub-expressions from each cluster, picked by
# Sharpe x Fitness from the two most recent batches.
ACCRUED_LIAB_EXPRS = [
    "rank(ts_zscore(accrued_liabilities_total, 30))",       # Sharpe 0.83, Fitness 1.29
    "group_rank(-ts_delta(accrued_liabilities_total, 5), subindustry)",  # Sharpe 0.72, Fitness 1.23, 6/8 checks
]

INTANGIBLE_EXPRS = [
    "group_rank(-ts_delta(fn_finite_lived_intangible_assets_net_a, 5), subindustry)",  # Sharpe 0.82, Fitness 1.45, 6/8
    "group_rank(ts_rank(fn_intangible_assets_accum_amort_q, 5), subindustry)",          # Sharpe 0.81, Fitness 1.43, 6/8
    "group_rank(-ts_delta(fn_finite_lived_intangible_assets_net_a, 20), subindustry)",  # Sharpe 1.04, Fitness 0.65 (best raw Sharpe)
]

NEUTRALIZATIONS = ["NONE", "SUBINDUSTRY", "INDUSTRY"]


def generate_candidates() -> list[dict]:
    candidates = []

    for a_expr in ACCRUED_LIAB_EXPRS:
        for i_expr in INTANGIBLE_EXPRS:
            combined = f"({a_expr} + {i_expr}) / 2"
            for neut in NEUTRALIZATIONS:
                candidates.append({
                    "expression": combined,
                    "template": "ensemble_avg",
                    "field": "accrued_liabilities_total+fn_finite_lived_intangible_assets",
                    "field_type": "ensemble",
                    "neutralization": neut,
                    "universe": "TOP3000",
                    "region": "USA",
                    "delay": 1,
                    "truncation": 0.08,
                    "source_cluster": "ensemble_working_capital_x_intangibles",
                })

    print(f"Generated {len(candidates)} ensemble candidates "
          f"({len(ACCRUED_LIAB_EXPRS)} accrued-liab variants x "
          f"{len(INTANGIBLE_EXPRS)} intangible variants x "
          f"{len(NEUTRALIZATIONS)} neutralizations).")

    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()

    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")

    print("Preview:")
    for c in candidates[:6]:
        print(f"  [neut={c['neutralization']}] {c['expression']}")