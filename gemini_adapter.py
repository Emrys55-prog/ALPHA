"""Gemini free-tier adapter for research_loop.py; uses Python's standard library."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

SYSTEM = """You are the idea-generation and research-reasoning worker in a quantitative alpha research loop. Propose falsifiable, economically motivated hypotheses and translate them into the supplied FASTEXPR syntax. Use only supplied field IDs and verified operators. Each idea must use a distinct signal mechanism; changing only a window or neutralization is not a new hypothesis. Read prior outcomes as evidence, avoid failed/repeated patterns, and explain how each idea addresses previous feedback. Do not claim an untested idea is profitable. Return only the requested structured candidates."""

SCHEMA = {
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "expression": {"type": "string"}, "hypothesis": {"type": "string"},
            "novelty": {"type": "string"}, "field": {"type": "string"},
            "neutralization": {"type": "string"}
        },
        "required": ["expression", "hypothesis", "novelty", "field", "neutralization"]
    }}}
}


def generate_ideas(prompt):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("ALPHA_LLM_MODEL", "gemini-3.8-flash").strip()
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY in PowerShell. Do not save it in project files.")
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + urllib.parse.quote(model, safe="") + ":generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=True)}]}],
        "generationConfig": {"maxOutputTokens": 4096, "responseMimeType": "application/json", "responseSchema": SCHEMA}
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "x-goog-api-key": key, "Content-Type": "application/json"
    })
    data = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"Gemini API HTTP {exc.code}: {detail}") from None
            try: delay = min(30, max(1, float(exc.headers.get("Retry-After", ""))))
            except ValueError: delay = 2 ** (attempt + 1)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3: raise RuntimeError(f"Gemini API request failed: {exc}") from None
            time.sleep(2 ** (attempt + 1))
    candidates = (data or {}).get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates; check model name and AI Studio quota.")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason", "unknown")
    if finish_reason not in ("STOP", "unknown"):
        raise RuntimeError(f"Gemini did not finish the structured response (finishReason={finish_reason}). No BRAIN simulation was started.")
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if part.get("text"))
    if not text: raise RuntimeError("Gemini returned no text; check response finish reason and safety feedback.")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned malformed structured JSON (finishReason={finish_reason}, {exc}). No BRAIN simulation was started; retry with a smaller prompt or check the selected model.") from None
    if not isinstance(result, dict) or not isinstance(result.get("candidates"), list):
        raise ValueError('Expected a JSON object with a "candidates" array.')
    return result["candidates"]
