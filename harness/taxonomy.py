"""
Closed-set contract for Track A (Auto-Remediation from Logs).

The model is NEVER allowed to invent a category / root cause / remediation.
It must pick from these fixed lists, or the pipeline routes the event to
human review. This is what "remediations must come from the approved set
(0 free-form)" means in practice: enum validation on the way out, not model
good behavior.
"""

CATEGORIES = [
    "resource_exhaustion",
    "capacity",
    "dependency_failure",
    "code_defect",
    "performance",
    "config_error",
]

ROOT_CAUSES = [
    "memory_leak",
    "rate_limit_breach",
    "db_connection_pool_exhausted",
    "db_deadlock",
    "upstream_outage",
    "null_pointer",
    "disk_full",
    "missing_index",
    "consumer_lag",
    "expired_cert",
]

# Fixed, approved remediation catalog. The agent selects ONE of these,
# never free text. Index kept 1:1 with the source ground truth so the
# eval harness can score exact-match.
REMEDIATIONS = [
    "add_backpressure_and_request_quota_increase",
    "increase_pool_size_and_add_timeout_retry",
    "scale_consumers_and_check_poison_message",
    "enable_fallback_queue_and_alert_vendor",
    "reorder_locks_and_add_retry_with_backoff",
    "ship_hotfix_null_guard",
    "rotate_logs_and_expand_volume",
    "add_index_and_review_query_plan",
    "rotate_certificate_and_add_expiry_alert",
    "restart_pod_and_raise_heap_limit",
]

# Sentinel outcomes that are NOT part of the closed remediation set but are
# valid pipeline states.
NOISE = "NOISE_NO_ACTION"
ESCALATE = "ESCALATE_TO_HUMAN"

# Deterministic (zero-LLM-cost) noise signatures. These are structurally
# unambiguous (health checks, static-asset 404s, debug/info telemetry)
# and are the single biggest source of the ~200 noise rows in the corpus.
# This is the "cheap-path routing for obvious noise" lever, applied BEFORE
# any model call.
NOISE_PATTERNS = [
    "GET /health 200 2ms",
    "GET /favicon.ico 404 1ms",
    "INFO scheduled job nightly-report started",
    "INFO cache warmup complete in 120ms",
    "INFO user session refreshed",
    "DEBUG feature-flag evaluated: new_checkout=false",
]

CLOSED_SET_PROMPT = f"""You are an incident-triage classifier for a platform reliability team.
You will be given ONE log/alert event (service, severity, message).

Decide if this is a REAL actionable incident or noise. If it is a real incident, classify it
using ONLY the enums below. Never invent a category, root cause, or remediation that is not
in these lists. If you are not confident (message is ambiguous, or doesn't clearly map to one
of these root causes), set confidence low and pick your best guess anyway. The pipeline will
route low-confidence answers to a human, so it is safe to be honest about uncertainty.

IMPORTANT: category is fully determined by root_cause. Use this exact mapping as ground truth,
not your own judgment about what these words mean:

  root_cause                     -> category
  memory_leak                    -> resource_exhaustion
  disk_full                      -> resource_exhaustion
  rate_limit_breach              -> capacity
  consumer_lag                   -> capacity
  db_connection_pool_exhausted   -> dependency_failure
  upstream_outage                -> dependency_failure
  db_deadlock                    -> code_defect
  null_pointer                   -> code_defect
  missing_index                  -> performance
  expired_cert                   -> config_error

First identify the root_cause from the log message, then look up its category in the table
above. Do not classify category independently of root_cause.

CATEGORY enum: {CATEGORIES}
ROOT_CAUSE enum: {ROOT_CAUSES}
REMEDIATION enum: {REMEDIATIONS}

Respond with ONLY a compact JSON object, no prose, no markdown fences:
{{"is_incident": true|false, "category": "<enum or null>", "root_cause": "<enum or null>",
"remediation": "<enum or null>", "confidence": <0.0-1.0>}}
"""
