"""Manifest-driven guardrails that apply input/output regex rules from manifest.yaml.

The manifest defines guardrails as regex patterns with actions (block/warn).
This middleware reads those patterns via aap_config and applies them:

- Input guardrails (@before_model): scan user messages and tool inputs for
  destructive commands, unsafe execution patterns, etc.
- Output guardrails (@after_agent): scan agent output for leaked credentials,
  secrets, and cloud provider keys.

This replaces hardcoded patterns — all regex rules are declared in the manifest,
making them configurable without code changes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain.agents.middleware import AgentState, after_agent, before_model
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


def _compile_guardrails(guardrails: list) -> list[tuple[re.Pattern, str, str]]:
    """Compile manifest guardrail entries into (pattern, action, message) tuples."""
    compiled = []
    for g in guardrails:
        if not isinstance(g, dict):
            # ManifestGuardrail object — access attributes
            pattern_str = (
                getattr(g, "pattern", None) or g.get("pattern", "")
                if isinstance(g, dict)
                else getattr(g, "pattern", "")
            )
            action = (
                getattr(g, "action", "block")
                if not isinstance(g, dict)
                else g.get("action", "block")
            )
            message = (
                getattr(g, "message", "Guardrail triggered")
                if not isinstance(g, dict)
                else g.get("message", "Guardrail triggered")
            )
        else:
            pattern_str = g.get("pattern", "")
            action = g.get("action", "block")
            message = g.get("message", "Guardrail triggered")

        if pattern_str:
            try:
                compiled.append((re.compile(pattern_str, re.IGNORECASE), action, message))
            except re.error:
                logger.warning("Invalid guardrail regex: %s", pattern_str)
    return compiled


def _scan_text(text: str, patterns: list[tuple[re.Pattern, str, str]]) -> tuple[bool, str]:
    """Scan text against compiled guardrail patterns.

    Returns (blocked, message) — blocked=True if action is 'block' and matched.
    """
    for pattern, action, message in patterns:
        if pattern.search(text):
            logger.warning("Manifest guardrail triggered: %s (action=%s)", message, action)
            if action == "block":
                return True, message
    return False, ""


def create_manifest_input_guardrail():
    """Create a @before_model middleware that applies manifest input guardrails.

    Scans user messages and tool call arguments for patterns that should be
    blocked (destructive commands, unsafe execution, etc.).

    Returns None if no input guardrails are defined in the manifest.
    """
    from agent.aap_config import get_input_guardrails

    raw_guardrails = get_input_guardrails()
    if not raw_guardrails:
        return None

    compiled = _compile_guardrails(raw_guardrails)
    if not compiled:
        return None

    logger.info("Loaded %d input guardrail patterns from manifest", len(compiled))

    @before_model
    def manifest_input_guardrail(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Scan user messages and tool inputs for blocked patterns."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]

        # Scan human messages
        if isinstance(last_msg, HumanMessage) and isinstance(last_msg.content, str):
            blocked, msg = _scan_text(last_msg.content, compiled)
            if blocked:
                return {
                    "messages": [
                        *messages,
                        AIMessage(content=f"BLOCKED by input guardrail: {msg}"),
                    ]
                }

        # Scan tool call arguments (e.g., execute commands)
        tool_calls = getattr(last_msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                args = tc.get("args", {})
                # Check command arguments (execute tool)
                for key in ("command", "cmd", "input"):
                    val = args.get(key, "")
                    if val and isinstance(val, str):
                        blocked, msg = _scan_text(val, compiled)
                        if blocked:
                            return {
                                "messages": [
                                    *messages,
                                    ToolMessage(
                                        content=f"BLOCKED by input guardrail: {msg}",
                                        tool_call_id=tc.get("id", ""),
                                    ),
                                ]
                            }

        return None

    return manifest_input_guardrail


def create_manifest_output_guardrail():
    """Create an @after_agent middleware that applies manifest output guardrails.

    Scans AI messages for patterns that should be blocked (leaked credentials,
    cloud provider keys, etc.) and redacts them.

    Returns None if no output guardrails are defined in the manifest.
    """
    from agent.aap_config import get_output_guardrails

    raw_guardrails = get_output_guardrails()
    if not raw_guardrails:
        return None

    compiled = _compile_guardrails(raw_guardrails)
    if not compiled:
        return None

    logger.info("Loaded %d output guardrail patterns from manifest", len(compiled))

    @after_agent
    def manifest_output_guardrail(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Scan agent output for blocked patterns and redact matches."""
        messages = state.get("messages", [])
        if not messages:
            return None

        modified = False
        new_messages = list(messages)

        for i, msg in enumerate(new_messages):
            if not isinstance(msg, AIMessage):
                continue
            content = msg.content
            if not content or not isinstance(content, str):
                continue

            # Replace all matched patterns with [REDACTED]
            new_content = content
            for pattern, action, guardrail_msg in compiled:
                matches = pattern.findall(new_content)
                if matches:
                    logger.warning(
                        "Output guardrail match: %s (%d occurrences)",
                        guardrail_msg,
                        len(matches),
                    )
                    if action == "block":
                        new_content = pattern.sub("[REDACTED]", new_content)

            if new_content != content:
                new_messages[i] = AIMessage(content=new_content, id=msg.id)
                modified = True

        if modified:
            return {"messages": new_messages}

        return None

    return manifest_output_guardrail
