"""
Quick inspection utility: dump every successful result from results.json,
sorted by Sharpe x Fitness, showing which template/field produced it.

Usage:
    python inspect_results.py
"""

import json
from pathlib import Path

results = json.loads(Path("results.json").read_text())
succeeded = [r for r in results if r.get("status") == "SUCCESS"]


def score(r):
    return (r.get("sharpe") or 0) * (r.get("fitness") or 0)


succeeded.sort(key=score, reverse=True)

for r in succeeded:
    print(f"{score(r):.2f} | {r.get('template')} | {r['expression'][:70]} "
          f"| Sharpe: {r.get('sharpe')} | Fitness: {r.get('fitness')}")