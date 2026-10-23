# LLM alpha research loop

The LLM is the central idea-generation and research-reasoning worker. `llm_worker.py` calls OpenAI's Responses API by default and asks for schema-constrained JSON. `research_loop.py` supplies cached fields, verified operators, and prior outcomes, validates the expressions, simulates a small batch, and feeds the measured feedback into the next round. A command-based provider remains available as an alternative.

## OpenAI setup

Set these variables in PowerShell for the session. The API key stays in the environment and is never written to the project:

```powershell
$env:ALPHA_LLM_PROVIDER = 'openai'
$env:OPENAI_API_KEY = '<your API key>'
$env:ALPHA_LLM_MODEL = '<model available to your API account>'
python research_loop.py --rounds 3 --batch-size 4 --max-sims 10
```

Choose a model your API account can use; the project does not guess one. The direct API uses the Responses API with strict structured output, a bounded output size, and transient retry handling. There is one LLM request per research round. The prompt sends up to 180 field IDs, selected across the available field categories, instead of sending the full 4,367-field cache each time.

To use another provider, set `ALPHA_LLM_PROVIDER='command'` and configure `ALPHA_IDEA_COMMAND` for a command that reads a JSON prompt on stdin and returns `{"candidates":[...]}` JSON on stdout. Candidate objects contain `expression`, `hypothesis`, `novelty`, `field`, and `neutralization`.

## Safeguards and review

The loop validates expressions against the full local field cache and an operator allowlist observed in the existing generators (`rank`, `group_rank`, `ts_delta`, `ts_zscore`, `ts_rank`). It deduplicates expressions plus settings in `research_loop/memory.sqlite3`, applies a per-run simulation cap, and saves reports in `research_loop/latest_report.json`. It does not call `submit.py`; all real submissions still require the existing manual confirmation.

Correlation remains advisory: the existing local checker does not align histories by dates, and BRAIN's `SELF_CORRELATION` result is authoritative. A pending result is not treated as a pass.
