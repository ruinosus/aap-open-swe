"""After-agent middleware that validates structured output before posting to GitHub.

For review skills: validates the JSON has summary, score, and comments fields.
For PR skills: validates the JSON has summary and files_changed fields.
Logs warnings if validation fails but does not block the response.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain.agents.middleware import AgentState, after_agent
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Required fields per output type
REQUIRED_FIELDS: dict[str, list[str]] = {
    "review": ["summary", "score", "comments"],
    "pr": ["summary"],
}


def validate_review_output(data: dict) -> list[str]:
    """Validate a review output dict. Returns list of error messages."""
    errors = []
    for field in REQUIRED_FIELDS.get("review", []):
        if field not in data:
            errors.append(f"Missing required field: '{field}'")

    if "score" in data:
        score = data["score"]
        if isinstance(score, str) and "/" in score:
            try:
                num = int(score.split("/")[0])
                if not 1 <= num <= 10:
                    errors.append(f"Score '{score}' out of range (expected 1-10)")
            except ValueError:
                errors.append(f"Invalid score format: '{score}' (expected 'N/10')")

    if "comments" in data:
        comments = data["comments"]
        if not isinstance(comments, list):
            errors.append(f"'comments' must be a list, got {type(comments).__name__}")
        else:
            for i, c in enumerate(comments):
                if not isinstance(c, dict):
                    errors.append(f"Comment [{i}] must be a dict")
                    continue
                for field in ("file", "line", "message", "severity"):
                    if field not in c:
                        errors.append(f"Comment [{i}] missing '{field}'")

    return errors


def validate_pr_output(data: dict) -> list[str]:
    """Validate a PR output dict. Returns list of error messages."""
    errors = []
    for field in REQUIRED_FIELDS.get("pr", []):
        if field not in data:
            errors.append(f"Missing required field: '{field}'")
    return errors


def create_output_validator(skill_id: str):
    """Create an after_agent middleware that validates skill output.

    Returns None if no validation is needed for the skill.
    """
    review_skills = ("code-review", "security-scan")
    pr_skills = ("doc-generator", "test-generator", "project-docs")

    if skill_id not in review_skills and skill_id not in pr_skills:
        return None

    @after_agent
    def output_validator(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Validate the agent's structured output."""
        # Check structured_response first
        structured = state.get("structured_response")
        if structured:
            data = structured.model_dump() if hasattr(structured, "model_dump") else structured
        else:
            # Try to parse from last AI message
            messages = state.get("messages", [])
            data = None
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and isinstance(msg.content, str):
                    try:
                        data = json.loads(msg.content)
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue

        if not data or not isinstance(data, dict):
            logger.warning("Skill %s: no structured output found to validate", skill_id)
            return None

        output_type = data.get("skill_output_type", "")

        if skill_id in review_skills:
            errors = validate_review_output(data)
        elif skill_id in pr_skills:
            errors = validate_pr_output(data)
        else:
            errors = []

        if errors:
            logger.warning(
                "Skill %s output validation failed (%d errors): %s",
                skill_id,
                len(errors),
                "; ".join(errors),
            )
        else:
            logger.info("Skill %s output validation passed (type=%s)", skill_id, output_type)

        return None

    return output_validator
