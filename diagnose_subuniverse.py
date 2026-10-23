"""
Sub-Universe Diagnostic
--------------------------
Tests the exact same expression on a smaller/more liquid universe
(TOP1000 instead of TOP3000) to see whether a LOW_SUB_UNIVERSE_SHARPE
failure reflects real small-cap dependency, or whether the signal
actually holds up fine once BRAIN's own weighting on the smaller
universe is applied directly (as opposed to being diluted within a
TOP3000 simulation).

Usage:
    python diagnose_subuniverse.py "<expression>" <neutralization>

    python diagnose_subuniverse.py "group_rank(-ts_delta(operating_income, 5), subindustry)" SUBINDUSTRY
"""

import sys

from auth import WQSession
from simulate import submit_simulation, poll_simulation, get_alpha_stats


def run_diagnostic(expression: str, neutralization: str, universe: str = "TOP1000") -> None:
    session = WQSession()
    session.login()

    candidate = {
        "expression": expression,
        "neutralization": neutralization,
        "universe": universe,
        "region": "USA",
        "delay": 1,
    }

    print(f"Testing on {universe} (originally failed LOW_SUB_UNIVERSE_SHARPE on TOP3000):")
    print(f"  {expression}\n")

    location = submit_simulation(session.session, candidate)
    print("Submitted, polling for completion...")

    alpha_id = poll_simulation(session.session, location)
    stats = get_alpha_stats(session.session, alpha_id)

    print(f"\nResults on {universe}:")
    print(f"  alpha_id  = {stats['alpha_id']}")
    print(f"  Sharpe    = {stats['sharpe']}")
    print(f"  Fitness   = {stats['fitness']}")
    print(f"  Turnover  = {stats['turnover']}")
    print(f"  Checks    = {stats['checks_passed']}/{stats['checks_total']}")

    print("\nInterpretation:")
    if stats["sharpe"] and stats["sharpe"] >= 1.25:
        print("  Signal HOLDS UP on the smaller/liquid universe — the TOP3000 "
              "sub-universe check failure may be more about weighting/tail "
              "effects than a fundamentally broken idea. Worth trying the "
              "truncation fix before the more involved cap-tilt rewrite.")
    else:
        print("  Signal WEAKENS significantly here too — confirms real "
              "dependency on smaller/illiquid names. The cap-tilted "
              "expression rewrite is likely necessary, not optional.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python diagnose_subuniverse.py "<expression>" <neutralization>')
        sys.exit(1)

    run_diagnostic(sys.argv[1], sys.argv[2])