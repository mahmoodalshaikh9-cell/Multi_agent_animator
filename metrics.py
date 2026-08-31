"""Lightweight per-attempt timing and LLM cost tracking (stdlib only).

A module-level singleton (METRICS) lets the harness set phases and every eval
module (vision.py, video_eval.py, local_agent.py, scene_meta.py) record a call
without threading a metrics object through every function signature.

Pricing is $ per 1M tokens, keyed by model id; unknown models fall back to the
"default" entry. Input tokens come from the API usage when present, otherwise
estimated as len(text) // 4 (provider responses here sometimes omit
prompt_tokens).
"""
import time

PRICES = {  # $ per 1M tokens
    "openai/gpt-5.6-luna":     {"input": 0.20, "output": 1.20},
    "google/gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "qwen/qwen3.8-flash":      {"input": 0.30, "output": 2.50},
    "default":                 {"input": 1.00, "output": 3.00},
}


def estimate_input_tokens(text: str) -> int:
    """Rough input-token estimate when the API does not report prompt_tokens."""
    return max(0, len(text or "") // 4)


class Metrics:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.totals = {
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        }
        self.phases = {}
        self.current_phase = None
        self.phase_start = None
        self.attempt_start = time.time()
        self.run_start = self.attempt_start
        self.attempt_phases = {}
        self.attempt_llm = {"calls": 0, "tokens": 0, "cost": 0.0}

    def phase(self, name):
        """Close the previous phase, then open a new one (None closes all)."""
        if not self.enabled:
            self.current_phase = None
            self.phase_start = None
            return
        if self.current_phase and self.phase_start:
            el = time.time() - self.phase_start
            self.phases[self.current_phase] = self.phases.get(self.current_phase, 0.0) + el
            self.attempt_phases[self.current_phase] = self.attempt_phases.get(
                self.current_phase, 0.0
            ) + el
        self.current_phase = name
        self.phase_start = time.time() if name else None

    def llm_cost(self, model: str, in_tok: int, out_tok: int) -> float:
        p = PRICES.get(model or "", PRICES["default"])
        return in_tok / 1e6 * p["input"] + out_tok / 1e6 * p["output"]

    def add_llm(self, model: str, prompt_tokens: int, completion_tokens: int,
                cost: float) -> None:
        if not self.enabled:
            return
        self.totals["llm_calls"] += 1
        self.totals["prompt_tokens"] += prompt_tokens
        self.totals["completion_tokens"] += completion_tokens
        self.totals["cost_usd"] += cost
        self.attempt_llm["calls"] += 1
        self.attempt_llm["tokens"] += prompt_tokens + completion_tokens
        self.attempt_llm["cost"] += cost


METRICS = Metrics()


def record_llm(model: str, prompt_text: str, usage: dict | None,
               cost: float | None = None) -> None:
    """Record one LLM call from a raw `usage` dict (or estimated tokens).

    Usage may be None or missing keys; input falls back to len//4 estimate.
    `cost` may be supplied directly (e.g. from a provider pricing) instead of
    recomputed from the pricing table.
    """
    usage = usage or {}
    pt = usage.get("prompt_tokens") or 0
    if not pt:
        pt = estimate_input_tokens(prompt_text)
    ct = usage.get("completion_tokens") or 0
    if cost is None:
        cost = METRICS.llm_cost(model, pt, ct)
    METRICS.add_llm(model, pt, ct, cost)


def start_attempt() -> None:
    """Reset per-attempt accumulators at the top of each attempt."""
    METRICS.attempt_start = time.time()
    METRICS.attempt_phases = {}
    METRICS.attempt_llm = {"calls": 0, "tokens": 0, "cost": 0.0}


def attempt_snapshot() -> dict:
    """Return the current attempt's rollup for summary.json."""
    return {
        "duration_s": round(time.time() - METRICS.attempt_start, 2),
        "llm_calls": METRICS.attempt_llm["calls"],
        "tokens": METRICS.attempt_llm["tokens"],
        "cost_usd": round(METRICS.attempt_llm["cost"], 6),
        "phases": {k: round(v, 2) for k, v in METRICS.attempt_phases.items()},
    }


def totals_summary() -> dict:
    """Return the whole-run rollup for summary.json."""
    return {
        "total_duration_s": round(time.time() - METRICS.run_start, 2),
        "total_llm_calls": METRICS.totals["llm_calls"],
        "total_tokens": (
            METRICS.totals["prompt_tokens"] + METRICS.totals["completion_tokens"]
        ),
        "total_prompt_tokens": METRICS.totals["prompt_tokens"],
        "total_completion_tokens": METRICS.totals["completion_tokens"],
        "total_cost_usd": round(METRICS.totals["cost_usd"], 6),
    }
