"""Respond to PR review comments by checking if findings were addressed."""

import json
import logging
import os
import subprocess

import requests

logger = logging.getLogger("review_responder")


def get_review_comments(repo_owner: str, repo_name: str, pr_number: int, token: str) -> list[dict]:
    """Fetch all review comments on a PR."""
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/comments"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    comments = []
    page = 1
    while True:
        resp = requests.get(
            url, headers=headers, params={"page": page, "per_page": 100}, timeout=15
        )
        if not resp.ok:
            logger.warning("Failed to fetch PR comments: %s", resp.status_code)
            break
        batch = resp.json()
        if not batch:
            break
        comments.extend(batch)
        page += 1
    return comments


def get_changed_files_since(commit_sha: str, repo_dir: str = ".") -> set[str]:
    """Get set of files changed between commit_sha and HEAD."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{commit_sha}..HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_dir,
        )
        if result.returncode == 0:
            return {f.strip() for f in result.stdout.strip().split("\n") if f.strip()}
    except Exception:
        logger.debug("git diff failed", exc_info=True)
    return set()


def reply_to_comment(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    comment_id: int,
    body: str,
    token: str,
) -> bool:
    """Post a reply to a PR review comment."""
    url = (
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/comments/{comment_id}/replies"
    )
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    resp = requests.post(url, headers=headers, json={"body": body}, timeout=10)
    if not resp.ok:
        logger.warning("Failed to reply to comment %s: %s", comment_id, resp.status_code)
    return resp.ok


def respond_to_review(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    token: str,
    repo_dir: str = ".",
    bot_login: str = "github-actions",
) -> dict:
    """Respond to all unaddressed review comments on a PR.

    For each comment:
    - If the file was changed since the comment was made -> "Fixed in {sha}"
    - If it already has a reply from us -> skip
    - If severity is LOW and not changed -> "Acknowledged"

    Returns summary dict with counts.
    """
    comments = get_review_comments(repo_owner, repo_name, pr_number, token)
    if not comments:
        return {"total": 0, "replied": 0, "skipped": 0}

    # Group comments: only top-level (no in_reply_to_id), from bot
    top_level = [
        c
        for c in comments
        if c.get("user", {}).get("login") == bot_login and not c.get("in_reply_to_id")
    ]
    replies_by_parent = {}
    for c in comments:
        parent = c.get("in_reply_to_id")
        if parent:
            replies_by_parent.setdefault(parent, []).append(c)

    # Get HEAD sha
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_dir,
        )
        head_sha = head_result.stdout.strip() if head_result.returncode == 0 else "HEAD"
    except Exception:
        head_sha = "HEAD"

    stats = {"total": len(top_level), "replied": 0, "skipped": 0, "already_replied": 0}

    for comment in top_level:
        comment_id = comment["id"]
        path = comment.get("path", "")
        body = comment.get("body", "")

        # Skip if we already replied
        existing_replies = replies_by_parent.get(comment_id, [])
        our_replies = [r for r in existing_replies if r.get("user", {}).get("login") != bot_login]
        if our_replies:
            stats["already_replied"] += 1
            stats["skipped"] += 1
            continue

        # Check if file was changed since comment's commit
        original_commit = comment.get("original_commit_id", "")
        changed_files = (
            get_changed_files_since(original_commit, repo_dir) if original_commit else set()
        )

        if path in changed_files:
            reply = f"Addressed in {head_sha}."
            if reply_to_comment(repo_owner, repo_name, pr_number, comment_id, reply, token):
                stats["replied"] += 1
            else:
                stats["skipped"] += 1
        elif "[LOW]" in body:
            reply = "Acknowledged."
            if reply_to_comment(repo_owner, repo_name, pr_number, comment_id, reply, token):
                stats["replied"] += 1
            else:
                stats["skipped"] += 1
        else:
            stats["skipped"] += 1

    return stats


def main():
    """CLI entry point for responding to PR reviews."""
    repo_owner = os.environ.get("REPO_OWNER", "")
    repo_name = os.environ.get("REPO_NAME", "")
    pr_number = int(os.environ.get("PR_NUMBER", "0"))
    token = os.environ.get("GITHUB_TOKEN", "")
    repo_dir = os.environ.get("REPO_DIR", ".")

    if not all([repo_owner, repo_name, pr_number, token]):
        logger.error("REPO_OWNER, REPO_NAME, PR_NUMBER, and GITHUB_TOKEN are required")
        return

    stats = respond_to_review(repo_owner, repo_name, pr_number, token, repo_dir)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
    main()
