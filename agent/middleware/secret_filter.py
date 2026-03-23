"""After-agent middleware that redacts secrets from agent output.

Scans the agent's final response for patterns matching API keys, tokens,
passwords, and other credentials. Replaces them with [REDACTED] before
the output reaches GitHub comments or PR reviews.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain.agents.middleware import AgentState, after_agent
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Patterns that match common secret formats
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("OpenAI API Key", re.compile(r"sk-[a-zA-Z0-9\-]{20,}")),
    ("GitHub Token", re.compile(r"ghp_[a-zA-Z0-9]{36}")),
    ("GitHub App Token", re.compile(r"ghs_[a-zA-Z0-9]{36}")),
    ("Anthropic Key", re.compile(r"sk-ant-[a-zA-Z0-9\-]{32,}")),
    (
        "Generic API Key",
        re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    ),
    ("Bearer Token", re.compile(r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*")),
    ("Connection String", re.compile(r"(?i)(mongodb|postgres|mysql|redis)://[^\s]+")),
    ("Private Key Header", re.compile(r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----")),
]


def redact_secrets(text: str) -> tuple[str, int]:
    """Scan text for secret patterns and replace with [REDACTED].

    Returns (redacted_text, count_of_redactions).
    """
    count = 0
    result = text
    for name, pattern in SECRET_PATTERNS:
        matches = pattern.findall(result)
        if matches:
            count += len(matches)
            result = pattern.sub(f"[REDACTED_{name.upper().replace(' ', '_')}]", result)
            logger.warning("Redacted %d instance(s) of %s from agent output", len(matches), name)
    return result, count


@after_agent
def secret_filter(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Scan agent output for secrets and redact them."""
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

        redacted, count = redact_secrets(content)
        if count > 0:
            new_messages[i] = AIMessage(content=redacted, id=msg.id)
            modified = True
            logger.info("Redacted %d secret(s) from AI message", count)

    if modified:
        return {"messages": new_messages}

    return None
