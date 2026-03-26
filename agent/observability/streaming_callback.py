"""LangChain callback handler for GH Actions log groups + token tracking."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import requests as _requests
from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler

from .gh_actions import _sanitize, gh_error

logger = logging.getLogger("streaming_callback")

# Live pricing from models.dev — fetched once, cached for the process lifetime
_MODELS_DEV_URL = "https://models.dev/api.json"
_pricing_cache: dict | None = None


def _get_pricing_data() -> dict:
    """Fetch and cache pricing data from models.dev."""
    global _pricing_cache
    if _pricing_cache is not None:
        return _pricing_cache
    try:
        resp = _requests.get(_MODELS_DEV_URL, timeout=5)
        if resp.ok:
            _pricing_cache = resp.json()
            logger.info("Loaded pricing data from models.dev (%d providers)", len(_pricing_cache))
        else:
            logger.warning("models.dev returned %s, using empty pricing", resp.status_code)
            _pricing_cache = {}
    except Exception:
        logger.warning("Failed to fetch models.dev pricing, cost tracking unavailable")
        _pricing_cache = {}
    return _pricing_cache


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate cost in USD using live pricing from models.dev."""
    # Parse provider:model format (e.g., "anthropic:claude-sonnet-4-6")
    if ":" in model_name:
        provider, model_id = model_name.split(":", 1)
    else:
        # Guess provider from model name
        model_id = model_name
        if model_name.startswith(("claude", "claude-")):
            provider = "anthropic"
        elif model_name.startswith(("gpt-", "o1", "o3", "o4")):
            provider = "openai"
        else:
            provider = ""

    data = _get_pricing_data()
    cost = data.get(provider, {}).get("models", {}).get(model_id, {}).get("cost")

    if not cost:
        logger.warning(
            "No pricing for '%s' (provider=%s, model=%s)", model_name, provider, model_id
        )
        return None

    input_price = cost.get("input", 0)
    output_price = cost.get("output", 0)
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


class AgentStreamingCallback(BaseCallbackHandler):
    """Emits GitHub Actions log groups per tool/LLM call and tracks tool counts.

    Token tracking is delegated to UsageMetadataCallbackHandler (langchain built-in).
    Use `create_callbacks()` to get both handlers wired together.
    """

    def __init__(self, progress_reporter=None):
        super().__init__()
        self.progress_reporter = progress_reporter
        self.tool_call_count = 0
        self._active_groups: dict[UUID, str] = {}

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

    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs: Any) -> None:
        out_str = _sanitize(str(output))
        if len(out_str) > 500:
            print(out_str[:500], flush=True)
            print(f"... ({len(out_str)} chars total)", flush=True)
        print("::endgroup::", flush=True)
        self._active_groups.pop(run_id, None)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
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
        msg_count = sum(len(batch) for batch in messages if isinstance(batch, list))
        print(
            f"::group::LLM call — {_sanitize(model_name)} ({msg_count} messages)",
            flush=True,
        )
        self._active_groups[run_id] = "llm"

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        gh_error(f"LLM call failed: {error}")
        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)


def create_callbacks(
    progress_reporter=None, model_id: str = ""
) -> tuple[list[BaseCallbackHandler], TokenStats]:
    """Create callback handlers and return (callbacks_list, token_stats).

    Uses langchain's built-in UsageMetadataCallbackHandler for token tracking
    and our AgentStreamingCallback for log groups + tool tracking.

    token_stats provides: input_tokens, output_tokens, total_tokens, llm_calls,
    tool_calls, estimated_cost.
    """
    usage_cb = UsageMetadataCallbackHandler()
    streaming_cb = AgentStreamingCallback(progress_reporter=progress_reporter)

    stats = TokenStats(usage_cb=usage_cb, streaming_cb=streaming_cb, model_id=model_id)
    return [usage_cb, streaming_cb], stats


class TokenStats:
    """Aggregates token usage from UsageMetadataCallbackHandler + tool counts."""

    def __init__(
        self,
        usage_cb: UsageMetadataCallbackHandler,
        streaming_cb: AgentStreamingCallback,
        model_id: str = "",
    ):
        self._usage_cb = usage_cb
        self._streaming_cb = streaming_cb
        self.model_id = model_id

    @property
    def input_tokens(self) -> int:
        return sum(v.get("input_tokens", 0) for v in self._usage_cb.usage_metadata.values())

    @property
    def output_tokens(self) -> int:
        return sum(v.get("output_tokens", 0) for v in self._usage_cb.usage_metadata.values())

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def llm_calls(self) -> int:
        return len(self._usage_cb.usage_metadata)

    @property
    def tool_calls(self) -> int:
        return self._streaming_cb.tool_call_count

    @property
    def estimated_cost(self) -> float | None:
        model = self.model_id
        if not model:
            # Use first model from usage_metadata keys
            keys = list(self._usage_cb.usage_metadata.keys())
            model = keys[0] if keys else ""
        return estimate_cost(model, self.input_tokens, self.output_tokens) if model else None

    @property
    def usage_by_model(self) -> dict:
        return dict(self._usage_cb.usage_metadata)
