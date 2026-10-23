"""
Stage 5: Qualification Filtering
-----------------------------------
Reads results.json from Stage 4 and filters/ranks candidates against
BRAIN's qualification thresholds (same shape as what you've been
checking manually: Sharpe, Fitness, Turnover, Drawdown, and the raw
per-check pass/fail list BRAIN returns).

Nothing in this stage submits anything — it's pure filtering/reporting.
Output is qualified.json: a ranked shortlist for you to review before
Stage 6 (correlation/de-dup) and Stage 7 (actual submission).

Usage:
    python qualify.py
"""

import json
from pathlib import Path

RESULTS_IN = Path("results.json")
QUALIFIED_OUT = Path("qualified.json")
WATCHLIST_OUT = Path("watchlist.json")

# Same thresholds you've been using to judge results manually:
# Sharpe > 1.25, Fitness >= 1.0 = "Average" or better.
# Turnover between 1-70% is BRAIN's general acceptable range.
# Drawdown isn't a hard gate here, just tracked for ranking.
# BRAIN's real thresholds, confirmed directly from a live 403 rejection
# response: LOW_SHARPE limit=1.25, LOW_FITNESS limit=1.0, LOW_TURNOVER
# limit=0.01, HIGH_TURNOVER limit=0.7. Our earlier guess of Sharpe >= 1.0
# was too loose — this is what BRAIN actually enforces.
MIN_SHARPE = 1.25
MIN_FITNESS = 1.0
MIN_TURNOVER_PCT = 1.0
MAX_TURNOVER_PCT = 70.0

# Watchlist tier: looser bar for "close but not there yet" candidates,
# worth revisiting with a focused follow-up batch rather than discarding.
WATCHLIST_MIN_SHARPE = 0.9
WATCHLIST_MIN_FITNESS = 0.8


def classify(result: dict) -> dict:
    """Attach a qualification verdict and reasons to a single result."""
    reasons = []

    sharpe = result.get("sharpe")
    fitness = result.get("fitness")
    turnover = result.get("turnover")

    if sharpe is None or fitness is None:
        return {**result, "qualifies": False, "reasons": ["missing stats"]}

    if abs(sharpe) < MIN_SHARPE:
        reasons.append(f"Sharpe {sharpe} below {MIN_SHARPE}")
    if fitness < MIN_FITNESS:
        reasons.append(f"Fitness {fitness} below {MIN_FITNESS}")
    if turnover is not None:
        turnover_pct = turnover * 100 if turnover < 1 else turnover
        if not (MIN_TURNOVER_PCT <= turnover_pct <= MAX_TURNOVER_PCT):
            reasons.append(f"Turnover {turnover_pct:.1f}% outside {MIN_TURNOVER_PCT}-{MAX_TURNOVER_PCT}%")

    checks_passed = result.get("checks_passed", 0)
    checks_total = result.get("checks_total", 0)
    if checks_total and checks_passed / checks_total < 0.5:
        reasons.append(f"Only {checks_passed}/{checks_total} BRAIN checks passed")

    # Note: this local filter can't see LOW_SUB_UNIVERSE_SHARPE (its limit
    # varies per-alpha and only comes back from BRAIN itself) — a candidate
    # can pass every check here and still get rejected on submission for
    # that reason, as happened with akbxEmxw. Stage 7's submit.py surfaces
    # it directly when that happens.

    qualifies = len(reasons) == 0

    # Watchlist: didn't clear the full bar, but not far off either.
    on_watchlist = False
    if not qualifies and abs(sharpe) >= WATCHLIST_MIN_SHARPE and fitness >= WATCHLIST_MIN_FITNESS:
        on_watchlist = True

    return {**result, "qualifies": qualifies, "on_watchlist": on_watchlist, "reasons": reasons}


def qualify_all() -> list[dict]:
    if not RESULTS_IN.exists():
        raise SystemExit(f"{RESULTS_IN} not found — run simulate.py first.")

    results = json.loads(RESULTS_IN.read_text())
    succeeded = [r for r in results if r.get("status") == "SUCCESS"]
    failed = [r for r in results if r.get("status") != "SUCCESS"]

    classified = [classify(r) for r in succeeded]

    # Rank by a simple composite: Sharpe * Fitness (both matter,
    # penalizes anything weak in either dimension)
    def score(r):
        s, f = r.get("sharpe") or 0, r.get("fitness") or 0
        return s * f

    classified.sort(key=score, reverse=True)

    qualified = [r for r in classified if r["qualifies"]]
    watchlist = [r for r in classified if r["on_watchlist"]]
    rejected = [r for r in classified if not r["qualifies"] and not r["on_watchlist"]]

    print(f"Total candidates: {len(results)}")
    print(f"  Simulation failed (syntax/field errors): {len(failed)}")
    print(f"  Rejected outright: {len(rejected)}")
    print(f"  WATCHLIST (close but not qualifying): {len(watchlist)}")
    print(f"  QUALIFIED: {len(qualified)}\n")

    if qualified:
        print("Qualified candidates, ranked by Sharpe x Fitness:")
        for r in qualified:
            print(f"  [{score(r):.2f}] {r['expression']}")
            print(f"      Sharpe={r['sharpe']}  Fitness={r['fitness']}  "
                  f"Turnover={r.get('turnover')}  Checks={r['checks_passed']}/{r['checks_total']}  "
                  f"alpha_id={r.get('alpha_id')}")

    if watchlist:
        print("\nWatchlist (worth a focused follow-up batch):")
        for r in watchlist:
            print(f"  [{score(r):.2f}] {r['expression']}  (field: {r.get('field')})")
            print(f"      Sharpe={r['sharpe']}  Fitness={r['fitness']}  reasons: {r['reasons']}")

    if not qualified and not watchlist:
        print("Nothing cleared either bar this round. Closest misses:")
        for r in classified[:5]:
            print(f"  {r['expression']}")
            print(f"      Sharpe={r['sharpe']}  Fitness={r['fitness']}  reasons: {r['reasons']}")

    QUALIFIED_OUT.write_text(json.dumps(qualified, indent=2))
    WATCHLIST_OUT.write_text(json.dumps(watchlist, indent=2))
    print(f"\nSaved {len(qualified)} qualified -> {QUALIFIED_OUT}")
    print(f"Saved {len(watchlist)} watchlist -> {WATCHLIST_OUT}")

    return qualified, watchlist


if __name__ == "__main__":
    qualify_all()