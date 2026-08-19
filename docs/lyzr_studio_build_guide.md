# Building this on Lyzr Agent Studio — setup guide

I don't have direct access to Lyzr Agent Studio from this environment, so this is the exact
configuration to replicate there. The harness (`harness/main.py`) is written to call a published
Studio agent directly once it exists (`LYZR_API_KEY` + `LYZR_AGENT_ID` env vars — see
`llm_backend.LyzrStudioBackend`), so the same script that validates the design here becomes your
real, reproducible submission harness with no code changes.

## Agent structure (single agent, three responsibilities)

1. **System prompt** — use `harness/taxonomy.py::CLOSED_SET_PROMPT` verbatim as the agent's
   instructions. It defines the category / root-cause / remediation enums and forces strict JSON
   output, which is what makes the closed-set validation on the way out possible.
2. **Model** — we tested a few small/cheap models during development (claude-haiku-4-5,
   gpt-4o-mini) to check that latency did not depend heavily on model choice. The model actually
   configured on the published agent, and used for the final submission numbers, is
   **gpt-5.4-mini**. Track A's messages are short and structurally simple, so a small/cheap tier
   is enough to clear the 0.85 macro-F1 target, which our real runs confirmed (1.000 F1 on both
   the naive and optimized runs).
3. **Studio features — what to turn on and why:**
   - **Guardrails / output schema validation**: on. This is what enforces the closed remediation
     set at the platform level (belt-and-suspenders with the harness-side validation).
   - **Knowledge Base**: off. Track A doesn't need retrieval — the classification signal is fully
     contained in the log line itself. Turning this on would add latency and cost for no accuracy
     gain here (unlike Track B, where grounding against a KB is the whole point).
   - **Memory**: off. Each event is classified independently; there's no cross-turn conversation
     state to preserve, and memory would add token overhead per call for nothing.
   - **Reflection**: off by default, but worth testing as an optional second pass gated on low
     confidence only (see moving_target.md) rather than on every call.
   - **Orchestration**: not needed — this is a single classification agent, not a multi-agent
     workflow. Keeping it single-agent avoids the extra hop latency a router/sub-agent pattern
     would add.

## Driving it via API for reproducibility

Publish the agent, then set:
```
export LYZR_API_KEY=<your studio api key>
export LYZR_AGENT_ID=<published agent id>
python3 harness/main.py --data track_a_logs.csv
```
This drives the actual Studio agent for every LLM call the harness makes (10 calls in the
optimized run, 455 in the naive baseline), so the numbers a reviewer sees are the numbers the
live agent actually produced — not a description of what it should do.
