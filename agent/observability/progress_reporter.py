"""Live issue comment updater — edits a GitHub issue comment with progress."""

import logging
import time

import requests

logger = logging.getLogger("progress_reporter")


class ProgressReporter:
    """Updates a GitHub issue comment with real-time agent progress.

    Creates a new comment on first post, then edits it as phases complete.
    Shows: skill, model, repo, phases, tool calls, tokens, cost, duration.
    """

    def __init__(
        self,
        github_token: str,
        repo_owner: str,
        repo_name: str,
        issue_number: int,
        comment_id: int | None = None,
        source_repo: str | None = None,
        skill_id: str = "",
        model_id: str = "",
    ):
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.issue_number = issue_number
        self.comment_id = comment_id
        self.source_repo = source_repo or f"{repo_owner}/{repo_name}"
        self.skill_id = skill_id
        self.model_id = model_id
        self.enabled = bool(github_token and issue_number)
        self._phases: list[dict] = []
        self._tool_calls = 0
        self._start_time = time.time()
        # Token tracking — populated from streaming callback
        self.input_tokens = 0
        self.output_tokens = 0
        self.llm_calls = 0
        self.estimated_cost: float | None = None

    def start_phase(self, name: str) -> None:
        """Mark a phase as started."""
        for p in self._phases:
            if p["status"] == "running":
                p["status"] = "done"
        self._phases.append({"name": name, "status": "running"})
        self._post()

    def complete_phase(self, name: str) -> None:
        """Mark a phase as completed."""
        for p in self._phases:
            if p["name"] == name:
                p["status"] = "done"
        self._post()

    def fail_phase(self, name: str, error: str = "") -> None:
        """Mark a phase as failed."""
        for p in self._phases:
            if p["name"] == name:
                p["status"] = "failed"
                if error:
                    p["error"] = error
        self._post()

    def log_tool_call(self, tool_name: str, snippet: str = "") -> None:
        """Log a tool call (increments counter)."""
        self._tool_calls += 1
        if self._tool_calls % 5 == 0:
            self._post()

    def update_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        llm_calls: int,
        estimated_cost: float | None,
    ) -> None:
        """Update token usage stats from the streaming callback."""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.llm_calls = llm_calls
        self.estimated_cost = estimated_cost

    def finalize(self, success: bool = True, execution_report: str = "") -> None:
        """Final update — replace progress comment with execution report."""
        for p in self._phases:
            if p["status"] == "running":
                p["status"] = "done" if success else "failed"
        if execution_report:
            self._post_body(execution_report)
        else:
            self._post(final=True)

    def _format_progress(self, final: bool = False) -> str:
        """Build the markdown progress comment."""
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)

        status_icon = {
            "pending": "\u2b1c",
            "running": "\u23f3",
            "done": "\u2705",
            "failed": "\u274c",
        }

        lines = ["### Agent Execution\n"]

        # Context table
        lines.append("| | |")
        lines.append("|---|---|")
        if self.skill_id:
            lines.append(f"| **Skill** | `{self.skill_id}` |")
        if self.model_id:
            lines.append(f"| **Model** | `{self.model_id}` |")
        lines.append(f"| **Repo** | `{self.repo_owner}/{self.repo_name}` |")
        lines.append(f"| **Duration** | {mins}m{secs:02d}s |")
        lines.append("")

        # Progress bar
        bar_parts = []
        for p in self._phases:
            icon = status_icon.get(p["status"], "\u2b1c")
            bar_parts.append(f"{icon} {p['name']}")
        if bar_parts:
            lines.append(" | ".join(bar_parts))
            lines.append("")

        # Usage table
        total_tokens = self.input_tokens + self.output_tokens
        if total_tokens > 0 or self._tool_calls > 0:
            lines.append("#### Usage")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            if self.llm_calls:
                lines.append(f"| LLM calls | {self.llm_calls} |")
            if total_tokens > 0:
                lines.append(f"| Input tokens | {self.input_tokens:,} |")
                lines.append(f"| Output tokens | {self.output_tokens:,} |")
                lines.append(f"| Total tokens | {total_tokens:,} |")
            if self._tool_calls:
                lines.append(f"| Tool calls | {self._tool_calls} |")
            if self.estimated_cost is not None:
                lines.append(f"| **Estimated cost** | **${self.estimated_cost:.4f}** |")

        return "\n".join(lines)

    def _post_body(self, body: str) -> None:
        """Post or edit a comment with the given body text."""
        if not self.enabled:
            return
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github+json",
        }
        if "/" not in self.source_repo:
            logger.debug("Invalid source_repo for _post_body: %s", self.source_repo)
            return
        source_owner, source_name = self.source_repo.split("/", 1)
        try:
            if self.comment_id:
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/comments/{self.comment_id}"
                resp = requests.patch(url, headers=headers, json={"body": body}, timeout=10)
                if not resp.ok:
                    logger.debug("_post_body PATCH failed: %s", resp.status_code)
            else:
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/{self.issue_number}/comments"
                resp = requests.post(url, headers=headers, json={"body": body}, timeout=10)
                if resp.ok:
                    self.comment_id = resp.json().get("id")
                else:
                    logger.debug("_post_body POST failed: %s", resp.status_code)
        except Exception:
            logger.debug("Failed to post body", exc_info=True)

    def _post(self, final: bool = False) -> None:
        """Create or edit the progress comment on GitHub."""
        if not self.enabled:
            return

        body = self._format_progress(final=final)
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github+json",
        }

        if "/" not in self.source_repo:
            logger.debug("Invalid source_repo format: %s", self.source_repo)
            return
        source_owner, source_name = self.source_repo.split("/", 1)

        try:
            if self.comment_id:
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/comments/{self.comment_id}"
                resp = requests.patch(url, headers=headers, json={"body": body}, timeout=10)
                if not resp.ok:
                    logger.debug("PATCH failed: %s", resp.status_code)
            else:
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/{self.issue_number}/comments"
                resp = requests.post(url, headers=headers, json={"body": body}, timeout=10)
                if resp.ok:
                    self.comment_id = resp.json().get("id")
                else:
                    logger.debug("POST failed: %s", resp.status_code)
        except Exception:
            logger.debug("Failed to update progress comment", exc_info=True)
