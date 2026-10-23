"""
Pipeline Orchestrator
------------------------
Chains the full research loop into ONE command instead of running
generator -> simulate -> qualify -> correlate separately and pasting
each output back for review.

Usage:
    python run_pipeline.py focused <seed_field> <keywords> [prefix]
    python run_pipeline.py mega [target_size]

Examples:
    python run_pipeline.py focused total_receivables receivable,collection,ar ""
    python run_pipeline.py mega 250

What it does NOT do: submit anything. Submission always stays a
separate, manual step via submit.py with its confirmation prompt —
that's intentional, not a limitation to work around.
"""

import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> bool:
    """Run a pipeline stage, streaming its output live. Returns True on
    success (exit code 0), False otherwise — so the orchestrator can
    decide whether to continue to the next stage."""
    print(f"\n{'='*60}\n>>> {' '.join(cmd)}\n{'='*60}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "focused":
        if len(sys.argv) < 4:
            print("Usage: python run_pipeline.py focused <seed_field> <keywords> [prefix]")
            sys.exit(1)
        seed_field = sys.argv[2]
        keywords = sys.argv[3]
        prefix = sys.argv[4] if len(sys.argv) > 4 else ""
        if not run(["python", "generator_focused.py", seed_field, keywords, prefix]):
            print("Generator failed — stopping.")
            sys.exit(1)

    elif mode == "mega":
        target = sys.argv[2] if len(sys.argv) > 2 else "250"
        if not run(["python", "generator_mega.py", target]):
            print("Generator failed — stopping.")
            sys.exit(1)

    else:
        print(f"Unknown mode: {mode}. Use 'focused' or 'mega'.")
        sys.exit(1)

    if not run(["python", "simulate.py"]):
        print("Simulation had failures — check output above. Continuing to qualify "
              "with whatever succeeded.")

    if not run(["python", "qualify.py"]):
        print("Qualify step failed — stopping before correlate.")
        sys.exit(1)

    # Only run correlation if there's something to correlate
    qualified_path = Path("qualified.json")
    watchlist_path = Path("watchlist.json")
    has_candidates = False
    for p in (qualified_path, watchlist_path):
        if p.exists():
            try:
                if json.loads(p.read_text()):
                    has_candidates = True
            except json.JSONDecodeError:
                pass

    if has_candidates:
        run(["python", "alpha_db.py", "import"])
        run(["python", "alpha_db.py", "correlate"])
        run(["python", "deep_check.py"])
    else:
        print("\nNothing qualified or made the watchlist this run — skipping correlation/deep checks.")

    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print("deep_checked.json shows which candidates actually look submittable")
    print("against BRAIN's real checks (sub-universe, concentration, correlation),")
    print("not just the local Sharpe/Fitness filter. Use submit.py manually for")
    print("anything you want to actually put live — that step always needs your")
    print("explicit confirmation.")


if __name__ == "__main__":
    main()