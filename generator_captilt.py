"""
Cap-Tilted Follow-up Generator
----------------------------------
Diagnosed via diagnose_subuniverse.py: group_rank(-ts_delta(operating_income,
5), subindustry) genuinely depends on smaller/illiquid names (Sharpe 1.96 on
TOP3000 drops to 0.74 on TOP1000) — that's why it failed BRAIN's
LOW_SUB_UNIVERSE_SHARPE check even with a strong headline Sharpe.

This tries several ways to tilt the same core idea toward larger, more
liquid stocks instead of discarding it:
  1. Multiply by rank(cap) — directly weight toward large caps
  2. trade_when filter — only trade the larger-cap half of the universe
  3. Weight the raw field by cap before ranking within group

Usage:
    python generator_captilt.py
"""

import json
from pathlib import Path

FIELD_CACHE = Path("field_cache/fields_USA_TOP3000_d1.json")
CANDIDATES_OUT = Path("candidates.json")

BASE_FIELD = "operating_income"
WINDOWS = [3, 5, 8]  # 3 and 5 were the strongest windows so far
NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY"]

CAP_FIELD_KEYWORDS = ["cap", "market_value", "mkt_cap", "market_cap"]


def find_cap_field() -> str:
    """Find a market-cap-like field in the cache. Falls back to the
    common convention 'cap' if the cache isn't available or nothing matches —
    that field name is standard across most BRAIN datasets."""
    if not FIELD_CACHE.exists():
        return "cap"

    fields = json.loads(FIELD_CACHE.read_text())
    for f in fields:
        fid = f.get("id", "").lower()
        if fid == "cap":
            return "cap"

    for f in fields:
        fid = f.get("id", "").lower()
        desc = (f.get("description") or "").lower()
        if any(kw in fid for kw in CAP_FIELD_KEYWORDS) or "market cap" in desc:
            return f["id"]

    print("Warning: no market-cap field found in cache, defaulting to 'cap' "
          "(standard field name in most BRAIN datasets — will fail fast in "
          "simulate.py if it's actually not available on your account).")
    return "cap"


def generate_captilt_candidates() -> list[dict]:
    cap_field = find_cap_field()
    print(f"Using cap field: {cap_field}")

    candidates = []
    for window in WINDOWS:
        for neut in NEUTRALIZATIONS:
            base = f"group_rank(-ts_delta({BASE_FIELD}, {window}), subindustry)"

            variants = [
                {
                    "name": "cap_multiply",
                    "expression": f"{base} * rank({cap_field})",
                },
                {
                    "name": "cap_trade_when_top_half",
                    "expression": f"trade_when(rank({cap_field}) > 0.5, {base}, -1)",
                },
                {
                    "name": "cap_weighted_before_rank",
                    "expression": f"group_rank(-ts_delta({BASE_FIELD}, {window}) * rank({cap_field}), subindustry)",
                },
            ]

            for v in variants:
                candidates.append({
                    "expression": v["expression"],
                    "template": v["name"],
                    "field": BASE_FIELD,
                    "field_type": "fundamental",
                    "window": window,
                    "neutralization": neut,
                    "universe": "TOP3000",
                    "region": "USA",
                    "delay": 1,
                    "source_cluster": "operating_income_captilt",
                })

    print(f"Generated {len(candidates)} cap-tilted candidates "
          f"({len(WINDOWS)} windows x {len(NEUTRALIZATIONS)} neutralizations x 3 tilt approaches).")

    return candidates


if __name__ == "__main__":
    candidates = generate_captilt_candidates()

    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")

    print("Preview:")
    for c in candidates:
        print(f"  [{c['template']}] {c['expression']}  (neut={c['neutralization']})")