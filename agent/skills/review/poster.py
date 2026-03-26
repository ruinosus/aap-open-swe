"""GitHub Reviews API integration for code-review and security-scan skills.

Parses structured JSON output from the agent and posts inline PR comments
via the GitHub Reviews API.
"""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)


def _try_parse_json(text: str) -> dict | None:
    """Attempt to parse text as JSON, returning dict or None."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _is_review(data: dict) -> bool:
    """Check if parsed dict looks like a review output."""
    return data.get("skill_output_type") == "review" or ("comments" in data and "summary" in data)


def parse_review_output(agent_response: str) -> dict | None:
    """Extract structured review JSON from agent response.

    Uses multiple strategies to find valid review JSON:
    1. Direct JSON parse (whole response is JSON)
    2. Markdown code blocks (```json ... ``` or ``` ... ```)
    3. Brace-matching extraction (find outermost { ... })
    4. Lenient fallback (look for summary + comments fields)

    Returns the parsed dict or None if not found/invalid.
    """
    if not agent_response or not agent_response.strip():
        return None

    text = agent_response.strip()

    # Strategy 1: Direct parse — whole response is valid JSON
    data = _try_parse_json(text)
    if data and _is_review(data):
        return data

    # Strategy 2: Markdown code blocks
    code_block_patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(\{.*?\})\s*```",
    ]
    for pattern in code_block_patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            data = _try_parse_json(match.strip())
            if data and _is_review(data):
                return data

    # Strategy 3: Find the outermost JSON object using brace matching
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    data = _try_parse_json(candidate)
                    if data and _is_review(data):
                        return data
                    break

    # Strategy 4: Find ANY JSON object containing skill_output_type
    # Handles cases where the model outputs prose + JSON
    json_obj_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
    for match in re.finditer(json_obj_pattern, text, re.DOTALL):
        data = _try_parse_json(match.group())
        if data and _is_review(data):
            return data

    return None


def format_review_summary(review: dict, skill_id: str) -> str:
    """Format review data as a markdown summary comment."""
    from agent.config import get_manifest, get_module_display_name, get_skill
    from agent.config.templates import render_template

    skill_obj = get_skill(skill_id)
    skill_name = skill_obj.name if skill_obj else skill_id
    score = review.get("score", "N/A")
    summary = review.get("summary", "No summary provided.")
    comments = review.get("comments", [])

    # Count by severity
    severities = {}
    for c in comments:
        sev = c.get("severity", "info")
        severities[sev] = severities.get(sev, 0) + 1

    severity_line = " | ".join(f"**{k}**: {v}" for k, v in sorted(severities.items()))

    get_manifest()  # ensure manifest is loaded
    module_name = get_module_display_name()

    # Try template rendering first
    rendered = render_template(
        "reviewSummary",
        {
            "module_name": module_name,
            "skill_name": skill_name,
            "score": score,
            "summary": summary,
            "severity_line": severity_line,
            "comment_count": len(comments) if comments else 0,
        },
    )

    return rendered or ""


def post_pr_review(
    owner: str,
    repo: str,
    pr_number: int,
    review: dict,
    skill_id: str,
    github_token: str | None = None,
) -> bool:
    """Post a PR review with inline comments via GitHub Reviews API.

    Returns True if successful, False otherwise.
    """
    token = github_token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        logger.error("No GitHub token available for posting review")
        return False

    comments = review.get("comments", [])
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Build review comments for the API
    review_comments = []
    for c in comments:
        review_comments.append(
            {
                "path": c["file"],
                "line": c.get("line", 1),
                "body": f"**[{c.get('severity', 'info').upper()}]** {c['message']}",
            }
        )

    body = format_review_summary(review, skill_id)

    payload = {
        "body": body,
        "event": "COMMENT",
        "comments": review_comments,
    }

    try:
        resp = httpx.post(api_url, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            logger.info("Posted PR review with %d inline comments", len(review_comments))
            return True

        # 422 "Line could not be resolved" — inline comments reference lines
        # not in the current diff (e.g., after a fix commit). Retry without
        # inline comments, posting the summary + findings as a single comment.
        if resp.status_code == 422 and review_comments:
            logger.warning("Inline comments failed (422), retrying as summary-only review")
            # Build findings table as part of the body
            findings_md = "\n".join(
                f"- **[{c.get('severity', 'info').upper()}]** `{c['file']}:{c.get('line', '?')}` — {c['message']}"
                for c in comments
            )
            fallback_body = body + f"\n\n{findings_md}"
            fallback_payload = {"body": fallback_body, "event": "COMMENT", "comments": []}
            resp2 = httpx.post(api_url, headers=headers, json=fallback_payload, timeout=30)
            if resp2.status_code in (200, 201):
                logger.info("Posted PR review as summary-only (no inline comments)")
                return True
            logger.error("Fallback review also failed: %s %s", resp2.status_code, resp2.text[:200])
            return False

        logger.error("Failed to post PR review: %s %s", resp.status_code, resp.text[:200])
        return False
    except Exception:
        logger.exception("Failed to post PR review")
        return False
