"""
Stage 6: Alpha Database + Correlation Check
-----------------------------------------------
Stores every simulated alpha locally in SQLite, so:
  1. We never waste a submission re-simulating an expression we've
     already tried (unique index on expression).
  2. We can compute correlation between candidates using their PnL
     history, and avoid building a "diverse" shortlist that's actually
     just five near-duplicates of the same signal.

Two-step workflow:
    python alpha_db.py import     # load results.json into the DB
    python alpha_db.py correlate  # fetch PnL for DB entries, check correlation

Usage as a library:
    from alpha_db import import_results, check_correlation
"""

import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

from auth import WQSession

BRAIN_API_BASE = "https://api.worldquantbrain.com"
DB_PATH = Path("alphas.db")
RESULTS_IN = Path("results.json")

# Correlation above this is treated as "too similar" — same general
# threshold discussed when we designed this stage: BRAIN's own
# self-correlation check is typically what actually matters, but 0.7
# is a reasonable local screening threshold before you even submit.
CORRELATION_THRESHOLD = 0.7


SCHEMA = """
CREATE TABLE IF NOT EXISTS alphas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expression TEXT NOT NULL UNIQUE,
    alpha_id TEXT,
    field TEXT,
    template TEXT,
    universe TEXT,
    region TEXT,
    neutralization TEXT,
    window INTEGER,
    sharpe REAL,
    fitness REAL,
    turnover REAL,
    drawdown REAL,
    margin REAL,
    checks_passed INTEGER,
    checks_total INTEGER,
    qualifies BOOLEAN DEFAULT 0,
    submitted BOOLEAN DEFAULT 0,
    daily_pnl TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def import_results() -> tuple[int, int]:
    """Load results.json into the DB. Returns (inserted, skipped_duplicates)."""
    if not RESULTS_IN.exists():
        raise SystemExit(f"{RESULTS_IN} not found — run simulate.py first.")

    results = json.loads(RESULTS_IN.read_text())
    conn = get_db()
    inserted, skipped = 0, 0

    for r in results:
        if r.get("status") != "SUCCESS":
            continue
        try:
            conn.execute(
                """INSERT INTO alphas
                   (expression, alpha_id, field, template, universe, region,
                    neutralization, window, sharpe, fitness, turnover, drawdown,
                    margin, checks_passed, checks_total)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.get("expression"), r.get("alpha_id"), r.get("field"),
                    r.get("template"), r.get("universe"), r.get("region"),
                    r.get("neutralization"), r.get("window"),
                    r.get("sharpe"), r.get("fitness"), r.get("turnover"),
                    r.get("drawdown"), r.get("margin"),
                    r.get("checks_passed"), r.get("checks_total"),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            # Expression already in the DB — skip, don't re-simulate later
            skipped += 1

    conn.commit()
    conn.close()
    return inserted, skipped


def fetch_pnl(session: requests.Session, alpha_id: str, debug: bool = False,
              max_wait: int = 60) -> list[float] | None:
    """Pull an alpha's daily PnL series. BRAIN's recordset endpoint returns
    JSON shaped as {"schema": {"properties": [...]}, "records": [[...], ...]}
    — rows are plain lists, with column meaning defined by schema.properties,
    not named keys. It can also come back with an empty body while the
    recordset is still being generated, so we poll briefly like a simulation.
    Returns None if it never produces data — caller should handle gracefully."""

    elapsed = 0
    poll_interval = 3

    while elapsed < max_wait:
        resp = session.get(f"{BRAIN_API_BASE}/alphas/{alpha_id}/recordsets/pnl")

        if resp.status_code != 200:
            if debug:
                print(f"    [debug] status={resp.status_code} body={resp.text[:300]}")
            return None

        text = resp.text.strip()
        if not text:
            # Recordset likely still generating — wait and retry, same
            # pattern as simulation polling.
            time.sleep(poll_interval)
            elapsed += poll_interval
            continue

        try:
            data = resp.json()
        except requests.exceptions.JSONDecodeError:
            if debug:
                print(f"    [debug] non-JSON body: {text[:300]}")
            return None

        schema_props = data.get("schema", {}).get("properties", [])
        records = data.get("records", [])

        if not records:
            if debug:
                print(f"    [debug] JSON parsed but 'records' was empty. Keys: {list(data.keys())}")
            return None

        # properties can be a list of {"name": ...} dicts (find the pnl column index)
        pnl_idx = None
        if isinstance(schema_props, list):
            for i, p in enumerate(schema_props):
                name = (p.get("name") or "").lower()
                if name in ("pnl", "cum_pnl", "returns", "ret"):
                    pnl_idx = i
                    break
        if pnl_idx is None:
            pnl_idx = 1  # common convention: index 0 = date, index 1 = pnl

        try:
            return [float(row[pnl_idx]) for row in records if len(row) > pnl_idx]
        except (TypeError, ValueError, IndexError) as e:
            if debug:
                print(f"    [debug] Row parse failed ({e}). Sample row: {records[0] if records else None}")
            return None

    if debug:
        print(f"    [debug] Recordset never populated within {max_wait}s (still empty body).")
    return None


def check_correlation(min_sharpe: float = 0.7) -> None:
    """Fetch PnL for every promising DB entry (sharpe above min_sharpe)
    and flag pairs that are too correlated to both be worth keeping."""
    conn = get_db()
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM alphas WHERE ABS(sharpe) >= ? AND alpha_id IS NOT NULL",
        (min_sharpe,),
    ).fetchall()

    if not rows:
        print(f"No alphas with |Sharpe| >= {min_sharpe} in the DB yet.")
        return

    print(f"Checking correlation across {len(rows)} promising alphas...")

    session = WQSession()
    session.login()

    pnl_by_id = {}
    for row in rows:
        cached = row["daily_pnl"]
        if cached:
            pnl_by_id[row["id"]] = json.loads(cached)
            continue

        pnl = fetch_pnl(session.session, row["alpha_id"], debug=True)
        if pnl is None:
            print(f"  Could not fetch PnL for {row['alpha_id']} "
                  f"({row['expression']}) — recordset endpoint may need adjusting.")
            continue

        conn.execute("UPDATE alphas SET daily_pnl = ? WHERE id = ?",
                      (json.dumps(pnl), row["id"]))
        pnl_by_id[row["id"]] = pnl
        time.sleep(1)

    conn.commit()

    if len(pnl_by_id) < 2:
        print("Not enough PnL series fetched to compare correlation.")
        conn.close()
        return

    # Convert cumulative PnL to daily returns before comparing — correlating
    # cumulative curves directly is misleading, since almost any two
    # generally-upward curves look highly correlated regardless of the
    # underlying signal. Correlation must be computed on day-to-day changes.
    def to_daily_returns(cum_pnl: list[float]) -> list[float]:
        return [cum_pnl[i + 1] - cum_pnl[i] for i in range(len(cum_pnl) - 1)]

    returns_by_id = {aid: to_daily_returns(pnl) for aid, pnl in pnl_by_id.items()}

    # Simple pairwise Pearson correlation on daily returns, no pandas/numpy needed
    ids = list(returns_by_id.keys())
    flagged = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = returns_by_id[ids[i]], returns_by_id[ids[j]]
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

    id_to_row = {row["id"]: row for row in rows}
    if flagged:
        print(f"\n{len(flagged)} pair(s) exceed correlation {CORRELATION_THRESHOLD}:")
        for id_a, id_b, corr in flagged:
            print(f"  corr={corr:.2f}")
            print(f"    A: {id_to_row[id_a]['expression']} (Sharpe {id_to_row[id_a]['sharpe']})")
            print(f"    B: {id_to_row[id_b]['expression']} (Sharpe {id_to_row[id_b]['sharpe']})")
            print("    -> keep whichever has the better Sharpe/Fitness, drop the other")
    else:
        print("\nNo highly-correlated pairs found — current shortlist looks diverse.")

    conn.close()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "import"

    if command == "import":
        inserted, skipped = import_results()
        print(f"Imported {inserted} new alphas, skipped {skipped} already in the DB.")
    elif command == "correlate":
        check_correlation()
    else:
        print("Usage: python alpha_db.py [import|correlate]")