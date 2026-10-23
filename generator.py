"""
Stage 3: Expression Generation
--------------------------------
Generates fresh alpha candidates while avoiding expressions that have
already been tested.

Features:
- Fresh random generation by default
- Optional reproducible seed for debugging
- Remembers previously tested expressions
- Avoids duplicate expressions within the same batch
- Uses field metadata to create safe operands
- Preserves VECTOR/event-field handling through field_rules.py

Usage:
    python generator.py

For reproducible debugging:
    python generator.py --seed 42
"""

import argparse
import json
import random
from pathlib import Path

from field_rules import load_field_metadata, operand, field_type


# ============================================================
# FILES
# ============================================================

FIELD_CACHE = Path("field_cache/fields_USA_TOP3000_d1.json")
CANDIDATES_OUT = Path("candidates.json")

EXCLUDED_FIELDS_FILE = Path("excluded_fields.json")
TESTED_EXPRESSIONS_FILE = Path("tested_expressions.json")


# ============================================================
# FIELD CONFIGURATION
# ============================================================

PRICE_VOLUME_FIELDS = [
    "returns",
    "close",
    "volume",
    "open",
    "high",
    "low",
    "vwap",
]

RAW_LEVEL_FIELDS = {
    "close",
    "open",
    "high",
    "low",
    "vwap",
}


# ============================================================
# SEARCH CONFIGURATION
# ============================================================

WINDOWS = [5, 10, 20, 30]

NEUTRALIZATIONS = [
    "INDUSTRY",
    "NONE",
]


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "name": "decay_linear_negated",
        "expr": "ts_decay_linear(-{field}, {window})",
        "price_volume_only": True,
        "excludes": RAW_LEVEL_FIELDS,
    },

    {
        "name": "decay_linear_zscore",
        "expr": "ts_decay_linear(-ts_zscore({field}, {window}), {window})",
        "price_volume_only": True,
        "includes_only": RAW_LEVEL_FIELDS,
    },

    {
        "name": "rank_delta_negated",
        "expr": "rank(-ts_delta({field}, {window}))",
        "price_volume_only": False,
    },

    {
        "name": "rank_zscore",
        "expr": "rank(ts_zscore({field}, {window}))",
        "price_volume_only": False,
    },

    {
        "name": "rank_field",
        "expr": "rank({field})",
        "price_volume_only": False,
        "no_window": True,
    },
]


# ============================================================
# EXCLUDED FIELDS
# ============================================================

def load_excluded_fields() -> set[str]:
    """
    Load fields that the system has already learned are incompatible.
    """

    if not EXCLUDED_FIELDS_FILE.exists():
        return set()

    try:
        data = json.loads(EXCLUDED_FIELDS_FILE.read_text())

        if isinstance(data, list):
            return set(data)

        if isinstance(data, dict):
            return set(data.keys())

    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read {EXCLUDED_FIELDS_FILE}: {exc}")

    return set()


# ============================================================
# TESTED EXPRESSIONS
# ============================================================

def load_tested_expressions() -> set[str]:
    """
    Load expressions that have already been tested.

    File format:

    [
        "rank(close)",
        "rank(ts_zscore(volume, 20))"
    ]
    """

    if not TESTED_EXPRESSIONS_FILE.exists():
        return set()

    try:
        data = json.loads(TESTED_EXPRESSIONS_FILE.read_text())

        if isinstance(data, list):
            return set(data)

        if isinstance(data, dict):
            expressions = data.get("expressions", [])

            if isinstance(expressions, list):
                return set(expressions)

    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"Warning: could not read "
            f"{TESTED_EXPRESSIONS_FILE}: {exc}"
        )

    return set()


def save_tested_expressions(expressions: set[str]) -> None:
    """
    Save tested expressions to disk.
    """

    TESTED_EXPRESSIONS_FILE.write_text(
        json.dumps(
            sorted(expressions),
            indent=2,
        )
    )


def register_tested_expressions(candidates: list[dict]) -> None:
    """
    Add generated candidates to the tested-expression history.

    NOTE:
    If you only want expressions to become 'tested' after BRAIN
    actually simulates them, call this from simulate.py instead.

    The generator itself does NOT register them automatically.
    """

    tested = load_tested_expressions()

    for candidate in candidates:
        expression = candidate.get("expression")

        if expression:
            tested.add(expression)

    save_tested_expressions(tested)


# ============================================================
# FUNDAMENTAL FIELD SAMPLING
# ============================================================

def load_fundamental_sample(
    n: int = 15,
    seed: int | None = None,
) -> list[str]:
    """
    Select a sample of fundamental fields.

    seed=None:
        Fresh random selection every run.

    seed=42:
        Reproducible selection for debugging.
    """

    if not FIELD_CACHE.exists():
        print(
            f"Warning: {FIELD_CACHE} not found — "
            f"run fields.py first."
        )

        print(
            "Continuing with price/volume fields only."
        )

        return []

    try:
        fields = json.loads(
            FIELD_CACHE.read_text()
        )
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"Warning: could not read {FIELD_CACHE}: {exc}"
        )

        return []

    ids = [
        f["id"]
        for f in fields
        if isinstance(f, dict)
        and f.get("id")
    ]

    if not ids:
        return []

    if seed is None:
        return random.sample(
            ids,
            min(n, len(ids)),
        )

    rng = random.Random(seed)

    return rng.sample(
        ids,
        min(n, len(ids)),
    )


# ============================================================
# SAFE RANDOM GENERATOR
# ============================================================

def make_rng(seed: int | None):
    """
    Return a random generator.

    seed=None -> genuinely fresh randomness
    seed=value -> reproducible randomness
    """

    if seed is None:
        return random.Random()

    return random.Random(seed)


# ============================================================
# CANDIDATE GENERATION
# ============================================================

def generate_candidates(
    max_candidates: int = 50,
    fundamental_sample_size: int = 15,
    seed: int | None = None,
) -> list[dict]:
    """
    Generate a fresh batch of candidate alpha expressions.

    Previously tested expressions are removed before sampling.
    """

    metadata = load_field_metadata()

    excluded = load_excluded_fields()

    if excluded:
        print(
            f"Skipping {len(excluded)} "
            f"previously-learned incompatible fields."
        )

    tested = load_tested_expressions()

    if tested:
        print(
            f"Skipping {len(tested)} "
            f"previously-tested expressions."
        )

    # --------------------------------------------------------
    # Select fundamental fields
    # --------------------------------------------------------

    fundamental_fields = [
        f
        for f in load_fundamental_sample(
            fundamental_sample_size,
            seed,
        )
        if f not in excluded
    ]

    # --------------------------------------------------------
    # Build field pool
    # --------------------------------------------------------

    all_fields = [
        (
            f,
            "price_volume",
            field_type(f, metadata),
        )
        for f in PRICE_VOLUME_FIELDS
        if f not in excluded
    ] + [
        (
            f,
            "fundamental",
            field_type(f, metadata),
        )
        for f in fundamental_fields
    ]

    # --------------------------------------------------------
    # Generate expressions
    # --------------------------------------------------------

    pool = []

    seen_expressions = set()

    for template in TEMPLATES:

        for field, category, actual_type in all_fields:

            # Skip templates restricted to price/volume
            if (
                template.get("price_volume_only")
                and category != "price_volume"
            ):
                continue

            # Skip explicitly excluded fields
            if field in template.get(
                "excludes",
                set(),
            ):
                continue

            # Skip fields outside include-only list
            if (
                "includes_only" in template
                and field not in template["includes_only"]
            ):
                continue

            # Templates without windows
            if template.get("no_window"):
                windows = [None]
            else:
                windows = WINDOWS

            for window in windows:

                for neutralization in NEUTRALIZATIONS:

                    # ------------------------------------------------
                    # Convert field to safe operand
                    #
                    # This is important because field_rules.py handles
                    # VECTOR/event fields such as:
                    #
                    # shares_sold_short_count_5_1555
                    #
                    # and can turn them into:
                    #
                    # vec_avg(shares_sold_short_count_5_1555)
                    # ------------------------------------------------

                    safe_field = operand(
                        field,
                        metadata,
                    )

                    expression = template["expr"].format(
                        field=safe_field,
                        window=window,
                    )

                    # ------------------------------------------------
                    # Prevent duplicates inside this generation run
                    # ------------------------------------------------

                    if expression in seen_expressions:
                        continue

                    seen_expressions.add(expression)

                    # ------------------------------------------------
                    # Prevent previously tested expressions
                    # ------------------------------------------------

                    if expression in tested:
                        continue

                    pool.append(
                        {
                            "expression": expression,
                            "template": template["name"],
                            "field": field,
                            "field_type": actual_type,
                            "window": window,
                            "neutralization": neutralization,
                            "universe": "TOP3000",
                            "region": "USA",
                            "delay": 1,
                        }
                    )

    # --------------------------------------------------------
    # Shuffle
    # --------------------------------------------------------

    rng = make_rng(seed)

    rng.shuffle(pool)

    candidates = pool[:max_candidates]

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    print(
        f"Generated pool of {len(pool)} "
        f"new possible expressions."
    )

    print(
        f"Selected {len(candidates)} "
        f"candidates for this batch."
    )

    if len(candidates) < max_candidates:
        print(
            "Warning: not enough unseen expressions "
            "were available to fill the requested batch."
        )

    return candidates


# ============================================================
# SAVE CANDIDATES
# ============================================================

def save_candidates(
    candidates: list[dict],
) -> None:

    CANDIDATES_OUT.write_text(
        json.dumps(
            candidates,
            indent=2,
        )
    )

    print(
        f"Saved {len(candidates)} "
        f"candidates to {CANDIDATES_OUT}"
    )


# ============================================================
# PREVIEW
# ============================================================

def preview_candidates(
    candidates: list[dict],
    n: int = 10,
) -> None:

    print("\nPreview:")

    for i, candidate in enumerate(
        candidates[:n],
        start=1,
    ):

        field_type_value = candidate.get(
            "field_type",
            "unknown",
        )

        expression = candidate.get(
            "expression",
            "",
        )

        neutralization = candidate.get(
            "neutralization",
            "NONE",
        )

        print(
            f"  {i:02d}. "
            f"[{field_type_value:11s}] "
            f"{expression} "
            f"(neut={neutralization})"
        )


# ============================================================
# COMMAND LINE
# ============================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Generate fresh BRAIN alpha candidates "
            "while avoiding previously tested expressions."
        )
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=25,
        help="Number of candidates to generate.",
    )

    parser.add_argument(
        "--fundamental-sample",
        type=int,
        default=15,
        help="Number of fundamental fields to sample.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Optional random seed. "
            "Leave empty for fresh randomness."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    args = parse_args()

    print("=" * 60)
    print("ALPHA GENERATOR")
    print("=" * 60)

    if args.seed is None:
        print(
            "Mode: FRESH RANDOM GENERATION"
        )
    else:
        print(
            f"Mode: REPRODUCIBLE "
            f"(seed={args.seed})"
        )

    print()

    candidates = generate_candidates(
        max_candidates=args.max_candidates,
        fundamental_sample_size=args.fundamental_sample,
        seed=args.seed,
    )

    save_candidates(candidates)

    preview_candidates(candidates)

    print()
    print("Generation complete.")