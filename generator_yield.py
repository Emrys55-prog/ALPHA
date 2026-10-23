"""
Metadata-aware yield-ratio generator.
VECTOR fields are reduced with vec_avg(...) before arithmetic/time-series
operators. GROUP/UNIVERSE/SYMBOL fields are rejected.
"""
import json, sys
from pathlib import Path
from field_rules import load_field_metadata, is_numeric_field, operand, field_type

CANDIDATES_OUT = Path("candidates.json")
DEFAULT_DENOMINATOR = "cap"
TS_RANK_WINDOWS = [20, 60, 120, 250]
ZSCORE_WINDOWS = [20, 60, 120]
DELTA_WINDOWS = [5, 20, 60]
NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY"]

def build(field, denominator, metadata):
    ratio = f"{operand(field, metadata)}/{operand(denominator, metadata)}"
    templates = []
    for w in TS_RANK_WINDOWS:
        templates.append(("yield_tsrank", f"group_rank(ts_rank({ratio}, {w}), subindustry)", w))
    for w in ZSCORE_WINDOWS:
        templates.append(("yield_zscore", f"group_rank(ts_zscore({ratio}, {w}), subindustry)", w))
    for w in DELTA_WINDOWS:
        templates.append(("yield_delta", f"group_rank(-ts_delta({ratio}, {w}), subindustry)", w))
    templates.append(("yield_level", f"group_rank({ratio}, subindustry)", None))
    out = []
    for name, expr, window in templates:
        for neut in NEUTRALIZATIONS:
            out.append({
                "expression": expr, "template": name, "field": field,
                "field_type": field_type(field, metadata),
                "denominator": denominator,
                "denominator_type": field_type(denominator, metadata),
                "window": window, "neutralization": neut,
                "universe": "TOP3000", "region": "USA", "delay": 1,
                "truncation": 0.08, "source_cluster": f"yield_{field}",
            })
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); CANDIDATES_OUT.write_text("[]"); sys.exit(1)
    field = sys.argv[1]
    denominator = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DENOMINATOR
    metadata = load_field_metadata()
    if field not in metadata or not is_numeric_field(field, metadata):
        print(f"ERROR: '{field}' is not a numeric field in the cache.")
        CANDIDATES_OUT.write_text("[]"); sys.exit(1)
    if denominator != DEFAULT_DENOMINATOR and (
        denominator not in metadata or not is_numeric_field(denominator, metadata)):
        print(f"ERROR: denominator '{denominator}' is not a numeric field.")
        CANDIDATES_OUT.write_text("[]"); sys.exit(1)
    candidates = build(field, denominator, metadata)
    CANDIDATES_OUT.write_text(json.dumps(candidates, indent=2))
    print(f"Saved {len(candidates)} candidates for {field}/{denominator} to {CANDIDATES_OUT}")
    for c in candidates[:6]:
        print(f"  [{c['field_type']}] {c['expression']} (neut={c['neutralization']})")
