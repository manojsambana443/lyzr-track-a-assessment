import json
import time

from taxonomy import (
    CLOSED_SET_PROMPT, NOISE_PATTERNS, REMEDIATIONS, CATEGORIES, ROOT_CAUSES,
)
from llm_backend import get_backend, cost_usd, estimate_tokens

CONFIDENCE_THRESHOLD = 0.6


def _is_cheap_path_noise(message: str) -> bool:
    return any(message.startswith(p) or message == p for p in NOISE_PATTERNS)


def _user_prompt(row):
    return f"service={row['service']} severity={row['severity']} message=\"{row['message']}\""


def _parse_llm_json(raw_text):
    try:
        start = raw_text.index("{")
        end = raw_text.rindex("}") + 1
        return json.loads(raw_text[start:end])
    except Exception:
        return {"is_incident": None, "category": None, "root_cause": None,
                 "remediation": None, "confidence": 0.0}


def _validate_closed_set(parsed):
    """Enum validation on the way out -- reject anything not in the fixed
    catalogs, regardless of what the model said."""
    cat = parsed.get("category")
    root = parsed.get("root_cause")
    rem = parsed.get("remediation")
    if cat not in CATEGORIES:
        cat = None
    if root not in ROOT_CAUSES:
        root = None
    if rem not in REMEDIATIONS:
        rem = None
    return cat, root, rem


def _normalize_confidence(raw):
    """Lyzr agents sometimes return confidence as a word ("high"/"medium"/"low")
    instead of a 0-1 float, depending on how the model chooses to answer.
    Accept both."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        word = raw.strip().lower()
        word_map = {"high": 0.9, "medium": 0.65, "med": 0.65, "low": 0.3}
        if word in word_map:
            return word_map[word]
        try:
            return float(word.rstrip("%")) / (100 if "%" in word else 1)
        except ValueError:
            return 0.0
    return 0.0


def _score_one_call(row, backend, model, ground_truth_lookup=None, pace_s=0.0):
    """Makes exactly one LLM call for this row's message and returns a
    filled-in record dict (LLM cost/latency counted once here)."""
    prompt = _user_prompt(row)
    gt = None
    if ground_truth_lookup is not None:
        gt = ground_truth_lookup.get(row["message"])
    if hasattr(backend, "call") and backend.__class__.__name__ == "SimulatedBackend":
        result = backend.call(CLOSED_SET_PROMPT, prompt, gt=gt)
    else:
        result = backend.call(CLOSED_SET_PROMPT, prompt)
        if pace_s > 0 and backend.__class__.__name__ == "LyzrStudioBackend":
            time.sleep(pace_s)
    parsed = _parse_llm_json(result.raw_json)
    cat, root, rem = _validate_closed_set(parsed)
    confidence = _normalize_confidence(parsed.get("confidence"))
    is_incident = bool(parsed.get("is_incident"))
    escalate = (not is_incident and confidence < CONFIDENCE_THRESHOLD) or \
               (is_incident and (confidence < CONFIDENCE_THRESHOLD or not rem))
    cost = cost_usd(result.model, result.input_tokens, result.output_tokens)
    return {
        "pred_is_incident": is_incident,
        "pred_category": cat,
        "pred_root_cause": root,
        "pred_remediation": rem,
        "pred_confidence": confidence,
        "escalated": escalate,
        "llm_called": True,
        "latency_s": result.latency_s,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": cost,
        "model": result.model,
        "backend": result.backend,
    }


def run_naive_baseline(rows, model="claude-sonnet-4-6", pace_s=0.0):
    """One full LLM call per raw row. No dedup, no routing, no caching.
    This is the required comparison point -- deliberately wasteful."""
    backend = get_backend(model, purpose="naive")
    ground_truth_lookup = {
        r["message"]: {
            "is_incident": r["is_labeled"],
            "category": r["gt_category"],
            "root_cause": r["gt_root_cause"],
            "remediation": r["gt_remediation"],
        }
        for r in rows if r["is_labeled"] == "yes"
    }
    # also mark non-incident ground truth for noise rows so the simulated
    # backend can be graded on those too
    for r in rows:
        if r["is_labeled"] != "yes" and r["message"] not in ground_truth_lookup:
            ground_truth_lookup.setdefault(
                r["message"], {"is_incident": _looks_like_incident(r["message"])}
            )

    records = []
    call_records = []  # one entry per ACTUAL LLM call -- naive makes 455 of these
    t0 = time.perf_counter()
    for row in rows:
        rec = _score_one_call(row, backend, model, ground_truth_lookup, pace_s=pace_s)
        rec.update({
            "event_id": row["event_id"],
            "is_labeled": row["is_labeled"] == "yes" if isinstance(row["is_labeled"], str) else row["is_labeled"],
            "gt_category": row["gt_category"],
            "gt_root_cause": row["gt_root_cause"],
            "gt_remediation": row["gt_remediation"],
            "is_true_noise": _is_cheap_path_noise(row["message"]),
        })
        records.append(rec)
        call_records.append(dict(rec))  # naive: every row is its own real call
    measured_wall_clock_s = time.perf_counter() - t0
    # In simulated mode calls aren't real network round-trips, so measured
    # wall-clock is meaningless; use the sum of simulated per-call latency
    # as the single-worker wall-clock proxy instead (real mode: keep the
    # actually-measured value, which already reflects real network time).
    if records and records[0]["backend"] == "simulated":
        wall_clock_s = sum(r["latency_s"] for r in call_records)
    else:
        wall_clock_s = measured_wall_clock_s
    return records, call_records, wall_clock_s


def _looks_like_incident(message):
    return not _is_cheap_path_noise(message)


def run_optimized_build(rows, model="claude-3-5-haiku-latest", pace_s=0.0):
    """
    Levers applied, in order:
      1. Cheap-path noise routing (zero LLM cost) for the 6 structurally
         obvious no-op message templates.
      2. Dedup/clustering: every remaining row is grouped by exact message
         text. The LLM is called ONCE per unique message, not once per row
         -- this is the single biggest cost lever per the assignment brief.
      3. Confidence gating: any cluster result below CONFIDENCE_THRESHOLD
         (or missing a valid remediation) is escalated to a human instead
         of guessed.
      4. Closed-set validation on the way out (see pipeline._validate_closed_set).
    """
    backend = get_backend(model, purpose="optimized")
    ground_truth_lookup = {
        r["message"]: {
            "is_incident": r["is_labeled"],
            "category": r["gt_category"],
            "root_cause": r["gt_root_cause"],
            "remediation": r["gt_remediation"],
        }
        for r in rows if r["is_labeled"] == "yes"
    }
    for r in rows:
        if r["is_labeled"] != "yes" and r["message"] not in ground_truth_lookup:
            ground_truth_lookup.setdefault(
                r["message"], {"is_incident": _looks_like_incident(r["message"])}
            )

    clusters = {}
    for row in rows:
        clusters.setdefault(row["message"], []).append(row)

    cluster_results = {}
    call_records = []  # one entry per ACTUAL LLM call -- optimized makes ~10 of these
    t0 = time.perf_counter()
    n_llm_calls = 0
    for message, members in clusters.items():
        if _is_cheap_path_noise(message):
            cluster_results[message] = {
                "pred_is_incident": False, "pred_category": None,
                "pred_root_cause": None, "pred_remediation": None,
                "pred_confidence": 0.99, "escalated": False, "llm_called": False,
                "latency_s": 0.0, "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "model": "rule-based-router", "backend": "cheap_path",
            }
            continue
        # one representative row from the cluster drives the single LLM call
        rep_row = members[0]
        rec = _score_one_call(rep_row, backend, model, ground_truth_lookup, pace_s=pace_s)
        n_llm_calls += 1
        cluster_results[message] = rec
        call_records.append(dict(rec))  # cost/tokens/latency counted ONCE per cluster call
    measured_wall_clock_s = time.perf_counter() - t0

    records = []
    for row in rows:
        base = cluster_results[row["message"]]
        rec = dict(base)
        rec.update({
            "event_id": row["event_id"],
            "is_labeled": row["is_labeled"] == "yes" if isinstance(row["is_labeled"], str) else row["is_labeled"],
            "gt_category": row["gt_category"],
            "gt_root_cause": row["gt_root_cause"],
            "gt_remediation": row["gt_remediation"],
            "is_true_noise": _is_cheap_path_noise(row["message"]),
        })
        records.append(rec)
    if call_records and call_records[0]["backend"] == "simulated":
        wall_clock_s = sum(r["latency_s"] for r in call_records)
    else:
        wall_clock_s = measured_wall_clock_s
    return records, call_records, wall_clock_s, n_llm_calls, len(clusters)
