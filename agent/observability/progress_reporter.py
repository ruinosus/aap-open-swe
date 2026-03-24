"""Live issue comment updater — edits a GitHub issue comment with progress."""

import logging
import time

import requests

logger = logging.getLogger("progress_reporter")


class ProgressReporter:
    """Updates a GitHub issue comment with real-time agent progress.

    Creates a new comment on first post, then edits it as phases complete.
    """

    def __init__(
        self,
        github_token: str,
        repo_owner: str,
        repo_name: str,
        issue_number: int,
        comment_id: int | None = None,
        source_repo: str | None = None,
    ):
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.issue_number = issue_number
        self.comment_id = comment_id
        self.source_repo = source_repo or f"{repo_owner}/{repo_name}"
        self.enabled = bool(github_token and issue_number)
        self._phases: list[dict] = []
        self._tool_calls = 0
        self._start_time = time.time()
        self._last_tool = ""

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
        """Log a tool call (increments counter, updates last tool)."""
        self._tool_calls += 1
        self._last_tool = f"`{tool_name}` {snippet[:60]}" if snippet else f"`{tool_name}`"
        if self._tool_calls % 5 == 0:
            self._post()

    def finalize(self, success: bool = True, result: str = "") -> None:
        """Final update — mark all running phases done or failed."""
        for p in self._phases:
            if p["status"] == "running":
                p["status"] = "done" if success else "failed"
        self._post(final=True, result=result)

    def _format_progress(self, final: bool = False, result: str = "") -> str:
        """Build the markdown progress comment."""
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)

        status_icon = {
            "pending": "\u2b1c",
            "running": "\u23f3",
            "done": "\u2705",
            "failed": "\u274c",
        }

        lines = ["### Agent Progress\n"]

        bar_parts = []
        for p in self._phases:
            icon = status_icon.get(p["status"], "\u2b1c")
            bar_parts.append(f"{icon} {p['name']}")
        if bar_parts:
            lines.append(" | ".join(bar_parts))
            lines.append("")

        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Tool calls | {self._tool_calls} |")
        lines.append(f"| Elapsed | {mins}m{secs:02d}s |")
        if self._last_tool:
            lines.append(f"| Last tool | {self._last_tool} |")

        if final and result:
            lines.append("")
            lines.append(f"<details><summary>Result</summary>\n\n{result[:3000]}\n\n</details>")

        return "\n".join(lines)

    def _post(self, final: bool = False, result: str = "") -> None:
        """Create or edit the progress comment on GitHub."""
        if not self.enabled:
            return

        body = self._format_progress(final=final, result=result)
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github+json",
        }

        source_owner, source_name = self.source_repo.split("/", 1)

        try:
            if self.comment_id:
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/comments/{self.comment_id}"
                requests.patch(url, headers=headers, json={"body": body}, timeout=10)
            else:
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/{self.issue_number}/comments"
                resp = requests.post(url, headers=headers, json={"body": body}, timeout=10)
                if resp.ok:
                    self.comment_id = resp.json().get("id")
        except Exception:
            logger.debug("Failed to update progress comment", exc_info=True)
