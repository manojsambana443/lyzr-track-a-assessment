# Track A Results Table

I ran this against my live Lyzr agent (Track A Log Triage Agent), on the full 455 event file,
using gpt-5.4-mini for both runs below, so the only thing changing between them is the pipeline
design, not the model. Naive calls the agent once per event, 455 calls. Optimized filters 6
junk message patterns with local rules (200 of 455 rows, no model call needed), then groups the
remaining 255 rows into 10 real incident patterns and calls the agent once per pattern, 10
calls total covering all 455 events.

| Metric | Naive baseline | Optimized build | Delta |
|---|---|---|---|
| Category accuracy (F1), on the 40 labeled events | 1.000 | 1.000 | both perfect |
| Root cause accuracy, on the 40 labeled events | 1.000 | 1.000 | both perfect |
| Remediation accuracy, on the 40 labeled events | 1.000 | 1.000 | both perfect |
| Fabricated remediations, full 455 event corpus | 0 | 0 | target met |
| False escalations on known noise patterns | 0 | 0 | target met |
| p50 latency per real call | 2.94s | 3.16s | +7.5% |
| p95 latency per real call | 3.91s | 4.29s | +9.7%, see note |
| Tokens per original input event, amortized | 656.6 | 14.6 | 97.8% less |
| Cost per original input event, amortized | $0.000626 | $0.0000143 | 97.7% less |
| Cost for the full batch | $0.2847 | $0.0065 | 97.7% less |
| Real calls made, out of 455 events | 455 | 10 | 97.8% fewer calls |
| Throughput | 20.1 events/min | 191.8 events/min | |

**Accuracy is measured against the 40 events that have ground truth labels**, not all 455
individually checked. Across all 455 events, the pipeline still recorded 0 fabricated
remediations and 0 false escalations.

**The amortized token and cost numbers spread the optimized build's total across all 455
events**, since it makes only 10 real calls, not one per event. Each of those 10 real calls
uses about 665 tokens on its own, close to what the naive build's calls use per event, 656.6.
The saving comes from making 10 calls instead of 455, not from each call being cheaper.

**On the p95 gap:** the naive number comes from 455 real calls, the optimized number from only
10. With 10 samples, one slow call pulls p95 up a lot, so it is a noisier estimate. Naive
passed the 4 second target (3.91s). Optimized did not, by 0.29 seconds (4.29s). I am reporting
both plainly rather than rounding the miss away.

**Two checks stop invented fixes:** the agent is instructed to only pick from the approved
list, and the output format constrains what it can return. My own script then checks every
returned remediation against that list again before accepting it.

## Checking this against the targets in the assignment

| What they asked for | Target | Naive result | Optimized result | Did I hit it |
|---|---|---|---|---|
| Process the whole file in one run | 455 events, one run | 455 events done | 455 events done | Yes |
| Category accuracy, on the 40 labeled events | 0.85 or higher | 1.000 | 1.000 | Yes |
| Root cause accuracy, on the 40 labeled events | 0.80 or higher | 1.000 | 1.000 | Yes |
| No fabricated remediations, full corpus | 0 | 0 | 0 | Yes |
| p95 latency | 4 seconds or under | 3.91s, pass | 4.29s, not strictly met | Naive yes, optimized no |
| Cost cut vs naive | 50% or more | not applicable | 97.7% cut | Yes, well past the target |
