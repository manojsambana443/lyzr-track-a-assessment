# Track A Submission — Manoj Kumar Sambana

## What's in this package

- `track_a_logs.csv` — the 455-event log corpus.
- `harness/` — the reproducible benchmark harness. Run `python3 main.py` (see `harness/README.md`)
  against your published Lyzr agent to regenerate every number in this submission live.
- `docs/results_table.md` — the required naive-vs-optimized results table, filled in with real
  numbers from a full 455-event run against the live Lyzr agent.
- `docs/optimization_writeup.md` — Part 2 deliverable #3: every lever pulled, and its measured
  effect, plus the Studio features enabled/disabled and why.
- `docs/moving_target.md` — Part 2 deliverable #4.
- `docs/Lyzr_TrackA_ScopingMemo.docx` — Part 1, the one-page client scoping note.
- `docs/lyzr_studio_build_guide.md` — the agent configuration (role, goal, instructions, schema,
  model) as built on Lyzr Agent Studio.

## Submission checklist (per the assignment's "Submission" section)

- [ ] **Agent Link** — grab the public link to the published agent from Lyzr Studio's Deploy tab
      and include it here.
- [x] **Results** — `docs/results_table.md` + `docs/optimization_writeup.md`.
- [x] **Scoping note** — `docs/Lyzr_TrackA_ScopingMemo.docx` (verified one page).
- [ ] **Demo** — record a <5 minute screen capture running `harness/main.py` and showing the
      results table regenerate, or plan to do this live in the interview.

## Checked against "what will not pass the bar"

| Failure mode listed in the assignment | Status |
|---|---|
| Single-input demo, no full-dataset run | Not applicable — full 455-event corpus processed, twice (naive + optimized) |
| Metrics with no runnable harness | Not applicable — `harness/main.py` is real, working code that calls the live agent |
| Every feature turned on with no justification | Not applicable — see the "Studio features enabled/disabled" section in the optimization write-up |
| Optimized build with no naive baseline | Not applicable — both run on the full corpus, real numbers for both |
| Real incidents buried in un-deduped noise, or invented remediations | Not applicable — noise filtered cleanly, 0 free-form remediations across 455 events |
| Strong memo with no working agent, or agent with no memo | Not applicable — both present |

## Headline numbers (full 455-event corpus, live agent)

- Category macro-F1: **1.000** (target ≥0.85)
- Root-cause accuracy: **1.000** (target ≥0.80)
- Free-form remediations: **0** (target 0)
- Cost reduction, optimized vs naive: **97.7%** (target ≥50%)
- p95 latency: **3.9-4.3s** (target ≤4s — see note in results_table.md on why we report a range)
