# Moving-Target Section

**Constraint chosen: "the cost budget is cut 40%."**

Current optimized cost is already $0.0065 for the full 455-event batch (about $0.0000143/event),
a 97.7% cut against the naive per-event baseline — so this budget is trivially met today. The
moving-target question that actually matters operationally is: what do we give up if we're
forced to cut cost again once volume scales toward the 50k-events/day target, where naive-style
per-event calling would otherwise dominate spend?

**What gets turned off first:** nothing in the dedup or noise-routing layer — those are already
free and are the reason cost is low. The lever we'd pull is the model tier for the escalation
path on genuinely novel message templates the system hasn't clustered yet. Since 10 templates
already cover 97.8% of call volume in this corpus, this mainly affects the long-tail case: a
brand-new log message the routing layer hasn't seen before. We would run a cheaper model as the
first pass on any new template, and only escalate to a stronger model when confidence comes back
below threshold — safe, because the confidence gate already exists and worked correctly (zero
false escalations across all 455 events in this run).

**What it costs in accuracy:** templates already known keep their current 1.000 accuracy (they're
matched against an established cluster, not re-reasoned from scratch on a cheaper model). The
cost is concentrated in the cold-start case: first-pass accuracy on a brand-new, never-seen
message on a cheaper model would be expected to soften slightly until either the confidence gate
correctly routes it to a human, or enough occurrences accumulate that it becomes its own cluster
and gets classified once, cheaply, like the rest.

**Alternative constraint (latency SLO tightens to 1.5s p95):** based on what we measured, this
would not be achievable without a fundamentally different inference path. Trace-level profiling
showed that platform-level overhead (session/routing setup, independent of model choice) accounts
for roughly half of the ~4s p95 latency we measured, and this floor held constant across two
different underlying models. Hitting 1.5s would require bypassing Lyzr's hosted platform layer in
favor of a direct, self-hosted or lower-latency inference path — a materially different
architecture, not a configuration change. We would flag this explicitly to the customer as a
platform-level constraint rather than attempt to tune around it, since our testing showed tuning
does not close a gap this large.
