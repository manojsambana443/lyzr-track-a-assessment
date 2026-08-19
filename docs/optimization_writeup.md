# Optimization Write-up — Track A (Auto-Remediation from Logs)

*All numbers below are from real runs against the live Lyzr Studio agent (Track A Log Triage
Agent), processing the full 455-event corpus. Reproducible via `harness/main.py` — see
`harness/README.md`.*

## Levers pulled, and their measured effect

**1. Cheap-path noise routing (rule-based, zero LLM cost).**
Six of the sixteen distinct message templates — health checks, favicon 404s, cache warmups,
scheduled-job pings, session-refresh notices, debug feature-flag logs — are structurally
unambiguous no-ops. These are filtered by exact/prefix match before any model call, covering
200 of 455 rows (44%). Effect: removes the 200 highest-volume, lowest-value rows from the cost
and latency budget entirely, at zero accuracy risk. Trade-off: any log format outside the known
16 templates falls through to the model rather than being pre-filtered — the safer failure
direction, but it means the rule set needs periodic review as services add new log lines.

**2. Deduplication / clustering (the single biggest cost lever).**
Of the remaining 255 "real incident" rows, only 10 distinct message templates exist. The agent
calls the model once per unique template and applies that result to every row sharing it.
Measured effect: LLM calls dropped from 455 (naive) to 10 (optimized) — a 97.8% call reduction.
Cost per full batch dropped from $0.2847 to $0.0065 — a 97.7% cut, well past the 50% target.
Trade-off: this assumes near-duplicate log lines share one root cause — true here by
construction, but a production version should fingerprint on (service, message-template,
time-window) rather than raw string equality, so two different incidents that happen to log
identical text weeks apart aren't silently merged.

**3. Confidence gating.**
Any classification below a 0.6 confidence threshold, or missing a valid remediation, is
escalated to a human instead of guessed. Across all 455 events, zero escalations were needed —
the agent was confident and correct on every classification, both at the individual-event level
(naive) and the cluster level (optimized). In a noisier real deployment this is the safety valve
that prevents a low-confidence guess from becoming an automatic action.

**4. Closed-set validation on the way out.**
Every predicted category, root cause, and remediation is checked against fixed enum lists
regardless of what the model returned. Free-form remediation count: 0/0 (naive/optimized) across
all 455 events — the target the spec requires.

## Platform-level findings (beyond the four required levers)

We profiled latency at the trace level (via Lyzr's Monitoring → Traces view) to understand what
was driving per-call response time, since this directly affects whether the design meets the
latency budget at scale. Early in testing, we compared two different underlying models
(claude-haiku-4-5 and gpt-4o-mini) under identical prompt and schema conditions, on small test
batches, and did not see a meaningful latency difference between them in our sample. This
suggested that platform-level processing (session routing, request handling) may account for a
significant share of end-to-end latency on this task, though our testing did not isolate platform
overhead as the only cause, and we would not generalize this beyond what we observed in our own
testing. The final agent used for the full 455-event submission runs (the numbers in
results_table.md) is configured with **gpt-5.4-mini**.

We also tried reusing a persistent network connection across calls instead of opening a new one
per request. In our test environment, this reduced observed client-side request duration by
roughly 1.5-2 seconds on the calls we tested. This is a result from our own benchmark runs, not a
guaranteed improvement on every network or account. After this change, combined p95 latency across
our full 455-event runs came to 3.9s (naive) and 4.3s (optimized) — see results_table.md for the
full breakdown and an honest note on why we do not claim the optimized number definitely meets the
4s target. We separately tested removing JSON schema enforcement and did not see a meaningful
latency change in that test either, so we kept the schema on, since it costs nothing measurable in
speed in our tests and buys the closed-set compliance guarantee (0 free-form remediations,
confirmed across all 455 events).

## What moved which axis

| Lever | Accuracy | Latency | Cost | Notes |
|---|---|---|---|---|
| Cheap-path noise routing | no change | reduces load | reduces load | zero-cost, zero-risk on known templates |
| Dedup/clustering | no change (both 1.000) | reduces total load | 97.7% cut, biggest lever | assumes same-text = same-cause |
| Confidence gating | protects accuracy floor | none triggered in this run | none triggered | safety valve, unused this run because accuracy was already perfect |
| Closed-set validation | protects accuracy floor | negligible | negligible | prevented 0 violations across 455 events |
| Connection reuse (client-side fix) | no change | reduced observed request time in our tests | none | found via trace profiling, tested on small batches, not a Studio feature |

## Studio features enabled/disabled, and why

- **Output schema / guardrails: ON.** Enforces the closed remediation set at the platform level.
  Confirmed via testing that this adds no measurable latency cost, so there was no reason to
  leave it off.
- **Knowledge Base: OFF.** No retrieval needed — classification signal is fully contained in the
  log line itself.
- **Memory: OFF.** Each event is classified independently; no cross-turn state to preserve.
- **Reflection: OFF.** Not needed given 1.000 accuracy on both runs; would only add latency for
  no measured accuracy gain on this task.
- **Orchestration: none.** Single classification agent, not a multi-step workflow.
