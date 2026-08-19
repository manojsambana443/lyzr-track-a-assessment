#!/usr/bin/env python3
"""
Recovers a results summary (accuracy, latency, cost, throughput) from an
events CSV that was already written by main.py, WITHOUT making any new API
calls. Use this if a run finished but the summary JSON wasn't saved (e.g.
an older harness version), so you don't have to spend credits re-running it.

USAGE
-----
  python3 recover_summary.py events_naive.csv naive
  python3 recover_summary.py events_optimized.csv optimized
"""
import csv
import json
import sys

from metrics import summarize_run


def str2bool(s):
    return str(s).strip().lower() in ("true", "1", "yes")


def load_records(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    records = []
    for r in rows:
        rec = dict(r)
        rec["is_labeled"] = str2bool(r["is_labeled"])
        rec["escalated"] = str2bool(r.get("escalated", "False"))
        rec["llm_called"] = str2bool(r.get("llm_called", "True"))
        rec["latency_s"] = float(r["latency_s"]) if r["latency_s"] else 0.0
        rec["input_tokens"] = int(r["input_tokens"]) if r["input_tokens"] else 0
        rec["output_tokens"] = int(r["output_tokens"]) if r["output_tokens"] else 0
        rec["cost_usd"] = float(r["cost_usd"]) if r["cost_usd"] else 0.0
        for key in ("pred_category", "pred_root_cause", "pred_remediation"):
            rec[key] = r[key] if r[key] else None
        records.append(rec)
    return records


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 recover_summary.py <events_csv> <naive|optimized>")
        sys.exit(1)
    path, run_name = sys.argv[1], sys.argv[2]
    records = load_records(path)

    if run_name == "naive":
        # naive: every row IS its own real call, so call_records == records
        call_records = [r for r in records]
    else:
        # optimized: only rows where llm_called=True map to a real call, but
        # each unique cluster's call was only counted once during the run,
        # not once per member row -- since the CSV has it duplicated across
        # every member row, we dedupe back down by (message not stored here,
        # so we approximate with round-tripped cost/latency values, which
        # were already de-duplicated correctly at save time). We reconstruct
        # unique calls by grouping identical (latency_s, cost_usd, model)
        # combinations that also have llm_called=True.
        seen = set()
        call_records = []
        for r in records:
            if not r["llm_called"]:
                continue
            key = (r["latency_s"], r["cost_usd"], r["input_tokens"], r["output_tokens"], r["model"])
            if key in seen:
                continue
            seen.add(key)
            call_records.append(r)

    # wall clock isn't recoverable exactly from the CSV alone (it wasn't a
    # per-row column), so approximate it as the sum of call latencies --
    # this matches how the harness itself computes it in simulated mode,
    # and is a reasonable stand-in for a sequential, unparallelized run.
    wall_clock_s = sum(r["latency_s"] for r in call_records)

    summary = summarize_run(run_name, records, call_records, wall_clock_s)
    out_path = f"results_{run_name}_recovered.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Recovered summary written to {out_path}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
