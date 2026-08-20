# Track A Submission, Manoj Kumar Sambana

## What is in this package

- `track_a_logs.csv`, the 455 event log corpus.
- `harness/`, the reproducible benchmark harness. Run `python3 main.py` against my published
  Lyzr agent to get the same numbers reported here. See `harness/README.md` for how.
- `docs/Track_A_Results_and_Optimization.pdf`, the results table, the optimization write-up,
  and the moving-target section, all in one document, with real numbers from a full 455 event
  run against the live Lyzr agent.
- `docs/Lyzr_TrackA_ScopingMemo.pdf`, the one page client scoping note, Part 1 of the
  assignment.
- `docs/lyzr_studio_build_guide.md`, the agent setup I used on Lyzr Agent Studio, role, goal,
  instructions, output format, and model.
- `docs/results_table.md`, `docs/optimization_writeup.md`, `docs/moving_target.md`, the plain
  markdown source for the sections in the combined PDF above.

## Submission checklist, from the assignment's own list

- [ ] Agent link, get the public link from Lyzr Studio's Deploy tab and include it here.
- [x] Results, `docs/Track_A_Results_and_Optimization.pdf`.
- [x] Scoping note, `docs/Lyzr_TrackA_ScopingMemo.pdf`, one page.
- [ ] Demo, record a short screen capture running `harness/main.py`, or plan to run it live.

## Checked against the assignment's "what will not pass the bar" list

| Thing that fails on its own | Did I do this |
|---|---|
| A single input demo, no full dataset run | No, the full 455 event file ran, twice, naive and optimized |
| Metrics with no runnable harness | No, `harness/main.py` is real code that calls the live agent |
| Every feature turned on with no reason given | No, see the Studio features section in the optimization write-up |
| An optimized build with no naive baseline | No, both ran on the full corpus, with real numbers for both |
| Real incidents buried in noise, or invented fixes | No, noise is filtered cleanly, and 0 fabricated remediations across all 455 events |
| A strong memo with no working agent, or an agent with no memo | No, both are here |

## Headline numbers, from the full 455 event run against the live agent

- Category accuracy, on the 40 labeled events: 1.000 (target 0.85 or higher)
- Root cause accuracy, on the 40 labeled events: 1.000 (target 0.80 or higher)
- Fabricated remediations, across all 455 events: 0 (target 0)
- Cost cut, optimized vs naive: 97.7 percent (target 50 percent or more)
- p95 latency, naive: 3.91 seconds, under target
- p95 latency, optimized: 4.29 seconds, 0.29 seconds over target, reported honestly, not
  rounded away

Full detail and honest notes on the accuracy scope, the token and cost math, and the latency
gap are in `docs/Track_A_Results_and_Optimization.pdf`.
