"""
Pluggable LLM backend for the benchmark harness.

MODES
-----
1. "anthropic"  -- real API call via api.anthropic.com (requires
                   ANTHROPIC_API_KEY in the environment). This is the mode
                   a reviewer runs to reproduce the results table.
2. "lyzr"       -- real call against a deployed Lyzr Agent Studio agent
                   endpoint (requires LYZR_API_KEY + LYZR_AGENT_ID). Use
                   this once the agent is built and published on Studio,
                   so the harness is driving the *actual* Studio agent
                   (per "driven over its API/SDK so the batch run is
                   reproducible").
3. "simulated"  -- deterministic offline stand-in used ONLY when neither
                   of the above credentials is present, so the harness can
                   be smoke-tested end-to-end without spending money or
                   requiring network access. Every simulated result is
                   tagged backend="simulated" in the output CSV, and the
                   results table prints a loud banner. This mode must NOT
                   be used for the numbers submitted to Lyzr -- swap in
                   real credentials before the graded run.

Pricing (USD / 1M tokens), Aug 2026 list prices -- edit if they change:
    claude-3-5-haiku   : $0.80 in / $4.00 out   (cheap-path / optimized build)
    claude-sonnet-4     : $3.00 in / $15.00 out  (naive baseline "biggest sensible model")
"""

import json
import os
import random
import time

PRICING = {
    "claude-3-5-haiku-latest": {"in": 0.80, "out": 4.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
}


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token for English)."""
    return max(1, round(len(text) / 4))


class LLMResult:
    def __init__(self, raw_json, input_tokens, output_tokens, latency_s, backend, model):
        self.raw_json = raw_json
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_s = latency_s
        self.backend = backend
        self.model = model


def resolve_backend():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("LYZR_API_KEY") and os.environ.get("LYZR_AGENT_ID"):
        return "lyzr"
    return "simulated"


class AnthropicBackend:
    def __init__(self, model):
        import anthropic  # imported lazily so simulated mode has no hard dep
        self.model = model
        self.client = anthropic.Anthropic()

    def call(self, system_prompt, user_prompt, max_tokens=200):
        t0 = time.perf_counter()
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency_s = time.perf_counter() - t0
        text = "".join(b.text for b in resp.content if b.type == "text")
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        return LLMResult(text, in_tok, out_tok, latency_s, "anthropic", self.model)


class LyzrStudioBackend:
    """Calls a published Lyzr Agent Studio agent via its inference endpoint."""

    def __init__(self, agent_id, api_key, user_id=None, base_url="https://agent-prod.studio.lyzr.ai"):
        import requests
        self.requests = requests
        self.agent_id = agent_id
        self.api_key = api_key
        self.user_id = user_id or os.environ.get("LYZR_USER_ID", "harness@local")
        self.base_url = base_url
        # Reuse one connection (keep-alive) across all calls instead of a
        # fresh TCP+TLS handshake per request -- this alone can shave real
        # time off each call when making hundreds of sequential requests.
        self._session = requests.Session()
        self._session.headers.update({"x-api-key": self.api_key, "Content-Type": "application/json"})

    def call(self, system_prompt, user_prompt, max_tokens=200, max_retries=4, base_delay=2.0):
        payload = {
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "session_id": f"{self.agent_id}-harness-{int(time.time()*1000)}",
            "message": user_prompt,
        }
        last_err = None
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            r = self._session.post(
                f"{self.base_url}/v3/inference/chat/",
                json=payload,
                timeout=30,
            )
            latency_s = time.perf_counter() - t0
            # 402/429 are the two status codes worth retrying: transient
            # rate-limit/credit-check hiccups, not a real request problem
            # (we already know the payload/schema are valid at this point).
            if r.status_code in (402, 429) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"    [retry] {r.status_code} on attempt {attempt+1}/{max_retries}, "
                      f"waiting {delay:.1f}s before retrying...")
                time.sleep(delay)
                last_err = r
                continue
            if r.status_code >= 400:
                raise RuntimeError(
                    f"Lyzr API {r.status_code} error after {attempt+1} attempt(s).\n"
                    f"Request payload: {payload}\n"
                    f"Response body: {r.text}"
                )
        data = r.json()
        text = data.get("response", "")
        # Lyzr's response payload doesn't always include token usage; fall
        # back to estimation when it's missing.
        in_tok = data.get("usage", {}).get("input_tokens") or estimate_tokens(system_prompt + user_prompt)
        out_tok = data.get("usage", {}).get("output_tokens") or estimate_tokens(text)
        return LLMResult(text, in_tok, out_tok, latency_s, "lyzr", self.agent_id)


class SimulatedBackend:
    """
    Offline stand-in so the harness runs end-to-end with no credentials.

    Simulates a classifier that is right most of the time and wrong some of
    the time (so the eval harness has something non-trivial to measure),
    plus realistic latency sampling, so the plumbing (metrics, tables,
    CSV export) can be validated before spending real API budget.

    NOT a substitute for the graded run -- clearly tagged in every output row.
    """

    def __init__(self, model, error_rate=0.05, seed=13):
        self.model = model
        self.error_rate = error_rate
        self.rng = random.Random(seed)

    def call(self, system_prompt, user_prompt, max_tokens=200, gt=None):
        # latency: lognormal-ish, cheap model faster than big model
        base = 0.35 if "haiku" in self.model else 0.9
        latency_s = max(0.08, self.rng.lognormvariate(0, 0.35)) * base

        in_tok = estimate_tokens(system_prompt + user_prompt)

        if gt and gt.get("is_incident") and gt.get("category"):
            if self.rng.random() < self.error_rate:
                # simulate an occasional wrong / low-confidence call
                payload = {
                    "is_incident": True,
                    "category": gt["category"],
                    "root_cause": self.rng.choice(
                        [gt["root_cause"], "consumer_lag", "missing_index"]
                    ),
                    "remediation": gt["remediation"],
                    "confidence": round(self.rng.uniform(0.35, 0.55), 2),
                }
            else:
                payload = {
                    "is_incident": True,
                    "category": gt["category"],
                    "root_cause": gt["root_cause"],
                    "remediation": gt["remediation"],
                    "confidence": round(self.rng.uniform(0.82, 0.98), 2),
                }
        else:
            payload = {
                "is_incident": False,
                "category": None,
                "root_cause": None,
                "remediation": None,
                "confidence": round(self.rng.uniform(0.9, 0.99), 2),
            }
        text = json.dumps(payload)
        out_tok = estimate_tokens(text)
        return LLMResult(text, in_tok, out_tok, latency_s, "simulated", self.model)


def get_backend(model, purpose="optimized"):
    """purpose: 'naive' -> biggest sensible model, 'optimized' -> cheap-path model"""
    mode = resolve_backend()
    if mode == "anthropic":
        return AnthropicBackend(model)
    if mode == "lyzr":
        return LyzrStudioBackend(
            os.environ["LYZR_AGENT_ID"], os.environ["LYZR_API_KEY"],
            user_id=os.environ.get("LYZR_USER_ID"),
        )
    return SimulatedBackend(model)


def cost_usd(model, input_tokens, output_tokens):
    p = PRICING.get(model, PRICING["claude-3-5-haiku-latest"])
    return (input_tokens / 1_000_000) * p["in"] + (output_tokens / 1_000_000) * p["out"]
