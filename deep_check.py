"""
Deep Check
-------------
qualify.py only checks Sharpe/Fitness/Turnover locally — it can't see
LOW_SUB_UNIVERSE_SHARPE, CONCENTRATED_WEIGHT, or SELF_CORRELATION,
which only exist as live BRAIN checks. This fetches those checks for
every qualified/watchlist candidate automatically — READ ONLY, nothing
gets submitted — so you see the real picture before ever touching
submit.py.

Usage:
    python deep_check.py
"""

import json
import time
from pathlib import Path

from auth import WQSession

BRAIN_API_BASE = "https://api.worldquantbrain.com"
QUALIFIED_IN = Path("qualified.json")
WATCHLIST_IN = Path("watchlist.json")
DEEP_CHECKED_OUT = Path("deep_checked.json")

# Checks that qualify.py can't see locally — these are what actually
# block submission most of the time, based on tonight's pattern.
CRITICAL_CHECKS = ["LOW_SUB_UNIVERSE_SHARPE", "CONCENTRATED_WEIGHT", "SELF_CORRELATION"]


def fetch_alpha(session, alpha_id: str) -> dict:
    resp = session.get(f"{BRAIN_API_BASE}/alphas/{alpha_id}")
    if resp.status_code != 200:
        return {}
    return resp.json()


def deep_check_all() -> None:
    candidates = []
    for path in (QUALIFIED_IN, WATCHLIST_IN):
        if path.exists():
            try:
                candidates.extend(json.loads(path.read_text()))
            except json.JSONDecodeError:
                pass

    if not candidates:
        print("No qualified or watchlist candidates to deep-check.")
        return

    print(f"Deep-checking {len(candidates)} candidates against live BRAIN "
          f"checks (read-only, nothing will be submitted)...\n")

    session = WQSession()
    session.login()

    results = []
    for c in candidates:
        alpha_id = c.get("alpha_id")
        if not alpha_id:
            continue

        alpha = fetch_alpha(session.session, alpha_id)
        checks = alpha.get("is", {}).get("checks", [])
        critical_results = {name: next(
            (ch.get("result") for ch in checks if ch.get("name") == name), "UNKNOWN"
        ) for name in CRITICAL_CHECKS}

        # PENDING only applies meaningfully to SELF_CORRELATION (it can't
        # be known until actual submission) — treat that as "unknown but
        # not blocking", while an actual FAIL on any of these is real.
        blocking_fails = [name for name, result in critical_results.items()
                           if result == "FAIL"]

        status = "LIKELY SUBMITTABLE" if not blocking_fails else f"BLOCKED: {', '.join(blocking_fails)}"

        print(f"{c['expression'][:70]}")
        print(f"  Sharpe={c.get('sharpe')} Fitness={c.get('fitness')} | {status}")
        for name, result in critical_results.items():
            print(f"    [{result}] {name}")
        print()

        results.append({
            **c,
            "deep_check": critical_results,
            "likely_submittable": not blocking_fails,
        })

        time.sleep(1)

    DEEP_CHECKED_OUT.write_text(json.dumps(results, indent=2))

    submittable = [r for r in results if r["likely_submittable"]]
    print(f"{'='*60}")
    print(f"{len(submittable)}/{len(results)} candidates look genuinely submittable.")
    print(f"Full detail saved to {DEEP_CHECKED_OUT}")
    if submittable:
        print("\nWorth reviewing with submit.py before confirming:")
        for r in submittable:
            print(f"  python submit.py {r['alpha_id']}")


if __name__ == "__main__":
    deep_check_all()