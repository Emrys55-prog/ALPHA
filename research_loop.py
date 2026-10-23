"""Feedback-driven research wrapper around the existing BRAIN simulation scripts.
LLM provider contract: command reads one JSON prompt on stdin and writes {"candidates":[...]} on stdout. Never submits alphas.
"""
import argparse, hashlib, json, os, re, shlex, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

from field_rules import load_field_metadata, normalize_expression, validate_fields, field_type

ROOT = Path(__file__).resolve().parent
FIELDS = ROOT / "field_cache" / "fields_USA_TOP3000_d1.json"
MEMORY = ROOT / "research_loop" / "memory.sqlite3"
REPORT = ROOT / "research_loop" / "latest_report.json"
RESULTS = ROOT / "research_loop" / "simulation_results.json"
OPS = {"rank", "group_rank", "ts_delta", "ts_zscore", "ts_rank", "vec_avg"}  # seen in existing generators
GROUPS = {"subindustry", "industry", "sector", "market"}
NEUTS = {"NONE", "INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def db_open():
    MEMORY.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(MEMORY)
    db.execute("""CREATE TABLE IF NOT EXISTS hypotheses (
        key TEXT PRIMARY KEY, expression TEXT, hypothesis TEXT, novelty TEXT,
        status TEXT, feedback TEXT, stats TEXT, alpha_id TEXT, created_at TEXT)""")
    return db


def key_for(c):
    keys = ("expression", "neutralization", "region", "universe", "delay", "decay", "truncation")
    return hashlib.sha256(json.dumps({k:c.get(k) for k in keys}, sort_keys=True).encode()).hexdigest()


def validate(expr, fields):
    if not expr or len(expr) > 500 or any(x in expr for x in (";", "\n", "\r", "=", "[", "]", "{", "}")):
        return "empty, too long, or disallowed syntax"
    if expr.count("(") != expr.count(")"):
        return "unbalanced parentheses"
    funcs = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", expr))
    unknown = funcs - OPS
    if unknown:
        return "unverified operator(s): " + ", ".join(sorted(unknown))
    names = IDENT.findall(re.sub(r"\b[A-Za-z_]\w*\s*\(", " ", expr))
    invalid = {n for n in names if n not in fields and n.lower() not in GROUPS}
    if invalid:
        return "field/group not in verified cache: " + ", ".join(sorted(invalid))
    residue = IDENT.sub("", expr)
    residue = re.sub(r"\s|[0-9.+\-*/,()]", "", residue)
    return "contains unsupported characters" if residue else ""


def ask_llm(prompt):
    if os.environ.get("ALPHA_LLM_PROVIDER", "gemini").strip().lower() == "gemini":
        from gemini_adapter import generate_ideas
        return generate_ideas(prompt)
    from llm_worker import generate_ideas
    return generate_ideas(prompt)


def choose_prompt_fields(rows, seed, limit=100):
    import random
    buckets = {}
    for row in rows:
        category = (row.get("category") or {}).get("name") or "Other"
        buckets.setdefault(category, []).append(row.get("id", ""))
    rng = random.Random(seed)
    for values in buckets.values(): rng.shuffle(values)
    chosen = []
    categories = sorted(buckets)
    while len(chosen) < limit:
        added = False
        for category in categories:
            if buckets[category]:
                chosen.append(buckets[category].pop())
                added = True
                if len(chosen) >= limit: break
        if not added: break
    return chosen

def prior_feedback(db, limit=24):
    rows = db.execute("SELECT expression,hypothesis,status,feedback,stats FROM hypotheses ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"expression":r[0], "hypothesis":r[1], "status":r[2], "feedback":json.loads(r[3]), "stats":json.loads(r[4])} for r in rows]


def correlation_advisory(expr, alpha_id, threshold):
    """Read PnL cached by the existing alpha_db.py; never call a new endpoint."""
    path = ROOT / "alphas.db"
    if not path.exists(): return []
    conn = sqlite3.connect(path)
    try: rows = conn.execute("SELECT expression,alpha_id,daily_pnl FROM alphas WHERE daily_pnl IS NOT NULL").fetchall()
    except sqlite3.Error: return []
    finally: conn.close()
    current = next((r for r in rows if r[0] == expr or (alpha_id and r[1] == alpha_id)), None)
    if not current: return []
    try: cp = [float(v) for v in json.loads(current[2])]
    except Exception: return []
    cr = [cp[i+1]-cp[i] for i in range(len(cp)-1)]
    out = []
    for e, aid, raw in rows:
        if e == expr or (alpha_id and aid == alpha_id): continue
        try: p = [float(v) for v in json.loads(raw)]
        except Exception: continue
        rr = [p[i+1]-p[i] for i in range(len(p)-1)]
        n = min(len(cr), len(rr))
        if n < 10: continue
        a, b = cr[-n:], rr[-n:]
        ma, mb = sum(a)/n, sum(b)/n
        da, dbb = [x-ma for x in a], [x-mb for x in b]
        va, vb = sum(x*x for x in da), sum(x*x for x in dbb)
        if va and vb:
            corr = sum(x*y for x,y in zip(da,dbb))/(va*vb)**0.5
            if abs(corr) >= threshold: out.append({"alpha_id":aid, "expression":e, "correlation":round(corr,4)})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--max-sims", type=int, default=10, help="hard cap for this invocation")
    ap.add_argument("--correlation-threshold", type=float, default=.7)
    args = ap.parse_args()
    if min(args.rounds, args.batch_size, args.max_sims) < 1: ap.error("all limits must be positive")
    provider = os.environ.get("ALPHA_LLM_PROVIDER", "gemini").strip().lower()
    if provider == "openai" and (not os.environ.get("OPENAI_API_KEY") or not os.environ.get("ALPHA_LLM_MODEL")):
        raise SystemExit("OpenAI mode needs OPENAI_API_KEY and ALPHA_LLM_MODEL. No BRAIN login or simulations were started.")
    if provider == "command" and not os.environ.get("ALPHA_IDEA_COMMAND"):
        raise SystemExit("Command mode needs ALPHA_IDEA_COMMAND. No BRAIN login or simulations were started.")
    if provider == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Gemini mode needs GEMINI_API_KEY. No BRAIN login or simulations were started.")
    if provider not in ("gemini", "openai", "command"): ap.error("ALPHA_LLM_PROVIDER must be gemini, openai, or command")
    field_rows = json.loads(FIELDS.read_text(encoding="utf-8"))
    fields = {str(x.get("id")) for x in field_rows if x.get("id")}
    db = db_open()
    import simulate, alpha_db
    from auth import WQSession
    from qualify import classify
    simulate.RESULTS_OUT = RESULTS
    alpha_db.RESULTS_IN = RESULTS
    session = WQSession(); session.login()
    report = {"started_at":datetime.now(timezone.utc).isoformat(), "rounds":[], "submission_performed":False}
    spent = 0
    for number in range(1, args.rounds+1):
        remaining = args.max_sims-spent
        if remaining <= 0: break
        prompt = {
            "task":"Generate a small, diverse research batch of BRAIN FASTEXPR alpha hypotheses.",
            "output_schema":{"candidates":[{"expression":"...", "hypothesis":"economic rationale", "novelty":"difference from tested work", "neutralization":"NONE|INDUSTRY|SUBINDUSTRY|SECTOR|MARKET"}]},
            "constraints":["Use only supplied cached fields and verified operators.","Avoid prior expressions and failed hypothesis patterns.","Return no more than requested_count.","Treat outcomes as evidence, not proof."],
            "fields":[
                {"id": fid, "type": field_type(fid, metadata),
                 "description": (metadata.get(fid) or {}).get("description", "")[:180]}
                for fid in choose_prompt_fields(field_rows, number)
            ], "verified_operators":sorted(OPS), "requested_count":min(args.batch_size,remaining), "previous_results_and_feedback":prior_feedback(db, limit=10)}
        proposed = ask_llm(prompt)
        accepted, rejected, seen = [], [], set()
        for item in proposed:
            if not isinstance(item,dict): rejected.append({"reason":"candidate must be an object"}); continue
            raw_expr = str(item.get("expression","")).strip()
            expr = normalize_expression(raw_expr, metadata)
            reason = validate(expr,fields)
            neut = str(item.get("neutralization","NONE")).upper()
            if not reason:
                unknown_fields = validate_fields(expr, metadata)
                if unknown_fields:
                    reason = "unknown field(s): " + ", ".join(unknown_fields)
            if not reason and neut not in NEUTS: reason = "unverified neutralization"
            if reason: rejected.append({"expression":expr,"reason":reason}); continue
            c = {"expression":expr,"hypothesis":str(item.get("hypothesis", ""))[:1000],"novelty":str(item.get("novelty", ""))[:500],"field":item.get("field"),"neutralization":neut,"universe":"TOP3000","region":"USA","delay":1,"decay":6,"truncation":0.08}
            k = key_for(c)
            if k in seen or db.execute("SELECT 1 FROM hypotheses WHERE key=?",(k,)).fetchone(): rejected.append({"expression":expr,"reason":"duplicate tested candidate/settings"}); continue
            seen.add(k); accepted.append((k,c))
            if len(accepted) >= min(args.batch_size,remaining): break
        rr = {"round":number,"proposed":len(proposed),"rejected":rejected,"simulated":[]}
        if not accepted:
            rr["stop_reason"]="No novel, valid LLM candidates."; report["rounds"].append(rr); break
        spent += len(accepted)  # reserve budget before starting network activity
        batch = simulate.run_batch([c for _,c in accepted],session.session)
        try:
            alpha_db.import_results(); alpha_db.check_correlation()
        except Exception as exc:
            corr_error = str(exc)[:240]
        else: corr_error = None
        results_by_key = {key_for(item): item for item in batch}
        for k,c in accepted:
            result = results_by_key[k]
            verdict = classify(result) if result.get("status")=="SUCCESS" else {"qualifies":False,"reasons":[result.get("error","simulation failed")]}
            fails = [f"{x.get('name')}:{x.get('result')}" for x in result.get("raw_checks",[]) if x.get("result") in ("FAIL","PENDING")]
            corr = correlation_advisory(c["expression"],result.get("alpha_id"),args.correlation_threshold) if not corr_error else []
            feedback = {"qualification_reasons":verdict.get("reasons",[]),"BRAIN_checks":fails,"local_high_correlations":corr,"local_correlation_error":corr_error,"note":"Local screen is advisory; BRAIN SELF_CORRELATION is authoritative and may remain pending."}
            status = "FAILED" if result.get("status")!="SUCCESS" else ("QUALIFIED" if verdict.get("qualifies") else "REVIEW")
            stats = {k:result.get(k) for k in ("sharpe","fitness","turnover","drawdown","checks_passed","checks_total")}
            db.execute("INSERT OR IGNORE INTO hypotheses VALUES (?,?,?,?,?,?,?,?,?)",(k,c["expression"],c["hypothesis"],c["novelty"],status,json.dumps(feedback),json.dumps(stats),result.get("alpha_id"),datetime.now(timezone.utc).isoformat()))
            rr["simulated"].append({"expression":c["expression"],"alpha_id":result.get("alpha_id"),"status":status,"stats":stats,"feedback":feedback})
        db.commit(); report["rounds"].append(rr)
    report.update({"finished_at":datetime.now(timezone.utc).isoformat(),"simulation_count":spent,"submission_performed":False})
    REPORT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    db.close()
    print(f"Research loop complete: {spent} simulation slots. Report: {REPORT}")
    print("No alphas were submitted. Use the existing submit.py confirmation after reviewing results.")

if __name__ == "__main__": main()







