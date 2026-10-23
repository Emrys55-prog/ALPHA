"""Continuous, budget-capped wrapper for research_loop.py.

Runs one feedback round at a time, preserves a daily usage budget, and writes
only strict-screen passers to research_loop/shortlist. Ctrl+C stops the loop.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "research_loop" / "continuous_state.json"
REPORT = ROOT / "research_loop" / "latest_report.json"
RESULTS = ROOT / "research_loop" / "simulation_results.json"
SHORTLIST = ROOT / "research_loop" / "shortlist"


def load_state(today):
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    if state.get("date") != today:
        return {"date": today, "model_calls": 0, "simulations": 0}
    return state


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temp, STATE)


def strong_enough(item, result):
    if item.get("status") != "QUALIFIED":
        return False, "local Sharpe/Fitness/turnover screen failed"
    checks = result.get("raw_checks", [])
    if not checks:
        return False, "simulation did not return BRAIN checks"
    pending_self_corr = False
    for check in checks:
        name, status = check.get("name"), check.get("result")
        if name == "SELF_CORRELATION" and status == "PENDING":
            pending_self_corr = True
            continue
        if status != "PASS":
            return False, f"BRAIN check {name or 'unknown'} is {status or 'unknown'}"
    return True, ("SELF_CORRELATION still needs your manual submission check" if pending_self_corr else "all returned checks passed")


def save_strong(item, result, note):
    alpha_id = result.get("alpha_id") or item.get("alpha_id")
    if not alpha_id:
        return None
    SHORTLIST.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": datetime.now().astimezone().isoformat(),
        "review_note": note,
        "submission_performed": False,
        "loop_feedback": item.get("feedback", {}),
        "candidate": result,
    }
    path = SHORTLIST / f"{alpha_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def run_once(batch_size, reserved_sims):
    before_calls = 1
    cmd = [sys.executable, str(ROOT / "research_loop.py"), "--rounds", "1",
           "--batch-size", str(batch_size), "--max-sims", str(reserved_sims)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode:
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-18:])
        print("Research cycle failed; pausing before retry:\n" + tail)
        return None
    try:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        results = json.loads(RESULTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read cycle report ({exc}); no candidate was added to the shortlist.")
        return None
    by_id = {r.get("alpha_id"): r for r in results if r.get("alpha_id")}
    simulated = 0
    for round_data in report.get("rounds", []):
        for item in round_data.get("simulated", []):
            alpha_id = item.get("alpha_id")
            result = by_id.get(alpha_id)
            if not result:
                continue
            simulated += 1
            good, note = strong_enough(item, result)
            if good:
                saved = save_strong(item, result, note)
                print(f"SHORTLISTED {alpha_id}: Sharpe={result.get('sharpe')} Fitness={result.get('fitness')} -> {saved}")
            else:
                print(f"Reviewed {alpha_id}: not shortlisted ({note}).")
    if simulated == 0:
        print("No valid candidates were simulated this cycle; the next idea round will use saved feedback.")
    # Use the loop's reserved simulation count, which includes failed BRAIN
    # runs that may still have consumed a simulation submission.
    return int(report.get("simulation_count", simulated))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--daily-sims", type=int, default=10, help="maximum simulation submissions per local day")
    ap.add_argument("--daily-model-calls", type=int, default=10, help="maximum idea-generation calls per local day")
    ap.add_argument("--batch-size", type=int, default=1, help="candidate ideas requested in each round")
    ap.add_argument("--idle-seconds", type=int, default=90, help="wait between model rounds")
    args = ap.parse_args()
    if min(args.daily_sims, args.daily_model_calls, args.batch_size, args.idle_seconds) < 1:
        ap.error("all limits must be positive")
    provider = os.environ.get("ALPHA_LLM_PROVIDER", "gemini").strip().lower()
    if provider == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        ap.error("GEMINI_API_KEY is not set in this PowerShell session")
    if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        ap.error("OPENAI_API_KEY is not set in this PowerShell session")

    print("Continuous research is running. Stop it with Ctrl+C.")
    print(f"Daily caps: {args.daily_model_calls} model calls, {args.daily_sims} simulation submissions.")
    print(f"Strong candidates will be saved in: {SHORTLIST}")
    try:
        while True:
            today = datetime.now().astimezone().date().isoformat()
            state = load_state(today)
            if state["model_calls"] >= args.daily_model_calls or state["simulations"] >= args.daily_sims:
                print(f"Today's cap reached ({state['model_calls']} model calls, {state['simulations']} simulations). Waiting for the next local day.")
                time.sleep(300)
                continue
            remaining_sims = args.daily_sims - state["simulations"]
            batch_size = min(args.batch_size, remaining_sims)
            state["model_calls"] += 1  # reserve before network request
            state["simulations"] += batch_size  # reserve conservatively before BRAIN submission
            save_state(state)
            actual = run_once(batch_size, batch_size)
            # Give unused reserved simulation slots back; keep reservations if a process failed mid-request.
            if actual is not None:
                state = load_state(datetime.now().astimezone().date().isoformat())
                state["simulations"] -= max(0, batch_size - min(batch_size, actual))
                save_state(state)
            time.sleep(args.idle_seconds)
    except KeyboardInterrupt:
        print("Stopped by you. Shortlisted candidates and loop memory are saved.")


if __name__ == "__main__":
    main()
