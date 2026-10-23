ALPHA metadata-driven compatibility fix

The field cache contains MATRIX, VECTOR, GROUP, UNIVERSE and SYMBOL fields.
The old generators treated nearly everything as a scalar fundamental.

This replacement:
- uses actual cached field types;
- wraps VECTOR operands with vec_avg(...) before numeric/time-series use;
- excludes non-numeric field types from generic generators;
- normalizes VECTOR fields again at simulation time as a safety net;
- gives the LLM field types in research_loop.py;
- stops old event-input failures from permanently blacklisting VECTOR fields.

Example:
  old:  group_rank(ts_rank(shares_sold_short_count_5_1555, 15), subindustry)
  new:  group_rank(ts_rank(vec_avg(shares_sold_short_count_5_1555), 15), subindustry)

No submission behavior was added or changed.
