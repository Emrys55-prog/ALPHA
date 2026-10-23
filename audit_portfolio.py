"""
Portfolio Audit
-------------------
Checks real pairwise correlation across your actual submitted alphas,
by ID, straight from BRAIN — regardless of which folder or method
(pipeline or manual) created each one. This is the tool for "is my
whole live portfolio actually diversified", not just one batch.

Usage:
    Edit ALPHA_IDS below with every ID from your Submitted tab
    (platform > Alphas > Submitted — bump Page size to see all of
    them at once), then run:

    python audit_portfolio.py
"""

import json
import time
from pathlib import Path

from auth import WQSession
from alpha_db import fetch_pnl  # reuse the same PnL-fetching logic

# Paste every alpha ID from your Submitted tab here.
ALPHA_IDS = [
    "j2Aqo3EQ",
"KPN1AwbN",
"YPbex10o",
"Xgb31gk1",
"3qXKxj7z",
"58zK7Nm6",
"O0NXv7vd",
"KPNMeQNz",
"d5bPr55E",
"KPNZmO31",
"levGXGXx",
"RRV2pzxo",
"akLAdeo1",
"pwj81Jl3",
"P07X6Wg7",
"Xg7PKQjl"
    # add the rest — every ID visible in your Submitted table
]

CORRELATION_THRESHOLD = 0.7
OUT_FILE = Path("portfolio_audit.json")


def get_alpha_info(session, alpha_id: str) -> dict:
    resp = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}")
    if resp.status_code != 200:
        return {}
    data = resp.json()
    return {
        "expression": data.get("regular", {}).get("code", "?"),
        "sharpe": data.get("is", {}).get("sharpe"),
        "fitness": data.get("is", {}).get("fitness"),
    }


def to_daily_returns(cum_pnl):
    return [cum_pnl[i + 1] - cum_pnl[i] for i in range(len(cum_pnl) - 1)]


def main():
    if len(ALPHA_IDS) < 2:
        print("Add at least 2 alpha IDs to ALPHA_IDS in this file first.")
        return

    session = WQSession()
    session.login()

    info = {}
    returns = {}
    for aid in ALPHA_IDS:
        print(f"Fetching {aid}...")
        info[aid] = get_alpha_info(session.session, aid)
        pnl = fetch_pnl(session.session, aid, debug=False)
        if pnl:
            returns[aid] = to_daily_returns(pnl)
        else:
            print(f"  Could not fetch PnL for {aid} — skipping in correlation check.")
        time.sleep(1)

    ids = list(returns.keys())
    flagged = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = returns[ids[i]], returns[ids[j]]
            n = min(len(a), len(b))
            if n < 10:
                continue
            a, b = a[:n], b[:n]
            mean_a, mean_b = sum(a) / n, sum(b) / n
            cov = sum((a[k] - mean_a) * (b[k] - mean_b) for k in range(n))
            std_a = sum((x - mean_a) ** 2 for x in a) ** 0.5
            std_b = sum((x - mean_b) ** 2 for x in b) ** 0.5
            if std_a == 0 or std_b == 0:
                continue
            corr = cov / (std_a * std_b)
            if abs(corr) >= CORRELATION_THRESHOLD:
                flagged.append((ids[i], ids[j], corr))

    print(f"\n{'='*60}")
    print(f"Checked {len(ids)} alphas. {len(flagged)} pair(s) above {CORRELATION_THRESHOLD} correlation:")
    for a, b, corr in flagged:
        print(f"\n  corr={corr:.2f}")
        print(f"    {a}: {info[a]['expression']} (Sharpe {info[a]['sharpe']})")
        print(f"    {b}: {info[b]['expression']} (Sharpe {info[b]['sharpe']})")

    if not flagged:
        print("\nNo dangerously correlated pairs found among fetchable alphas.")

    json.dump({"info": info, "flagged": flagged}, open(OUT_FILE, "w"), indent=2)
    print(f"\nFull detail saved to {OUT_FILE}")


if __name__ == "__main__":
    main()