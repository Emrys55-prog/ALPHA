"""
Utility: Learn bad fields from past simulation failures
----------------------------------------------------------
Reads results.json (from Stage 4) and extracts any field that failed
with an operator-compatibility error (e.g. "does not support event
inputs"). These get appended to excluded_fields.json, which generator.py
reads to skip them in future batches — so the pipeline gets smarter
about which fields are usable each time it runs.

Usage:
    python learn_excluded_fields.py
"""

import json
from pathlib import Path

RESULTS_IN = Path("results.json")
EXCLUDED_OUT = Path("excluded_fields.json")

# Error substrings that indicate the FIELD itself is unusable with
# standard operators (as opposed to a syntax mistake in our template).
FIELD_INCOMPATIBILITY_MARKERS = [
    "does not support event inputs",
    "Invalid data field",  # e.g. a guessed seed field that doesn't exist
                            # in this account's actual field list
]


def learn_excluded_fields() -> set[str]:
    excluded = set()
    if EXCLUDED_OUT.exists():
        excluded = set(json.loads(EXCLUDED_OUT.read_text()))

    if not RESULTS_IN.exists():
        print(f"{RESULTS_IN} not found — nothing to learn from yet.")
        return excluded

    results = json.loads(RESULTS_IN.read_text())
    new_exclusions = set()

    for r in results:
        if r.get("status") != "FAILED":
            continue
        error = r.get("error", "")
        if any(marker in error for marker in FIELD_INCOMPATIBILITY_MARKERS):
            field = r.get("field")
            if field and field not in excluded:
                new_exclusions.add(field)

    excluded |= new_exclusions

    if new_exclusions:
        print(f"Learned {len(new_exclusions)} new incompatible fields:")
        for f in sorted(new_exclusions):
            print(f"  - {f}")
    else:
        print("No new incompatible fields found in this results.json.")

    EXCLUDED_OUT.write_text(json.dumps(sorted(excluded), indent=2))
    print(f"Total excluded fields now: {len(excluded)} (saved to {EXCLUDED_OUT})")

    return excluded


if __name__ == "__main__":
    learn_excluded_fields()