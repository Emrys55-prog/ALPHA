"""LLM idea-provider adapters. API secrets are read from the environment only."""
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["candidates"],
    "properties": {"candidates": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["expression", "hypothesis", "novelty", "field", "neutralization"],
        "properties": {
            "expression": {"type": "string"}, "hypothesis": {"type": "string"},
            "novelty": {"type": "string"}, "field": {"type": "string"},
            "neutralization": {"type": "string", "enum": ["NONE", "INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"]}
        }
    }}}
}

SYSTEM_PROMPT = """You are the idea-generation and research-reasoning worker in a quantitative alpha research loop. Propose falsifiable, economically motivated hypotheses and translate them into the supplied FASTEXPR syntax. Use only supplied field IDs and verified operators. Each idea should represent a distinct signal mechanism; changing only a window or neutralization is not a new hypothesis. Read prior results as evidence: avoid repeated expressions and patterns associated with failures, and explain how each new idea addresses prior feedback. Do not claim that an untested idea is profitable. Return only the requested structured candidates."""


def _openai(prompt):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("ALPHA_LLM_MODEL", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Set it in this PowerShell session; never put it in the project files.")
    if not model:
        raise RuntimeError("ALPHA_LLM_MODEL is missing. Choose a model available to your API account.")
    payload = {
        "model": model,
        "store": False,
        "max_output_tokens": 2500,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
        ],
        "text": {"format": {"type": "json_schema", "name": "alpha_ideas", "strict": True, "schema": SCHEMA}},
    }
    url = os.environ.get("ALPHA_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses"
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
        "Authorization": "Bearer " + api_key, "Content-Type": "application/json",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"LLM API returned HTTP {exc.code}: {detail}") from None
            retry = exc.headers.get("Retry-After", "")
            try: delay = min(30, max(1, float(retry)))
            except ValueError: delay = 2 ** (attempt + 1)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3: raise RuntimeError(f"LLM API request failed: {exc}") from None
            time.sleep(2 ** (attempt + 1))
    if data.get("status") == "incomplete":
        raise RuntimeError("LLM response was incomplete; reduce the requested batch size or output length.")
    texts, refusals = [], []
    for item in data.get("output", []):
        if item.get("type") != "message": continue
        for part in item.get("content", []):
            if part.get("type") == "output_text": texts.append(part.get("text", ""))
            elif part.get("type") == "refusal": refusals.append(part.get("refusal", "refused"))
    if refusals: raise RuntimeError("LLM declined the request: " + "; ".join(refusals)[:400])
    if not texts: raise RuntimeError("LLM response contained no structured output text.")
    result = json.loads("".join(texts))
    return result["candidates"]


def _command(prompt):
    raw = os.environ.get("ALPHA_IDEA_COMMAND", "").strip()
    if not raw: raise RuntimeError("Set ALPHA_IDEA_COMMAND for command-provider mode.")
    proc = subprocess.run(shlex.split(raw, posix=(os.name != "nt")), input=json.dumps(prompt), text=True, capture_output=True, timeout=180)
    if proc.returncode: raise RuntimeError(f"Idea provider exited {proc.returncode}: {proc.stderr[-800:]}")
    result = json.loads(proc.stdout)
    if not isinstance(result, dict) or not isinstance(result.get("candidates"), list):
        raise ValueError('Provider output must be a JSON object with a "candidates" array.')
    return result["candidates"]


def generate_ideas(prompt):
    provider = os.environ.get("ALPHA_LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai": return _openai(prompt)
    if provider == "command": return _command(prompt)
    raise RuntimeError("ALPHA_LLM_PROVIDER must be 'openai' or 'command'.")
