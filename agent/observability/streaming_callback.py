"""LangChain callback handler that captures tool calls for observability."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .gh_actions import gh_error

logger = logging.getLogger("streaming_callback")


class AgentStreamingCallback(BaseCallbackHandler):
    """Callback handler that emits GitHub Actions log groups per tool call
    and feeds progress updates to ProgressReporter.

    Usage:
        callback = AgentStreamingCallback(progress_reporter=reporter)
        agent.ainvoke(input, config={"callbacks": [callback]})
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
        tool_name = serialized.get("name", "unknown_tool")
        snippet = str(input_str)[:80].replace("\n", " ")
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
        out_str = str(output)
        if len(out_str) > 500:
            print(f"(output: {len(out_str)} chars)", flush=True)
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
        msg_count = sum(len(batch) for batch in messages)
        print(f"::group::LLM call — {model_name} ({msg_count} messages)", flush=True)
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
