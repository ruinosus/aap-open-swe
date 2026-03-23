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


def parse_review_output(agent_response: str) -> dict | None:
    """Extract structured review JSON from agent response.

    Looks for a JSON block with skill_output_type == "review".
    Returns the parsed dict or None if not found/invalid.
    """
    # Try to find JSON in the response (may be wrapped in markdown code blocks)
    json_patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"(\{[^{}]*\"skill_output_type\"[^{}]*\})",
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, agent_response, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict) and data.get("skill_output_type") == "review":
                    return data
            except (json.JSONDecodeError, TypeError):
                continue

    # Try parsing the whole string as JSON
    try:
        data = json.loads(agent_response)
        if isinstance(data, dict) and data.get("skill_output_type") == "review":
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    return None


def format_review_summary(review: dict, skill_id: str) -> str:
    """Format review data as a markdown summary comment."""
    skill_name = "Code Review" if skill_id == "code-review" else "Security Scan"
    score = review.get("score", "N/A")
    summary = review.get("summary", "No summary provided.")
    comments = review.get("comments", [])

    # Count by severity
    severities = {}
    for c in comments:
        sev = c.get("severity", "info")
        severities[sev] = severities.get(sev, 0) + 1

    severity_line = " | ".join(f"**{k}**: {v}" for k, v in sorted(severities.items()))

    md = f"### AAP Open SWE — {skill_name}\n\n"
    md += f"**Score:** {score}\n\n"
    md += f"{summary}\n\n"
    if severity_line:
        md += f"**Findings:** {severity_line}\n\n"
    if comments:
        md += f"**{len(comments)} inline comment(s)** posted on this PR.\n"
    else:
        md += "No issues found.\n"

    return md


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
            logger.info("Posted PR review with %d comments", len(review_comments))
            return True
        else:
            logger.error("Failed to post PR review: %s %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Failed to post PR review")
        return False
