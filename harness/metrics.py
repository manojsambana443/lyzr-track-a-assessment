import statistics
from collections import defaultdict

from taxonomy import CATEGORIES


def macro_f1(y_true, y_pred, labels):
    """Macro-averaged F1 over the given label set. Missing/None predictions
    count as wrong (never silently dropped)."""
    per_label = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        if tp + fp == 0:
            precision = 0.0
        else:
            precision = tp / (tp + fp)
        if tp + fn == 0:
            recall = 0.0
        else:
            recall = tp / (tp + fn)
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        per_label[label] = f1
    labels_present = [l for l in labels if y_true.count(l) > 0]
    if not labels_present:
        return 0.0, per_label
    return sum(per_label[l] for l in labels_present) / len(labels_present), per_label


def percentile(values, pct):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def summarize_run(run_name, records, call_records, wall_clock_s):
    """
    records: list of dicts, ONE PER EVENT (455 rows) -- used only for
        accuracy scoring (a cluster's prediction is shared by all its
        member events, which is correct: they really do get the same
        classification).
    call_records: list of dicts, ONE PER ACTUAL LLM CALL MADE -- used for
        every cost/latency/token metric, so a deduped cluster's cost is
        counted exactly once, not once per member event.
    """
    n = len(records)
    llm_calls = call_records

    labeled = [r for r in records if r["is_labeled"]]
    y_true_cat = [r["gt_category"] for r in labeled]
    y_pred_cat = [r["pred_category"] or "NONE" for r in labeled]
    y_true_root = [r["gt_root_cause"] for r in labeled]
    y_pred_root = [r["pred_root_cause"] or "NONE" for r in labeled]

    f1_cat, _ = macro_f1(y_true_cat, y_pred_cat, CATEGORIES)
    root_labels = sorted(set(y_true_root))
    root_correct = sum(1 for t, p in zip(y_true_root, y_pred_root) if t == p)
    root_acc = root_correct / len(labeled) if labeled else 0.0

    remediation_correct = sum(
        1 for r in labeled if r["pred_remediation"] == r["gt_remediation"]
    )
    remediation_acc = remediation_correct / len(labeled) if labeled else 0.0

    free_form_remediations = sum(
        1 for r in records
        if r["pred_remediation"] and r["pred_remediation"] not in APPROVED_REMEDIATIONS
    )

    # false-escalation: a pure-noise event that got escalated to a human
    # (should never happen once cheap-path routing works). This is distinct
    # from an LLM call being spent on noise, which is a pure cost story.
    noise_events = [r for r in records if not r["is_labeled"] and r.get("is_true_noise")]
    false_escalations = sum(1 for r in noise_events if r["escalated"])
    wasted_llm_calls_on_noise = sum(1 for r in noise_events if r["llm_called"])

    latencies = [r["latency_s"] for r in llm_calls]
    p50 = percentile(latencies, 0.5)
    p95 = percentile(latencies, 0.95)

    total_tokens_in = sum(r["input_tokens"] for r in llm_calls)
    total_tokens_out = sum(r["output_tokens"] for r in llm_calls)
    total_cost = sum(r["cost_usd"] for r in llm_calls)
    tokens_per_task = (total_tokens_in + total_tokens_out) / n if n else 0
    cost_per_task = total_cost / n if n else 0
    throughput = n / wall_clock_s * 60 if wall_clock_s > 0 else 0

    return {
        "run_name": run_name,
        "n_events": n,
        "n_llm_calls": len(llm_calls),
        "f1_category": f1_cat,
        "root_cause_accuracy": root_acc,
        "remediation_accuracy": remediation_acc,
        "free_form_remediation_count": free_form_remediations,
        "false_escalation_count": false_escalations,
        "false_escalation_rate": false_escalations / len(noise_events) if noise_events else 0.0,
        "wasted_llm_calls_on_noise": wasted_llm_calls_on_noise,
        "p50_latency_s": p50,
        "p95_latency_s": p95,
        "total_tokens": total_tokens_in + total_tokens_out,
        "tokens_per_task": tokens_per_task,
        "total_cost_usd": total_cost,
        "cost_per_task_usd": cost_per_task,
        "throughput_per_min": throughput,
        "wall_clock_s": wall_clock_s,
    }


from taxonomy import REMEDIATIONS as APPROVED_REMEDIATIONS  # noqa: E402
