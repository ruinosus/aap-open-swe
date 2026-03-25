"""LangChain callback handler that captures tool calls and token usage."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .gh_actions import _sanitize, gh_error

logger = logging.getLogger("streaming_callback")

# Pricing per 1M tokens (USD) — source: models.dev
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-11-20": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
}


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate cost in USD based on model pricing. Returns None if unknown."""
    # Strip provider prefix (e.g., "anthropic:claude-sonnet-4-6" -> "claude-sonnet-4-6")
    clean_name = model_name.split(":")[-1] if ":" in model_name else model_name

    # Try exact match
    pricing = MODEL_PRICING.get(clean_name)
    if not pricing:
        # Try substring match
        for key, val in MODEL_PRICING.items():
            if key in clean_name or clean_name in key:
                pricing = val
                break
    if not pricing:
        return None
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


class AgentStreamingCallback(BaseCallbackHandler):
    """Callback handler that emits GitHub Actions log groups per tool call,
    tracks token usage, and feeds progress updates to ProgressReporter.

    Usage:
        callback = AgentStreamingCallback(progress_reporter=reporter)
        agent.ainvoke(input, config={"callbacks": [callback]})
    """

    def __init__(self, progress_reporter=None):
        super().__init__()
        self.progress_reporter = progress_reporter
        self.tool_call_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.llm_calls = 0
        self._model_name = ""
        self._active_groups: dict[UUID, str] = {}

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def estimated_cost(self) -> float | None:
        return estimate_cost(self._model_name, self.total_input_tokens, self.total_output_tokens)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = _sanitize(serialized.get("name", "unknown_tool"))
        snippet = _sanitize(str(input_str)[:80])
        print(f"::group::Tool: {tool_name} — {snippet}", flush=True)
        self._active_groups[run_id] = tool_name
        self.tool_call_count += 1

        if self.progress_reporter:
            self.progress_reporter.log_tool_call(tool_name, snippet)

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        out_str = _sanitize(str(output))
        if len(out_str) > 500:
            print(out_str[:500], flush=True)
            print(f"... ({len(out_str)} chars total)", flush=True)
        print("::endgroup::", flush=True)
        self._active_groups.pop(run_id, None)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = self._active_groups.pop(run_id, "unknown")
        gh_error(f"Tool {tool_name} failed: {error}")
        print("::endgroup::", flush=True)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model_id = serialized.get("id", ["unknown"])
        model_name = model_id[-1] if isinstance(model_id, list) else str(model_id)
        if not self._model_name:
            self._model_name = model_name
        msg_count = sum(len(batch) for batch in messages if isinstance(batch, list))
        print(
            f"::group::LLM call — {_sanitize(model_name)} ({msg_count} messages)",
            flush=True,
        )
        self._active_groups[run_id] = "llm"

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self.llm_calls += 1
        self._extract_token_usage(response)

        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        gh_error(f"LLM call failed: {error}")
        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)

    def _extract_token_usage(self, response: Any) -> None:
        """Extract token usage from LLMResult — supports OpenAI and Anthropic."""
        # Strategy 1: llm_output.token_usage (OpenAI pattern)
        llm_output = getattr(response, "llm_output", None) or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if usage:
            self.total_input_tokens += usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            self.total_output_tokens += usage.get("completion_tokens", 0) or usage.get(
                "output_tokens", 0
            )
            return

        # Strategy 2: message.usage_metadata (Anthropic / langchain-anthropic)
        generations = getattr(response, "generations", [])
        if generations and generations[0]:
            msg = getattr(generations[0][0], "message", None)
            if msg:
                usage_meta = getattr(msg, "usage_metadata", None)
                if usage_meta and isinstance(usage_meta, dict):
                    self.total_input_tokens += usage_meta.get("input_tokens", 0)
                    self.total_output_tokens += usage_meta.get("output_tokens", 0)
                    return
                # Also check response_metadata.usage
                resp_meta = getattr(msg, "response_metadata", None) or {}
                resp_usage = resp_meta.get("usage", {})
                if resp_usage:
                    self.total_input_tokens += resp_usage.get("input_tokens", 0)
                    self.total_output_tokens += resp_usage.get("output_tokens", 0)
                    return

            # Strategy 3: generation_info (fallback)
            gen_info = getattr(generations[0][0], "generation_info", {}) or {}
            gen_usage = gen_info.get("usage", {})
            if gen_usage:
                self.total_input_tokens += gen_usage.get("prompt_tokens", 0) or gen_usage.get(
                    "input_tokens", 0
                )
                self.total_output_tokens += gen_usage.get("completion_tokens", 0) or gen_usage.get(
                    "output_tokens", 0
                )
