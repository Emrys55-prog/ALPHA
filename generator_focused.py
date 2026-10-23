"""
Focused Follow-up Generator
------------------------------
Unlike generator.py (broad random sampling), this builds a batch
targeted at a specific seed field or category — now reusable for ANY
lead, not hardcoded to one field. Pass a seed field and keywords on
the command line to point it at a new cluster to explore.

Also excludes fields already flagged in exhausted_clusters.json — so
once you've confirmed a cluster (like anl4_qf_az_cfps_mean and its
analyst-estimate siblings) caps out below BRAIN's real bar, this
generator won't waste a batch re-sampling it.

Usage:
    python generator_focused.py <seed_field> [keyword1,keyword2,...] [prefix]

    # Re-run the analyst-estimate exploration (now mostly exhausted):
    python generator_focused.py anl4_qf_az_cfps_mean cfps,eps,sales,guidance,estimate,consensus anl4

    # Explore a totally different category instead, e.g. quality/profitability:
    python generator_focused.py operating_income_to_equity roe,margin,profitability,quality fnd6

    # No args: prints usage and available exhausted clusters to avoid
    python generator_focused.py
"""

import json
import random
import sys
from pathlib import Path

from field_rules import load_field_metadata, operand, field_type, is_numeric_field


FIELD_CACHE = Path("field_cache/fields_USA_TOP3000_d1.json")
CANDIDATES_OUT = Path("candidates.json")
EXCLUDED_FIELDS_FILE = Path("excluded_fields.json")
EXHAUSTED_CLUSTERS_FILE = Path("exhausted_clusters.json")

MAX_SIMILAR_FIELDS = 7  # keep the field list focused, not another broad sweep

# Finer-grained windows than the broad batch (which used 5/10/20/30)
WINDOWS = [3, 5, 8, 10, 15, 20, 30]

# More neutralization options than the broad batch, since we're testing
# a specific hypothesis and want to see how it holds up across settings
NEUTRALIZATIONS = ["NONE", "INDUSTRY", "SUBINDUSTRY", "MARKET"]

# Templates for fundamentals/analyst-type fields. group_rank variants
# added per community research: group_rank(x, subindustry) is often a
# stronger combination for these field types than plain rank() —
# worth testing head-to-head against what we already tried.
TEMPLATES = [
    {"name": "rank_delta_negated", "expr": "rank(-ts_delta({field}, {window}))"},
    {"name": "rank_zscore", "expr": "rank(ts_zscore({field}, {window}))"},
    {"name": "group_rank_delta_subind", "expr": "group_rank(-ts_delta({field}, {window}), subindustry)"},
    {"name": "group_rank_tsrank_subind", "expr": "group_rank(ts_rank({field}, {window}), subindustry)"},
]


def load_exhausted_fields() -> set[str]:
    """Fields belonging to clusters already confirmed (via alpha_db.py
    correlate) to cap out below BRAIN's real threshold — skip these
    even if they match the current keyword search."""
    if not EXHAUSTED_CLUSTERS_FILE.exists():
        return set()
    try:
        clusters = json.loads(EXHAUSTED_CLUSTERS_FILE.read_text())
    except json.JSONDecodeError:
        print(f"Warning: {EXHAUSTED_CLUSTERS_FILE} exists but isn't valid JSON "
              f"(empty or corrupted) — continuing without exclusions.")
        return set()
    fields = set()
    for cluster in clusters.values():
        fields.update(cluster.get("fields", []))
    return fields


def find_similar_fields(seed_field: str, keywords: list[str], prefix: str) -> list[str]:
    metadata = load_field_metadata()

    if not FIELD_CACHE.exists():
        print(f"Warning: {FIELD_CACHE} not found. Using only the seed field.")
        return [seed_field]

    excluded = set()
    if EXCLUDED_FIELDS_FILE.exists():
        excluded = set(json.loads(EXCLUDED_FIELDS_FILE.read_text()))

    exhausted = load_exhausted_fields()
    if exhausted:
        print(f"Skipping {len(exhausted)} fields from already-exhausted clusters.")

    fields = json.loads(FIELD_CACHE.read_text())
    matches = []

    for f in fields:
        fid = f.get("id", "")

        if (
            fid in excluded
            or fid in exhausted
            or fid == seed_field
            or not is_numeric_field(fid, metadata)
        ):
            continue

        if prefix and not fid.startswith(prefix):
            continue

        if any(kw in fid.lower() for kw in keywords):
            matches.append(fid)

    random.seed(7)
    random.shuffle(matches)

    all_ids = {
        f.get("id")
        for f in fields
        if f.get("id")
    }

    seed_list = []

    if seed_field in all_ids and is_numeric_field(seed_field, metadata):
        seed_list = [seed_field]

    return seed_list + matches[:MAX_SIMILAR_FIELDS]


def validate_seed_field(seed_field: str) -> bool:
    """Returns False (and prints close matches) if the seed field doesn't
    actually exist in the cache — catches a guessed name before it wastes
    a whole batch of simulations failing on 'unknown variable'."""
    if not FIELD_CACHE.exists():
        return True  # can't validate without a cache, let it through
    fields = json.loads(FIELD_CACHE.read_text())
    ids = {f.get("id") for f in fields if f.get("id")}
    if seed_field in ids:
        return True

    print(f"ERROR: seed field '{seed_field}' is not in your cached field list — "
          f"this would fail every candidate that uses it.")
    tokens = [t for t in seed_field.lower().split("_") if len(t) > 2]
    scored = []
    for fid in ids:
        hits = sum(1 for t in tokens if t in fid.lower())
        if hits >= 1:
            scored.append((hits, fid))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    if scored:
        print("Close matches you could use instead:")
        for _, fid in scored[:10]:
            print(f"  {fid}")
    return False


def generate_focused_candidates(
    seed_field: str,
    keywords: list[str],
    prefix: str,
    max_candidates: int = 25,
    seed: int = 7,
) -> list[dict]:

    metadata = load_field_metadata()

    if not validate_seed_field(seed_field):
        print(
            "Continuing with similar-field keyword matches only, "
            "skipping the bad seed."
        )

    fields = find_similar_fields(
        seed_field,
        keywords,
        prefix,
    )

    print(f"Focused field set ({len(fields)}): {fields}")

    pool = []

    for template in TEMPLATES:
        for field in fields:
            for window in WINDOWS:

                # VECTOR fields automatically become:
                # vec_avg(field)
                safe_field = operand(field, metadata)

                expr = template["expr"].format(
                    field=safe_field,
                    window=window,
                )

                # Keep candidate metadata consistent with the expression.
                if "group_rank" in expr:
                    neutralization = "SUBINDUSTRY"
                else:
                    neutralization = "NONE"

                pool.append({
                    "expression": expr,
                    "template": template["name"],
                    "field": field,
                    "field_type": field_type(field, metadata),
                    "window": window,
                    "neutralization": neutralization,
                    "universe": "TOP3000",
                    "region": "USA",
                    "delay": 1,
                    "source_cluster": seed_field,
                })

    print(
        f"Generated focused pool of {len(pool)} expressions."
    )

    seed_variants = [
        c for c in pool
        if c["field"] == seed_field
    ]

    other_variants = [
        c for c in pool
        if c["field"] != seed_field
    ]

    random.seed(seed)

    random.shuffle(seed_variants)
    random.shuffle(other_variants)

    seed_count = min(12, len(seed_variants))

    candidates = (
        seed_variants[:seed_count]
        + other_variants[:max_candidates - seed_count]
    )

    candidates = candidates[:max_candidates]

    print(
        f"Sampled down to {len(candidates)} candidates "
        f"({seed_count} on the seed field, "
        f"rest spread across similar fields)."
    )

    return candidates

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        exhausted = load_exhausted_fields()
        if exhausted:
            print(f"\nCurrently exhausted (avoid re-exploring): {sorted(exhausted)}")
        sys.exit(0)

    seed_field = sys.argv[1]
    keywords = sys.argv[2].split(",") if len(sys.argv) > 2 else []
    prefix = sys.argv[3] if len(sys.argv) > 3 else ""

    candidates = generate_focused_candidates(seed_field, keywords, prefix, max_candidates=25)

    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates to {CANDIDATES_OUT}\n")

    print("Preview:")
    for c in candidates[:10]:
        print(f"  [{c['field']}] {c['expression']}  (neut={c['neutralization']})")