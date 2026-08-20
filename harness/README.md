# Track A Benchmark Harness

Reproduces the required results table: naive baseline vs. optimized build, on the full 455-event
`track_a_logs.csv` corpus, scored against the 40 labeled ground-truth events.

## Run it

This assignment is built and graded on Lyzr Agent Studio. The command below runs the harness
against your published Lyzr agent, this is the real, graded path.

```bash
pip install -r requirements.txt

export LYZR_API_KEY=your-lyzr-api-key
export LYZR_AGENT_ID=your-agent-id
export LYZR_USER_ID=your-account-email
python3 main.py --data ../track_a_logs.csv
```

All three variables above are required for a real Lyzr run. If any are missing, the harness
falls back to one of two other modes, neither of which is the graded submission path:

```bash
# Optional, development/testing only: calls Anthropic's API directly, bypassing Lyzr
# entirely. Useful for testing the harness logic itself before the Lyzr agent is ready,
# but this does NOT exercise the Lyzr agent and is not what gets submitted.
export ANTHROPIC_API_KEY=sk-ant-...
python3 main.py --data ../track_a_logs.csv

# No credentials set at all -> offline simulation, for smoke-testing the harness code
# with no network calls and no cost. Also not a substitute for the real Lyzr run.
python3 main.py --data ../track_a_logs.csv
```

## What it does

1. Loads all 455 events.
2. **Naive baseline**: one LLM call per event, no dedup, no routing, biggest sensible model
   (`claude-sonnet-4-6` by default).
3. **Optimized build**: cheap-path rule-based noise filter (0 LLM calls for 6 known no-op
   templates) → dedup by exact message text (1 LLM call per unique remaining template, not per
   row) → confidence gating (escalate anything below 0.6 confidence or missing a valid
   remediation) → closed-set enum validation on every prediction.
4. Scores both runs against the 40 labeled rows: category macro-F1, root-cause accuracy,
   remediation accuracy, free-form-remediation count (must be 0), false-escalation rate.
5. Times and costs every actual LLM call (not per-event , a deduped cluster's cost is counted
   once, matching what you'd actually be billed).
6. Writes `results_table.md`, `results_table.json`, `events_naive.csv`, `events_optimized.csv`.

## Files

- `taxonomy.py`: the closed-set category/root-cause/remediation enums and the system prompt.
- `llm_backend.py`: pluggable backend: real Anthropic API, real Lyzr Studio agent, or a
  clearly-labeled offline simulation (auto-selected based on which env vars are set).
- `pipeline.py`: naive and optimized run logic.
- `metrics.py`: macro-F1, latency percentiles, cost, throughput.
- `data.py`: CSV loader.
- `main.py`: orchestrates both runs and prints/writes the table.

## Scaling note (50k events/day)

At 50k events/day with this corpus's ~3.5% unique-template rate (16/455), expect roughly
1,700-2,000 unique templates/day in the worst case if template diversity scales linearly with
volume , but in practice template diversity plateaus fast in real systems (the same ~20-50
services keep emitting the same error shapes), so LLM calls/day should stay in the low
thousands, not 50k. The architecture doesn't change: same dedup key, same confidence gate: it's
a rerun of this same pipeline, sharded by time window, with the cluster cache persisted across
runs so a message seen yesterday doesn't trigger a fresh LLM call today.
