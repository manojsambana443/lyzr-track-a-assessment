# Optimization Write-up, Track A (Auto-Remediation from Logs)

All numbers here come from real runs against my live Lyzr agent, on the full 455 event file.
Full numbers and target checks are in the results table. This document covers what I did and
why. The harness that produced these numbers is included, see harness/README.md to run it.

## The levers I pulled

**1. Filter obvious junk with plain rules, before calling the model.** Six of sixteen message
patterns are clearly not real problems (health checks, favicon requests, cache warmups,
scheduled job pings, session refresh, debug flags). A simple text match catches these before
the model sees them, covering 200 of 455 rows, 44 percent of the file, at zero accuracy risk.
Anything that does not match a known junk pattern still goes to the model, which is the safer
way to fail. I would need to review these rules occasionally as services add new log formats.

**2. Group duplicate messages, ask the model once per group.** Out of the remaining 255 rows,
there are only 10 distinct message patterns. Asking once per pattern instead of once per row
cut real calls from 455 to 10, a 97.8 percent drop, and cost from $0.2847 to $0.0065 for the
full batch, a 97.7 percent cut, well past the 50 percent target. Each individual call uses
about the same tokens either way (roughly 665 optimized vs 656.6 naive), so the saving is
entirely from fewer calls, not cheaper ones. This assumes identical text means the same
problem, true here by design, but a real system should also check service and rough time
window so two unrelated incidents with the same wording weeks apart do not get merged.

**3. Send unsure cases to a human instead of guessing.** Anything below a confidence threshold,
or missing a valid remediation, gets flagged for a person. Nothing needed flagging in this run,
the agent was confident and correct on every check against a known answer. This is the safety
net for a messier real deployment.

**4. Check every fix against the approved list, twice.** Once when the agent generates it,
constrained by the output format, and once in my own script before accepting it. Zero
violations across all 455 events.

## Latency investigation

Grouping cut the number of calls a lot, but not the wait time per call, since each call still
depends on the same external agent. What I tried, in order:

- **Looked at where the time actually went**, using Lyzr's Monitoring and Traces view. A real
  chunk of the total time happens before the model call even starts.
- **Tested two models** (claude-haiku-4-5, gpt-4o-mini) on small batches. Speed barely changed
  between them, which pointed away from model choice as the cause.
- **Turned the strict output format off for a test.** Speed barely changed, so I kept it on,
  since it costs nothing measurable and backs the no-invented-fixes guarantee.
- **Told the agent to skip explanations and only return the required fields**, to keep the
  response itself short.
- **Found and fixed a real issue on my side**: my script opened a new network connection per
  call instead of reusing one. Reusing it cut real time off each call, this was the one change
  that actually moved the number.
- **Reran small batches after each change** to confirm nothing broke accuracy or the approved
  fix list along the way.

Final numbers: 3.91s p95 on the naive run, under target, and 4.29s p95 on the optimized run,
0.29 seconds over target. I stopped testing once model choice and output format had both come
back showing no real effect, and the one change that helped was already applied. I am reporting
both real numbers rather than re-running until a better one came out.

Separately, I also rewrote how the classification instructions describe categories, moving from
plain lists to an explicit root-cause-to-category table. That fix was for accuracy, not speed,
it corrected the agent picking a category that sounded reasonable but did not match the
assignment's own labels. Noting it here so it is not confused with the latency work above.

## What each thing changed

| What I did | Accuracy | Speed | Cost |
|---|---|---|---|
| Filter junk with rules | no change | less work overall | less work overall |
| Group duplicates, ask once | no change, both 1.000 on labeled set | fewer calls needed | 97.7% less, the big one |
| Send unsure cases to a human | keeps accuracy safe | not triggered this run | not triggered this run |
| Check every fix against the list, twice | keeps accuracy safe | barely any cost | barely any cost |
| Reuse one connection | no change | cut real time in tests | none |

## Studio features, on and off

- **Strict output format: on.** Forces fixes from the approved list. No measurable speed cost.
- **Knowledge Base: off.** Nothing needs looking up, the log line has everything needed.
- **Memory: off.** Each log line stands alone.
- **Reflection: off.** Accuracy was already perfect on the labeled set for both runs, no gain.
- **No multi-agent setup.** One agent, one job. More steps would just add delay.
