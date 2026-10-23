"""
Mega Batch Generator
------------------------
Broad, overnight-scale exploration. Instead of restricting itself to a
fixed set of hand-picked keyword categories, this samples fields RANDOMLY
from the full cached field list and crosses them with every template /
window / neutralization combination — so the batch spreads across
whatever the cache actually contains, not just the clusters you already
thought of.

Excludes anything in excluded_fields.json (known-bad fields) and
exhausted_clusters.json (confirmed dead-end clusters), same as
generator_focused.py, and only uses numeric (MATRIX/VECTOR/SPECIAL)
fields so every generated expression is simulatable.

Usage:
    python generator_mega.py [target_size]

    python generator_mega.py 250

Options:
    --fields N   Number of cached fields to sample randomly (default 80)
    --seed N     Reproducible run (default: fresh randomness each run)
"""

import argparse
import json
import random
from pathlib import Path
from typing import Any

from field_rules import (
    load_field_metadata,
    operand,
    field_type,
    is_numeric_field,
)

FIELD_CACHE = Path("field_cache/fields_USA_TOP3000_d1.json")
CANDIDATES_OUT = Path("candidates.json")
EXCLUDED_FIELDS_FILE = Path("excluded_fields.json")
EXHAUSTED_CLUSTERS_FILE = Path("exhausted_clusters.json")

# How many distinct cached fields to random-sample per run. Each sampled
# field is crossed with every template/window/neutralization below, so
# the raw pool is much larger than this before it is trimmed to
# target_size.
DEFAULT_FIELD_SAMPLE = 80

WINDOWS = [3, 5, 8, 15, 20]
NEUTRALIZATIONS = ["NONE", "INDUSTRY", "SUBINDUSTRY"]

TEMPLATES = [
    {"name": "rank_delta_negated", "expr": "rank(-ts_delta({field}, {window}))"},
    {"name": "rank_zscore", "expr": "rank(ts_zscore({field}, {window}))"},
    {"name": "group_rank_delta_subind", "expr": "group_rank(-ts_delta({field}, {window}), subindustry)"},
    {"name": "group_rank_tsrank_subind", "expr": "group_rank(ts_rank({field}, {window}), subindustry)"},
]


def load_exclusions() -> set[str]:
    excluded: set[str] = set()
    if EXCLUDED_FIELDS_FILE.exists():
        try:
            excluded |= set(json.loads(EXCLUDED_FIELDS_FILE.read_text()))
        except json.JSONDecodeError:
            pass
    if EXHAUSTED_CLUSTERS_FILE.exists():
        try:
            clusters = json.loads(EXHAUSTED_CLUSTERS_FILE.read_text())
            for cluster in clusters.values():
                excluded |= set(cluster.get("fields", []))
        except json.JSONDecodeError:
            pass
    return excluded


def load_candidate_fields(
    excluded: set[str],
    metadata: dict[str, dict[str, Any]],
) -> list[str]:
    """Every unique numeric field in the cache that isn't excluded or
    known-exhausted — the full pool the random sampler draws from."""
    if not FIELD_CACHE.exists():
        raise SystemExit(f"{FIELD_CACHE} not found — run fields.py first.")

    fields = json.loads(FIELD_CACHE.read_text())

    candidates: list[str] = []
    seen: set[str] = set()

    for f in fields:
        fid = f.get("id")
        if not fid or fid in seen or fid in excluded:
            continue
        if not is_numeric_field(fid, metadata):
            continue
        seen.add(fid)
        candidates.append(fid)

    return candidates


def generate_mega_batch(
    target_size: int = 250,
    field_sample_size: int = DEFAULT_FIELD_SAMPLE,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)

    excluded = load_exclusions()
    print(f"Excluding {len(excluded)} known-bad/exhausted fields.")

    metadata = load_field_metadata()

    pool_fields = load_candidate_fields(excluded, metadata)
    print(f"{len(pool_fields)} eligible fields in cache after exclusions.")

    if not pool_fields:
        print("No eligible fields to sample — nothing to generate.")
        return []

    sample = rng.sample(pool_fields, min(field_sample_size, len(pool_fields)))
    print(f"Randomly sampled {len(sample)} fields from the cache.")

    pool: list[dict[str, Any]] = []
    seen_expressions: set[str] = set()

    for field in sample:
        safe_field = operand(field, metadata)
        ftype = field_type(field, metadata)
        for template in TEMPLATES:
            for window in WINDOWS:
                for neut in NEUTRALIZATIONS:
                    expr = template["expr"].format(
                        field=safe_field,
                        window=window,
                    )
                    if expr in seen_expressions:
                        continue
                    seen_expressions.add(expr)
                    pool.append({
                        "expression": expr,
                        "template": template["name"],
                        "field": field,
                        "field_type": ftype,
                        "window": window,
                        "neutralization": neut,
                        "universe": "TOP3000",
                        "region": "USA",
                        "delay": 1,
                        "truncation": 0.08,
                        "source_cluster": "mega_random",
                    })

    print(f"\nGenerated pool of {len(pool)} candidates "
          f"from {len(sample)} randomly sampled fields.")

    rng.shuffle(pool)
    candidates = pool[:target_size]

    spread: dict[str, int] = {}
    for c in candidates:
        spread[c["field_type"]] = spread.get(c["field_type"], 0) + 1
    print(f"Sampled down to {len(candidates)}. Field-type spread: {spread}")

    return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Randomly sample cached fields and generate a mega batch."
    )
    parser.add_argument(
        "target",
        nargs="?",
        type=int,
        default=250,
        help="Number of candidates to generate (default 250).",
    )
    parser.add_argument(
        "--fields",
        type=int,
        default=DEFAULT_FIELD_SAMPLE,
        help="Number of cached fields to sample randomly (default 80).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed. Leave empty for fresh randomness.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    candidates = generate_mega_batch(
        target_size=args.target,
        field_sample_size=args.fields,
        seed=args.seed,
    )

    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"\nSaved {len(candidates)} candidates to {CANDIDATES_OUT}")
    print(f"\nThis will take a while to simulate — each run of simulate.py "
          f"resumes automatically if interrupted, so it's safe to run "
          f"overnight and let it pick up where it left off if anything drops.")
