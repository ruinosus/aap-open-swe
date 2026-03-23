"""Before-model middleware that enforces file scope restrictions per skill.

Intercepts tool calls (write_file, edit_file) and blocks writes to files
outside the allowed scope for each skill. This prevents skills from
modifying files they shouldn't touch (e.g., project-docs modifying .github/).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain.agents.middleware import AgentState, before_model
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Skill ID → list of allowed path patterns (regex)
# If a skill is not listed, all paths are allowed (no restriction)
SKILL_SCOPE: dict[str, dict] = {
    "code-review": {
        "allow_writes": False,  # Review skills should not write any files
    },
    "security-scan": {
        "allow_writes": False,
    },
    "project-docs": {
        "allow_writes": True,
        "allowed_patterns": [
            r"^README\.md$",
            r"^[A-Z]+\.md$",  # Root-level .md files (CUSTOMIZATION.md, etc.)
            r"^docs/.*\.md$",  # docs/ directory .md files
        ],
        "blocked_patterns": [
            r"^\.github/",  # Never touch workflow files
            r"^\.aap/",  # Never touch manifest/skills
            r".*\.py$",  # Never touch Python code
            r".*\.ya?ml$",  # Never touch YAML config
        ],
    },
    "doc-generator": {
        "allow_writes": True,
        "allowed_patterns": [
            r".*\.py$",  # Can modify Python files (docstrings)
            r"^docs/.*\.md$",  # Can create docs
            r"^README\.md$",
        ],
        "blocked_patterns": [
            r"^\.github/",
            r"^\.aap/",
            r"^tests/",  # Don't modify tests
        ],
    },
    "test-generator": {
        "allow_writes": True,
        "allowed_patterns": [
            r"^tests/.*\.py$",  # Can create/modify test files
            r"^test_.*\.py$",  # Root-level test files
        ],
        "blocked_patterns": [
            r"^\.github/",
            r"^\.aap/",
            r"^agent/",  # Don't modify source code
        ],
    },
}

# Tool names that write files
WRITE_TOOLS = {"write_file", "edit_file"}


def _extract_file_path(tool_call: dict) -> str | None:
    """Extract file path from a tool call's arguments."""
    args = tool_call.get("args", {})
    return args.get("file_path") or args.get("path") or args.get("filename")


def _is_path_allowed(path: str, scope: dict) -> bool:
    """Check if a file path is allowed by the skill scope rules."""
    if not scope.get("allow_writes", True):
        return False

    # Normalize path — remove leading ./ or /
    path = re.sub(r"^(\./|/)+", "", path)

    # Check blocked patterns first (deny takes priority)
    for pattern in scope.get("blocked_patterns", []):
        if re.match(pattern, path):
            return False

    # If allowed_patterns is defined, path must match at least one
    allowed = scope.get("allowed_patterns")
    if allowed:
        return any(re.match(p, path) for p in allowed)

    # No allowed_patterns means everything (not blocked) is allowed
    return True


def create_skill_file_scope_middleware(skill_id: str):
    """Create a before_model middleware that enforces file scope for a skill.

    Returns None if no scope restrictions exist for the skill.
    """
    scope = SKILL_SCOPE.get(skill_id)
    if not scope:
        return None

    @before_model
    def skill_file_scope(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Check pending tool calls and block writes outside skill scope."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]

        # Check if the last AI message has tool calls
        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            if tool_name not in WRITE_TOOLS:
                continue

            file_path = _extract_file_path(tc)
            if not file_path:
                continue

            if not _is_path_allowed(file_path, scope):
                logger.warning(
                    "Skill %s blocked from writing to %s (outside scope)",
                    skill_id,
                    file_path,
                )
                # Inject a tool result message telling the agent this is blocked
                from langchain_core.messages import ToolMessage

                blocked_msg = ToolMessage(
                    content=(
                        f"BLOCKED: Skill '{skill_id}' is not allowed to modify '{file_path}'. "
                        f"This file is outside the allowed scope for this skill. "
                        f"Please only modify files within your designated scope."
                    ),
                    tool_call_id=tc.get("id", ""),
                )
                return {"messages": [*messages, blocked_msg]}

        return None

    return skill_file_scope
