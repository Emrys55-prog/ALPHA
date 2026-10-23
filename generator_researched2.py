"""
Researched Formulas, Round 2
---------------------------------
Three specific, documented formulas from independent sources, not
generic keyword-matched templates:

1. "Hot news with reversion" — short stocks with rising after-hours
   buzz vs their 60-day average, else fall back to short-term reversal.
   Cited as performing especially well starting ~March 2020.
2. Sentiment buzz regression — regression-based mean reversion using
   buzz magnitude to predict returns. From a WorldQuant seminar's own
   notes, with specific settings (decay 15, truncation 0.1).
3. Model dataset (CORRECTED prefix: mdl175_, not the mdf_ guessed
   earlier) — revenue trend combined with volatility, a genuinely
   different Model-category signal.

All three use vec_avg to properly aggregate vector-type fields before
other operators — the step that was likely missing from the earlier
failed sentiment attempt.

Usage:
    python generator_researched2.py
"""

import json
from pathlib import Path

CANDIDATES_OUT = Path("candidates.json")


def generate_candidates() -> list:
    candidates = []

    # 1. Hot news with reversion (ternary conditional)
    for window in [40, 60, 80]:
        expr = (f"rank(ts_sum(vec_avg(nws12_afterhsz_sl), {window})) > 0.5 "
                f"? 1 : rank(-ts_delta(close, 2))")
        candidates.append({
            "expression": expr,
            "template": "hot_news_reversion",
            "field": "nws12_afterhsz_sl",
            "field_type": "sentiment_vector",
            "neutralization": "SUBINDUSTRY",
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 3,
            "truncation": 0.01,
            "source_cluster": "researched_hot_news",
        })

    # 2. Sentiment buzz regression
    for reg_window in [60, 120, 180]:
        expr = f"-ts_regression(returns, ts_delay(vec_avg(snt_buzz_ret), 1), {reg_window})"
        candidates.append({
            "expression": expr,
            "template": "sentiment_buzz_regression",
            "field": "snt_buzz_ret",
            "field_type": "sentiment_vector",
            "neutralization": "SUBINDUSTRY",
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 15,
            "truncation": 0.1,
            "source_cluster": "researched_sentiment_regression",
        })

    # 3. Model dataset — corrected prefix (mdl175_, not mdf_)
    for window in [20, 60]:
        # Simple baseline: does this dataset even work for this account?
        candidates.append({
            "expression": f"group_rank(ts_rank(mdl175_revenuettm, {window}), subindustry)",
            "template": "model_dataset_baseline",
            "field": "mdl175_revenuettm",
            "field_type": "model",
            "neutralization": "SUBINDUSTRY",
            "universe": "TOP3000",
            "region": "USA",
            "delay": 1,
            "decay": 6,
            "truncation": 0.08,
            "source_cluster": "researched_model_dataset",
        })
    # Combined version from the documented example
    expr = "rank(-mdl175_volatility * log(volume)) * (1 + group_rank(mdl175_revenuettm, subindustry))"
    candidates.append({
        "expression": expr,
        "template": "model_dataset_combined",
        "field": "mdl175_volatility",
        "field_type": "model",
        "neutralization": "SUBINDUSTRY",
        "universe": "TOP3000",
        "region": "USA",
        "delay": 1,
        "decay": 6,
        "truncation": 0.08,
        "source_cluster": "researched_model_dataset",
    })

    print(f"Generated {len(candidates)} candidates across 3 researched formulas.")
    return candidates


if __name__ == "__main__":
    candidates = generate_candidates()
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")
    print("Preview:")
    for c in candidates:
        print(f"  [{c['template']}] {c['expression'][:80]}")