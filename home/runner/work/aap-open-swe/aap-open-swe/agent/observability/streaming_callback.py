"""LangChain callback handler that captures tool calls for observability."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .gh_actions import _sanitize, gh_error

logger = logging.getLogger("streaming_callback")


class AgentStreamingCallback(BaseCallbackHandler):
    """Callback handler that emits GitHub Actions log groups per tool call
    and feeds progress updates to ProgressReporter.

    Each tool invocation is wrapped in a ``::group::`` / ``::endgroup::`` pair
    so GitHub Actions collapses the output by default.  LLM calls are similarly
    grouped.  If a ``ProgressReporter`` is provided, tool-call metrics are
    forwarded to it so the live issue comment stays up to date.

    Usage:
        callback = AgentStreamingCallback(progress_reporter=reporter)
        agent.ainvoke(input, config={"callbacks": [callback]})
    """

    def __init__(self, progress_reporter=None):
        """Initialize the callback handler.

        Args:
            progress_reporter: Optional ``ProgressReporter`` instance.  When
                provided, every tool call is forwarded via
                ``progress_reporter.log_tool_call()``.
        """
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
        """Open a GitHub Actions log group when a tool starts.

        Args:
            serialized: LangChain serialized tool dict (must contain ``"name"``).
            input_str: Raw input string passed to the tool.
            run_id: Unique identifier for this tool invocation.
            **kwargs: Additional keyword arguments (ignored).
        """
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
        """Close the GitHub Actions log group when a tool finishes.

        Prints a truncated preview of the output (up to 500 chars) before
        closing the group so the log remains readable without being flooded.

        Args:
            output: The tool's return value as a string.
            run_id: Unique identifier matching the corresponding ``on_tool_start``.
            **kwargs: Additional keyword arguments (ignored).
        """
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
        """Emit a GitHub Actions error annotation and close the log group.

        Args:
            error: The exception raised by the tool.
            run_id: Unique identifier matching the corresponding ``on_tool_start``.
            **kwargs: Additional keyword arguments (ignored).
        """
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
        """Open a GitHub Actions log group when an LLM call begins.

        Args:
            serialized: LangChain serialized model dict (must contain ``"id"``).
            messages: Batched message lists passed to the model.
            run_id: Unique identifier for this LLM invocation.
            **kwargs: Additional keyword arguments (ignored).
        """
        model_id = serialized.get("id", ["unknown"])
        model_name = model_id[-1] if isinstance(model_id, list) else str(model_id)
        msg_count = sum(len(batch) for batch in messages if isinstance(batch, list))
        print(
            f"::group::LLM call — {_sanitize(model_name)} ({msg_count} messages)",
            flush=True,
        )
        self._active_groups[run_id] = "llm"

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """Close the GitHub Actions log group when an LLM call completes.

        Args:
            response: The LLM response object (not inspected).
            run_id: Unique identifier matching the corresponding ``on_chat_model_start``.
            **kwargs: Additional keyword arguments (ignored).
        """
        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        """Emit a GitHub Actions error annotation when an LLM call fails.

        Args:
            error: The exception raised during the LLM call.
            run_id: Unique identifier matching the corresponding ``on_chat_model_start``.
            **kwargs: Additional keyword arguments (ignored).
        """
        gh_error(f"LLM call failed: {error}")
        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)
