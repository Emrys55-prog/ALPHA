"""
Stage 4: Simulation
---------------------
Submits each candidate expression from Stage 3 to BRAIN's simulate
endpoint, polls until the simulation finishes, then pulls back the
result stats (Sharpe, Fitness, Turnover, Drawdown, Margin) and the
pass/fail status of every check BRAIN runs.

Runs candidates one at a time (safest for a first test batch — once
this works reliably you can parallelize). Results are saved to
results.json for Stage 5 to filter.

Usage:
    python simulate.py
"""

import json
import time
from pathlib import Path

import requests

from auth import WQSession

BRAIN_API_BASE = "https://api.worldquantbrain.com"
CANDIDATES_IN = Path("candidates.json")
RESULTS_OUT = Path("results.json")

# Defaults seen across community BRAIN automation tools. decay=6 and
# truncation=0.08 are reasonable starting points — override per-candidate
# if you want to test different decay/truncation combos later.
DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "delay": 1,
    "decay": 6,
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "maxTrade": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}


def _request_with_retry(session, method, url, max_retries=6, network_retries=5, **kwargs):
    """Wraps session.request with 429 backoff AND network-error backoff
    (dropped connection, timeout) — so a brief network blip mid-batch
    doesn't kill the whole overnight run."""
    kwargs.setdefault("timeout", 60)

    for attempt in range(max_retries):
        try:
            resp = session.request(method, url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            wait = 2 ** (attempt + 2)
            print(f"    Network error ({e.__class__.__name__}) — retrying in {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = int(retry_after) if retry_after else (2 ** (attempt + 1))
            print(f"    Rate limited — waiting {wait}s...")
            time.sleep(wait)
            continue
        return resp
    raise RuntimeError(f"Still failing after {max_retries} retries: {url}")


def submit_simulation(session: requests.Session, candidate: dict) -> str:
    """Submit one candidate expression. Returns the polling URL BRAIN gives back."""

    settings = {
        **DEFAULT_SETTINGS,
        "region": candidate.get("region", "USA"),
        "universe": candidate.get("universe", "TOP3000"),
        "delay": candidate.get("delay", 1),
        "neutralization": candidate.get("neutralization", "NONE"),
        "truncation": candidate.get("truncation", DEFAULT_SETTINGS["truncation"]),
        "decay": candidate.get("decay", DEFAULT_SETTINGS["decay"]),
    }

    payload = {
        "type": "REGULAR",
        "settings": settings,
        "regular": candidate["expression"],
    }

    resp = _request_with_retry(session, "POST", f"{BRAIN_API_BASE}/simulations", json=payload)

    if resp.status_code != 201:
        raise RuntimeError(f"Submit failed ({resp.status_code}): {resp.text}")

    location = resp.headers.get("Location")
    if not location:
        raise RuntimeError(f"No Location header in submit response: {resp.headers}")

    return location


def poll_simulation(session: requests.Session, location_url: str,
                     poll_interval: int = 5, timeout: int = 600) -> str:
    """Poll until the simulation finishes. Returns the resulting alpha ID."""

    elapsed = 0
    while elapsed < timeout:
        resp = _request_with_retry(session, "GET", location_url)

        if resp.status_code != 200:
            raise RuntimeError(f"Poll failed ({resp.status_code}): {resp.text}")

        retry_after = resp.headers.get("Retry-After")
        if retry_after and float(retry_after) > 0:
            wait = float(retry_after)
            time.sleep(wait)
            elapsed += wait
            continue

        # No Retry-After means it's done
        payload = resp.json()
        alpha_id = payload.get("alpha")
        if not alpha_id:
            raise RuntimeError(f"Simulation finished but no alpha ID returned: {payload}")
        return alpha_id

    raise TimeoutError(f"Simulation did not finish within {timeout}s")


def get_alpha_stats(session: requests.Session, alpha_id: str) -> dict:
    """Fetch the finished alpha's stats and check results."""

    resp = _request_with_retry(session, "GET", f"{BRAIN_API_BASE}/alphas/{alpha_id}")
    if resp.status_code != 200:
        raise RuntimeError(f"Alpha fetch failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    is_stats = data.get("is", {})

    checks = is_stats.get("checks", [])
    passed_checks = sum(1 for c in checks if c.get("result") == "PASS")

    return {
        "alpha_id": alpha_id,
        "sharpe": is_stats.get("sharpe"),
        "fitness": is_stats.get("fitness"),
        "turnover": is_stats.get("turnover"),
        "returns": is_stats.get("returns"),
        "drawdown": is_stats.get("drawdown"),
        "margin": is_stats.get("margin"),
        "checks_total": len(checks),
        "checks_passed": passed_checks,
        "all_checks_passed": passed_checks == len(checks) and len(checks) > 0,
        "raw_checks": checks,
    }


def _candidate_key(c: dict) -> tuple:
    """Uniqueness key for resume/dedup purposes. Expression text ALONE is
    not enough — two candidates can share identical expression text but
    test different settings (neutralization, truncation, decay, etc),
    which genuinely changes the simulation result. Keying on expression
    only would wrongly treat those as duplicates and skip a real test.
    Every setting simulate.py actually sends to BRAIN must be listed here,
    or a sweep over that setting alone will silently get skipped on
    resume — this has now bitten twice (truncation, then decay)."""
    return (
        c.get("expression"),
        c.get("neutralization"),
        c.get("universe"),
        c.get("region"),
        c.get("delay"),
        c.get("truncation"),
        c.get("decay"),
    )


def run_batch(candidates: list[dict], session: requests.Session,
              delay_between: float = 3.0) -> list[dict]:
    # Resume support: if results.json already has successful results for
    # some of these exact (expression, neutralization, universe, region,
    # delay) combinations — e.g. from a run cut off by a network outage —
    # don't re-submit them. Only skip TRUE duplicates, not different
    # neutralization variants of the same expression text.
    previous_results = {}
    if RESULTS_OUT.exists():
        try:
            for r in json.loads(RESULTS_OUT.read_text()):
                if r.get("status") == "SUCCESS":
                    previous_results[_candidate_key(r)] = r
        except (json.JSONDecodeError, KeyError):
            pass

    results = []
    to_submit = []
    for candidate in candidates:
        prior = previous_results.get(_candidate_key(candidate))
        if prior:
            results.append(prior)
        else:
            to_submit.append(candidate)

    if previous_results and len(results) > 0:
        print(f"Resuming: {len(results)} already succeeded in a previous run, "
              f"skipping those. {len(to_submit)} left to submit.\n")

    for i, candidate in enumerate(to_submit):
        expr = candidate["expression"]
        print(f"[{i+1}/{len(to_submit)}] Submitting: {expr}")

        try:
            location = submit_simulation(session, candidate)
            print("    Submitted, polling for completion...")

            alpha_id = poll_simulation(session, location)
            stats = get_alpha_stats(session, alpha_id)

            result = {**candidate, **stats, "status": "SUCCESS"}
            print(f"    Done — alpha_id={stats['alpha_id']}, Sharpe={stats['sharpe']}, "
                  f"Fitness={stats['fitness']}, Checks {stats['checks_passed']}/{stats['checks_total']}")

        except Exception as e:
            print(f"    FAILED: {e}")
            result = {**candidate, "status": "FAILED", "error": str(e)}

        results.append(result)

        # Save incrementally so a crash mid-batch doesn't lose earlier results
        RESULTS_OUT.write_text(json.dumps(results, indent=2))

        time.sleep(delay_between)

    return results


if __name__ == "__main__":
    if not CANDIDATES_IN.exists():
        raise SystemExit(f"{CANDIDATES_IN} not found — run generator.py first.")

    candidates = json.loads(CANDIDATES_IN.read_text())
    print(f"Loaded {len(candidates)} candidates to simulate.\n")

    session = WQSession()
    session.login()

    results = run_batch(candidates, session.session)

    succeeded = [r for r in results if r["status"] == "SUCCESS"]
    print(f"\nDone. {len(succeeded)}/{len(results)} simulations succeeded.")
    print(f"Results saved to {RESULTS_OUT}")