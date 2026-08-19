#!/usr/bin/env python3
"""
Reproducible benchmark harness for Lyzr Take-Home, Track A
(Auto-Remediation from Logs).

USAGE
-----
  # Real graded run (reviewer re-runs this):
  export ANTHROPIC_API_KEY=sk-ant-...
  python3 main.py --data ../track_a_logs.csv

  # Or against the actual published Lyzr Studio agent:
  export LYZR_API_KEY=...
  export LYZR_AGENT_ID=...
  python3 main.py --data ../track_a_logs.csv

  # No credentials in the environment -> falls back to a clearly-labeled
  # offline simulation so you can smoke-test the harness itself:
  python3 main.py --data ../track_a_logs.csv

OUTPUT
------
  results_table.md          -- the required naive vs optimized delta table
  results_table.json        -- same, machine-readable
  events_naive.csv          -- per-event predictions, naive run
  events_optimized.csv      -- per-event predictions, optimized run
"""
import argparse
import csv
import json
import sys

from data import load_rows
from pipeline import run_naive_baseline, run_optimized_build
from metrics import summarize_run
from llm_backend import resolve_backend


def write_events_csv(path, records):
    fields = ["event_id", "is_labeled", "gt_category", "gt_root_cause", "gt_remediation",
              "pred_is_incident", "pred_category", "pred_root_cause", "pred_remediation",
              "pred_confidence", "escalated", "llm_called", "latency_s", "input_tokens",
              "output_tokens", "cost_usd", "model", "backend"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)


def fmt_delta(naive, opt, pct=False, money=False, invert=False):
    if naive == 0:
        return "n/a"
    delta = (opt - naive) / abs(naive) * 100
    if invert:
        delta = -delta
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}%"


def print_table(naive_summary, opt_summary):
    rows = [
        ("Accuracy - category macro-F1", f"{naive_summary['f1_category']:.3f}",
         f"{opt_summary['f1_category']:.3f}", fmt_delta(naive_summary['f1_category'], opt_summary['f1_category'])),
        ("Accuracy - root-cause acc.", f"{naive_summary['root_cause_accuracy']:.3f}",
         f"{opt_summary['root_cause_accuracy']:.3f}", fmt_delta(naive_summary['root_cause_accuracy'], opt_summary['root_cause_accuracy'])),
        ("Accuracy - remediation acc.", f"{naive_summary['remediation_accuracy']:.3f}",
         f"{opt_summary['remediation_accuracy']:.3f}", fmt_delta(naive_summary['remediation_accuracy'], opt_summary['remediation_accuracy'])),
        ("Free-form remediation count (must be 0)", str(naive_summary['free_form_remediation_count']),
         str(opt_summary['free_form_remediation_count']), "-"),
        ("False-escalation rate (noise -> human/LLM)", f"{naive_summary['false_escalation_rate']:.3f}",
         f"{opt_summary['false_escalation_rate']:.3f}", "-"),
        ("p50 latency / task (s)", f"{naive_summary['p50_latency_s']:.2f}",
         f"{opt_summary['p50_latency_s']:.2f}", fmt_delta(naive_summary['p50_latency_s'], opt_summary['p50_latency_s'], invert=True)),
        ("p95 latency / task (s)", f"{naive_summary['p95_latency_s']:.2f}",
         f"{opt_summary['p95_latency_s']:.2f}", fmt_delta(naive_summary['p95_latency_s'], opt_summary['p95_latency_s'], invert=True)),
        ("Tokens / task (avg, all 455 events)", f"{naive_summary['tokens_per_task']:.0f}",
         f"{opt_summary['tokens_per_task']:.0f}", fmt_delta(naive_summary['tokens_per_task'], opt_summary['tokens_per_task'], invert=True)),
        ("Cost / task (avg, USD)", f"${naive_summary['cost_per_task_usd']:.6f}",
         f"${opt_summary['cost_per_task_usd']:.6f}", fmt_delta(naive_summary['cost_per_task_usd'], opt_summary['cost_per_task_usd'], invert=True)),
        ("Cost / full batch (USD)", f"${naive_summary['total_cost_usd']:.4f}",
         f"${opt_summary['total_cost_usd']:.4f}", fmt_delta(naive_summary['total_cost_usd'], opt_summary['total_cost_usd'], invert=True)),
        ("LLM calls made (of 455 events)", str(naive_summary['n_llm_calls']),
         str(opt_summary['n_llm_calls']), fmt_delta(naive_summary['n_llm_calls'], opt_summary['n_llm_calls'], invert=True)),
        ("Throughput (events/min)", f"{naive_summary['throughput_per_min']:.1f}",
         f"{opt_summary['throughput_per_min']:.1f}", fmt_delta(naive_summary['throughput_per_min'], opt_summary['throughput_per_min'])),
        ("Wall-clock, full batch (s)", f"{naive_summary['wall_clock_s']:.2f}",
         f"{opt_summary['wall_clock_s']:.2f}", fmt_delta(naive_summary['wall_clock_s'], opt_summary['wall_clock_s'], invert=True)),
    ]
    header = f"| Metric | Naive baseline | Optimized build | Delta |\n|---|---|---|---|\n"
    body = "\n".join(f"| {n} | {a} | {b} | {d} |" for n, a, b, d in rows)
    return header + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../track_a_logs.csv")
    ap.add_argument("--naive-model", default="claude-sonnet-4-6")
    ap.add_argument("--optimized-model", default="claude-3-5-haiku-latest")
    ap.add_argument("--limit", type=int, default=None,
                     help="only process the first N rows (for quick connectivity testing)")
    ap.add_argument("--pace-s", type=float, default=1.0,
                     help="minimum seconds between consecutive LLM calls (Lyzr backend only, "
                          "to avoid tripping a rate limit); set 0 to disable")
    ap.add_argument("--skip-naive", action="store_true",
                     help="skip the 455-call naive baseline (runs optimized build only, "
                          "useful when credits/quota are tight)")
    ap.add_argument("--skip-optimized", action="store_true",
                     help="skip the optimized build (naive baseline only)")
    args = ap.parse_args()

    backend_mode = resolve_backend()
    print(f"[harness] LLM backend mode: {backend_mode.upper()}")
    if backend_mode == "simulated":
        print("=" * 78)
        print("  SIMULATION MODE -- no ANTHROPIC_API_KEY or LYZR_API_KEY found.")
        print("  Numbers below are from a deterministic offline stand-in, NOT a real")
        print("  LLM. They validate the harness plumbing only. Set ANTHROPIC_API_KEY")
        print("  (or LYZR_API_KEY + LYZR_AGENT_ID) and re-run before submitting.")
        print("=" * 78)

    rows = load_rows(args.data)
    if args.limit:
        rows = rows[: args.limit]
        print(f"[harness] --limit set: only processing first {len(rows)} rows")
    print(f"[harness] loaded {len(rows)} events from {args.data} "
          f"({sum(1 for r in rows if r['is_labeled']=='yes')} labeled)")

    # Optimized build runs FIRST and is much cheaper (~10 calls vs 455) --
    # if credits run out or a transient error kills the process, we still
    # have the more important, cost-optimized results saved to disk before
    # spending anything on the expensive naive comparison run.
    if args.skip_optimized:
        opt_summary = None
        print("[harness] --skip-optimized set, skipping optimized build")
    else:
        print("[harness] running optimized build (cheap-path + dedup + confidence gating)...")
        opt_records, opt_calls, opt_wall, n_llm_calls, n_clusters = run_optimized_build(rows, model=args.optimized_model, pace_s=args.pace_s)
        opt_summary = summarize_run("optimized", opt_records, opt_calls, opt_wall)
        print(f"[harness] optimized build: {n_clusters} unique message clusters, "
              f"{n_llm_calls} LLM calls issued for {len(rows)} events "
              f"({(1 - n_llm_calls/len(rows))*100:.1f}% call reduction vs naive)")
        with open("results_optimized_only.json", "w") as f:
            json.dump(opt_summary, f, indent=2)
        write_events_csv("events_optimized.csv", opt_records)
        print("[harness] optimized results saved to results_optimized_only.json + events_optimized.csv "
              "(safe even if the naive run below fails or runs out of credits)")

    if args.skip_naive:
        naive_summary = None
        print("[harness] --skip-naive set, skipping naive baseline")
    else:
        print("[harness] running naive baseline (1 LLM call per event, no dedup/routing)...")
        naive_records, naive_calls, naive_wall = run_naive_baseline(rows, model=args.naive_model, pace_s=args.pace_s)
        naive_summary = summarize_run("naive", naive_records, naive_calls, naive_wall)
        write_events_csv("events_naive.csv", naive_records)
        with open("results_naive_only.json", "w") as f:
            json.dump(naive_summary, f, indent=2)
        print("[harness] naive results saved to results_naive_only.json + events_naive.csv")

    if naive_summary is None or opt_summary is None:
        print("[harness] one run was skipped -- no comparison table to print. "
              "Re-run without --skip-* flags once you have both results.")
        return

    print(f"[harness] optimized build: {n_clusters} unique message clusters, "
          f"{n_llm_calls} LLM calls issued for {len(rows)} events "
          f"({(1 - n_llm_calls/len(rows))*100:.1f}% call reduction vs naive)")

    table = print_table(naive_summary, opt_summary)
    print("\n" + table + "\n")

    with open("results_table.md", "w") as f:
        f.write(f"# Track A Results Table\n\nBackend mode: **{backend_mode}**\n\n" + table + "\n")
    with open("results_table.json", "w") as f:
        json.dump({"backend_mode": backend_mode, "naive": naive_summary, "optimized": opt_summary,
                    "n_clusters": n_clusters, "n_llm_calls_optimized": n_llm_calls}, f, indent=2)
    print("[harness] wrote results_table.md, results_table.json, events_naive.csv, events_optimized.csv")


if __name__ == "__main__":
    main()
