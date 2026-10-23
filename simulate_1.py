"""Sequential BRAIN alpha runner. Accepts any number of expressions.

Usage: python simulate_1.py "rank(returns)" "rank(ts_delta(returns, 5))"
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from auth import WQSession
from field_rules import load_field_metadata, normalize_expression, validate_fields

BASE_URL = "https://api.worldquantbrain.com"
RESULTS_FILE = Path("batch_results.json")
DELAY_BETWEEN_ALPHAS = 3
POLL_INTERVAL = 5
POLL_TIMEOUT = 600

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 6,
    "neutralization": "INDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "maxTrade": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}


def request_with_retry(session, method, url, **kwargs):
    """Retry transient network errors and HTTP 429 responses."""
    kwargs.setdefault("timeout", 60)
    max_retries = 6
    for attempt in range(max_retries):
        try:
            response = session.request(method, url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** (attempt + 2)
            print(f"  Network error ({type(exc).__name__}); retrying in {wait}s...")
            time.sleep(wait)
            continue

        if response.status_code == 429:
            if attempt == max_retries - 1:
                return response
            retry_after = response.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else 2 ** (attempt + 1)
            except ValueError:
                wait = 2 ** (attempt + 1)
            print(f"  Rate limited; waiting {wait:g}s...")
            time.sleep(wait)
            continue
        return response
    raise RuntimeError(f"Request retries exhausted: {method} {url}")


def submit_simulation(session, expression, metadata):
    """Normalize and validate the expression, then submit one simulation."""
    expression = normalize_expression(expression, metadata)
    unknown = validate_fields(expression, metadata)
    if unknown:
        raise ValueError("Field validation failed: " + ", ".join(unknown))

    payload = {
        "type": "REGULAR",
        "settings": DEFAULT_SETTINGS,
        "regular": expression,
    }
    response = request_with_retry(
        session, "POST", f"{BASE_URL}/simulations", json=payload
    )
    if response.status_code != 201:
        raise RuntimeError(
            f"Simulation submission failed ({response.status_code}): {response.text[:500]}"
        )
    location = response.headers.get("Location")
    if not location:
        raise RuntimeError("BRAIN did not return a simulation Location header.")
    return expression, location


def poll_simulation(session, location, timeout=POLL_TIMEOUT):
    """Poll the simulation endpoint; use its completed `alpha` field as the ID.

    This follows simulate.py's working mechanism. The Location identifies a
    simulation job; it is not an alpha ID and must not be used in /alphas/{id}.
    """
    started = time.monotonic()
    print("  Waiting for simulation", end="", flush=True)
    while time.monotonic() - started < timeout:
        response = request_with_retry(session, "GET", location)
        if response.status_code != 200:
            raise RuntimeError(f"Polling failed ({response.status_code}): {response.text[:500]}")

        data = response.json()
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            wait = float(retry_after)
            print(".", end="", flush=True)
            time.sleep(wait)
            continue

        alpha_id = data.get("alpha")
        if not alpha_id:
            raise RuntimeError(f"Simulation completed without an alpha ID: {data}")
        print(" done")
        return alpha_id

    raise TimeoutError(f"Simulation did not finish within {timeout}s")


def get_alpha_stats(session, alpha_id):
    """Fetch completed alpha metrics, using simulate.py's response schema."""
    response = request_with_retry(session, "GET", f"{BASE_URL}/alphas/{alpha_id}")
    if response.status_code != 200:
        raise RuntimeError(
            f"Could not retrieve alpha {alpha_id} ({response.status_code}): {response.text[:500]}"
        )
    data = response.json()
    is_stats = data.get("is", {})
    checks = is_stats.get("checks", [])
    passed = sum(1 for check in checks if check.get("result") == "PASS")
    return {
        "alpha_id": alpha_id,
        "sharpe": is_stats.get("sharpe"),
        "fitness": is_stats.get("fitness"),
        "turnover": is_stats.get("turnover"),
        "returns": is_stats.get("returns"),
        "drawdown": is_stats.get("drawdown"),
        "margin": is_stats.get("margin"),
        "checks_total": len(checks),
        "checks_passed": passed,
        "all_checks_passed": bool(checks) and passed == len(checks),
        "raw_checks": checks,
    }


def save_result(result):
    """Append each completed or failed attempt immediately to disk."""
    if RESULTS_FILE.exists():
        try:
            results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
            if not isinstance(results, list):
                results = []
        except (OSError, json.JSONDecodeError):
            results = []
    else:
        results = []
    results.append(result)
    RESULTS_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")


def simulate_one(session, expression, metadata, number, total):
    print(f"\n[{number}/{total}] {expression}")
    try:
        normalized, location = submit_simulation(session, expression, metadata)
        if normalized != expression:
            print(f"  Normalized: {normalized}")
        print("  Submitted.")
        alpha_id = poll_simulation(session, location)
        stats = get_alpha_stats(session, alpha_id)
        result = {
            "expression": expression,
            "normalized_expression": normalized,
            "timestamp": datetime.now().astimezone().isoformat(),
            "success": True,
            **stats,
        }
        print(
            f"  Alpha {alpha_id}: Sharpe={stats['sharpe']}, "
            f"Fitness={stats['fitness']}, Checks={stats['checks_passed']}/{stats['checks_total']}"
        )
        return result
    except Exception as exc:
        print(f"  FAILED: {exc}")
        return {
            "expression": expression,
            "timestamp": datetime.now().astimezone().isoformat(),
            "success": False,
            "error": str(exc),
        }


def main():
    expressions = sys.argv[1:]
    if not expressions:
        raise SystemExit('Usage: python simulate_1.py "expression1" "expression2" ...')

    print(f"Queued {len(expressions)} expressions; logging in once.")
    wq_session = WQSession()
    wq_session.login()
    session = wq_session.session
    metadata = load_field_metadata()

    for number, expression in enumerate(expressions, 1):
        result = simulate_one(session, expression, metadata, number, len(expressions))
        save_result(result)
        print(f"  Saved progress to {RESULTS_FILE} ({number}/{len(expressions)}).")
        if number < len(expressions):
            print(f"  Waiting {DELAY_BETWEEN_ALPHAS}s before the next expression...")
            time.sleep(DELAY_BETWEEN_ALPHAS)

    successful = sum(1 for item in _load_latest_results(len(expressions)) if item.get("success"))
    print(f"\nFinished this run: {successful}/{len(expressions)} succeeded. Results: {RESULTS_FILE}")


def _load_latest_results(count):
    try:
        rows = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        return rows[-count:] if isinstance(rows, list) else []
    except (OSError, json.JSONDecodeError):
        return []


if __name__ == "__main__":
    main()
