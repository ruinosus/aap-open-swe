"""Repository protection middleware — prevents pushing to unauthorized repos.

Enforces two critical safety rules:

1. **Whitelist enforcement:** Only repos owned by orgs in ALLOWED_GITHUB_ORGS
   can receive direct pushes. If the allowlist is empty, all orgs are allowed
   (backwards compatible).

2. **Fork enforcement:** For repos outside the whitelist, the agent MUST fork
   first and push to the fork — never to the original repo. This prevents
   polluting third-party repositories.

This middleware intercepts tool calls to `execute` that contain `git push`
and validates the target repo before allowing the push.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain.agents.middleware import AgentState, before_model
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


def _extract_push_target(command: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a git push command.

    Handles formats:
    - git push https://...github.com/owner/repo.git ...
    - git push origin ...
    - git push https://x-access-token:TOKEN@github.com/owner/repo.git ...
    """
    # Match github.com/owner/repo in push URLs
    match = re.search(r"github\.com[/:]([^/\s]+)/([^/\s.]+?)(?:\.git)?(?:\s|$)", command)
    if match:
        return match.group(1).lower(), match.group(2).lower()
    return None


def create_repo_protection_middleware(
    allowed_orgs: frozenset[str],
    current_repo_owner: str,
    current_repo_name: str,
):
    """Create middleware that blocks pushes to repos outside the allowed orgs.

    Args:
        allowed_orgs: Set of allowed GitHub org/owner names (lowercase).
                      If empty, all orgs are allowed (no restriction).
        current_repo_owner: The owner of the repo the agent is working on.
        current_repo_name: The name of the repo the agent is working on.

    Returns:
        A @before_model middleware, or None if no restrictions apply.
    """
    if not allowed_orgs:
        logger.info("No ALLOWED_GITHUB_ORGS configured — repo protection disabled")
        return None

    @before_model
    def repo_protection(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Block git push to repos outside the allowed org whitelist."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            if tool_name != "execute":
                continue

            args = tc.get("args", {})
            command = args.get("command", "") or args.get("cmd", "")
            if not command or "git push" not in command:
                continue

            target = _extract_push_target(command)
            if not target:
                continue

            target_owner, target_repo = target

            # Check if target is in whitelist
            if target_owner in allowed_orgs:
                continue

            # Block — this is a push to an unauthorized repo
            logger.warning(
                "BLOCKED: Push to %s/%s denied — org '%s' not in ALLOWED_GITHUB_ORGS (%s). "
                "For external repos, use fork first.",
                target_owner,
                target_repo,
                target_owner,
                ", ".join(sorted(allowed_orgs)),
            )
            return {
                "messages": [
                    *messages,
                    ToolMessage(
                        content=(
                            f"BLOCKED: Cannot push to {target_owner}/{target_repo}. "
                            f"The organization '{target_owner}' is not in the allowed list. "
                            f"Allowed organizations: {', '.join(sorted(allowed_orgs))}. "
                            f"For external repositories, you MUST fork the repo first to your "
                            f"own organization, then push to the fork."
                        ),
                        tool_call_id=tc.get("id", ""),
                    ),
                ],
            }

        return None

    return repo_protection
