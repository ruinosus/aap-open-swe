# Agent Observability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agent execution in GitHub Actions observable in real-time — structured logs, live issue progress, and streaming tool-call visibility.

**Architecture:** Three independent layers: (A) GitHub Actions log groups + step summary for structured logs, (B) live issue comment updates via progress middleware, (C) streaming callbacks that capture every tool call and feed A+B. Each layer works alone but they compose together.

**Tech Stack:** Python logging, GitHub Actions annotations (`::group::`, `::notice::`, `GITHUB_STEP_SUMMARY`), LangChain `BaseCallbackHandler`, GitHub REST API (via `requests`).

---

## File Structure

| File | Responsibility |
|------|---------------|
| Create: `agent/observability/__init__.py` | Package exports |
| Create: `agent/observability/gh_actions.py` | GitHub Actions log formatting (groups, annotations, step summary) |
| Create: `agent/observability/progress_reporter.py` | Live issue comment updater (edit comment with progress) |
| Create: `agent/observability/streaming_callback.py` | LangChain callback handler that captures tool calls and feeds gh_actions + progress_reporter |
| Modify: `agent/run_standalone.py` | Wire the 3 observability layers into agent execution |
| Modify: `.github/workflows/agent.yml` | Pass COMMENT_ID env var for progress updates |
| Create: `tests/test_observability.py` | Unit tests for all 3 layers |

---

## Chunk 1: Layer A — GitHub Actions Log Groups + Step Summary

### Task 1: Create gh_actions.py — log formatting helpers

**Files:**
- Create: `agent/observability/__init__.py`
- Create: `agent/observability/gh_actions.py`
- Test: `tests/test_observability.py`

- [ ] **Step 1: Write failing tests for gh_actions helpers**

```python
# tests/test_observability.py
import io
import os
from unittest.mock import patch

from agent.observability.gh_actions import (
    gh_group,
    gh_notice,
    gh_warning,
    gh_error,
    write_step_summary,
)


class TestGhGroup:
    def test_group_prints_markers(self, capsys):
        with gh_group("Layer 1 — Core"):
            print("doing work")
        out = capsys.readouterr().out
        assert "::group::Layer 1 — Core" in out
        assert "doing work" in out
        assert "::endgroup::" in out

    def test_nested_groups(self, capsys):
        with gh_group("Outer"):
            with gh_group("Inner"):
                print("nested")
        out = capsys.readouterr().out
        assert out.count("::group::") == 2
        assert out.count("::endgroup::") == 2


class TestAnnotations:
    def test_notice(self, capsys):
        gh_notice("All tests passed")
        assert "::notice::All tests passed" in capsys.readouterr().out

    def test_warning(self, capsys):
        gh_warning("No HITL tools found")
        assert "::warning::No HITL tools found" in capsys.readouterr().out

    def test_error(self, capsys):
        gh_error("Push failed")
        assert "::error::Push failed" in capsys.readouterr().out


class TestStepSummary:
    def test_writes_to_github_step_summary(self, tmp_path):
        summary_file = tmp_path / "summary.md"
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
            write_step_summary("## Results\n\nAll good.")
        assert "## Results" in summary_file.read_text()

    def test_noop_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise
            write_step_summary("content")

    def test_appends_to_existing(self, tmp_path):
        summary_file = tmp_path / "summary.md"
        summary_file.write_text("# Existing\n")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
            write_step_summary("## New section")
        content = summary_file.read_text()
        assert "# Existing" in content
        assert "## New section" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_observability.py -v`
Expected: FAIL — `agent.observability` not found

- [ ] **Step 3: Implement gh_actions.py**

```python
# agent/observability/__init__.py
from .gh_actions import gh_group, gh_notice, gh_warning, gh_error, write_step_summary
from .progress_reporter import ProgressReporter
from .streaming_callback import AgentStreamingCallback

__all__ = [
    "gh_group",
    "gh_notice",
    "gh_warning",
    "gh_error",
    "write_step_summary",
    "ProgressReporter",
    "AgentStreamingCallback",
]
```

```python
# agent/observability/gh_actions.py
"""GitHub Actions log formatting — groups, annotations, step summary."""

import os
import sys
from contextlib import contextmanager


@contextmanager
def gh_group(title: str):
    """Emit collapsible log group in GitHub Actions."""
    print(f"::group::{title}", flush=True)
    try:
        yield
    finally:
        print("::endgroup::", flush=True)


def gh_notice(msg: str) -> None:
    """Emit a notice annotation."""
    print(f"::notice::{msg}", flush=True)


def gh_warning(msg: str) -> None:
    """Emit a warning annotation."""
    print(f"::warning::{msg}", flush=True)


def gh_error(msg: str) -> None:
    """Emit an error annotation."""
    print(f"::error::{msg}", flush=True)


def write_step_summary(content: str) -> None:
    """Append markdown to the GitHub Actions step summary."""
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not path:
        return
    with open(path, "a") as f:
        f.write(content)
        f.write("\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_observability.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/observability/__init__.py agent/observability/gh_actions.py tests/test_observability.py
git commit -m "feat: add GitHub Actions log groups and step summary helpers"
```

---

### Task 2: Wire log groups into run_standalone.py

**Files:**
- Modify: `agent/run_standalone.py`

- [ ] **Step 1: Add log groups around major phases in run_standalone.py**

Wrap existing code blocks with `gh_group()`. Key groups:

```python
# At top of run_agent(), after imports:
from agent.observability import gh_group, gh_notice, gh_warning, write_step_summary

# Wrap sandbox setup
with gh_group("Sandbox setup"):
    sandbox = LocalShellBackend(...)
    sandbox.execute("git config user.name ...")
    sandbox.execute("git config user.email ...")

# Wrap model loading
with gh_group(f"Model loading — {model_id}"):
    model = make_model(...)

# Wrap system prompt building
with gh_group(f"System prompt — {skill_id or 'swe-coder'}"):
    # ... existing prompt building code ...
    gh_notice(f"Skill: {skill_id}, prompt length: {len(system_prompt)} chars")

# Wrap middleware assembly
with gh_group(f"Middleware stack ({len(middleware)} layers)"):
    # ... existing middleware code ...

# Wrap agent invocation
with gh_group("Agent execution"):
    result = await agent.ainvoke(...)

# Wrap post-processing
with gh_group("Post-processing"):
    # ... existing result handling ...

# Wrap git operations
with gh_group("Git push"):
    # ... existing push code ...
```

- [ ] **Step 2: Add step summary generation at the end of run_agent()**

After the existing output logic, add:

```python
# Build step summary
summary_lines = [
    "## Agent Execution Summary",
    "",
    f"| Key | Value |",
    f"|-----|-------|",
    f"| **Skill** | `{skill_id or 'swe-coder'}` |",
    f"| **Model** | `{model_id}` |",
    f"| **Repo** | `{repo_owner}/{repo_name}` |",
    f"| **Messages** | {len(messages)} |",
    f"| **Has changes** | {'Yes' if has_changes else 'No'} |",
    f"| **Branch** | `{branch_name}` |",
]

# Count tool calls from messages
tool_call_count = sum(
    len(getattr(m, "tool_calls", []))
    for m in messages
    if hasattr(m, "tool_calls")
)
summary_lines.append(f"| **Tool calls** | {tool_call_count} |")

write_step_summary("\n".join(summary_lines))
```

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 156+ passed

- [ ] **Step 4: Run linter**

Run: `uv run ruff check agent/observability/ agent/run_standalone.py && uv run ruff format --check agent/observability/ agent/run_standalone.py`
Expected: All checks passed

- [ ] **Step 5: Commit**

```bash
git add agent/run_standalone.py
git commit -m "feat: wire GitHub Actions log groups and step summary into agent runner"
```

---

## Chunk 2: Layer B — Live Issue Progress Updates

### Task 3: Create progress_reporter.py

**Files:**
- Create: `agent/observability/progress_reporter.py`
- Test: `tests/test_observability.py` (append)

- [ ] **Step 1: Write failing tests for ProgressReporter**

Append to `tests/test_observability.py`:

```python
from unittest.mock import MagicMock, patch, call
from agent.observability.progress_reporter import ProgressReporter


class TestProgressReporter:
    def test_init_with_all_params(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="ruinosus",
            repo_name="aap-open-swe",
            issue_number=15,
            comment_id=123,
        )
        assert pr.repo_owner == "ruinosus"
        assert pr.comment_id == 123

    def test_init_disabled_without_token(self):
        pr = ProgressReporter(
            github_token="",
            repo_owner="ruinosus",
            repo_name="aap-open-swe",
            issue_number=15,
        )
        assert pr.enabled is False

    def test_format_progress_bar(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._phases = [
            {"name": "Setup", "status": "done"},
            {"name": "Layer 1", "status": "running"},
            {"name": "Layer 2", "status": "pending"},
        ]
        bar = pr._format_progress()
        assert "Setup" in bar
        assert "Layer 1" in bar
        assert "Layer 2" in bar

    def test_start_phase_updates_state(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._post = MagicMock()  # Mock the HTTP call
        pr.start_phase("Layer 1 — Core")
        assert any(p["name"] == "Layer 1 — Core" for p in pr._phases)

    def test_complete_phase_updates_state(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._post = MagicMock()
        pr.start_phase("Layer 1")
        pr.complete_phase("Layer 1")
        phase = next(p for p in pr._phases if p["name"] == "Layer 1")
        assert phase["status"] == "done"

    def test_tool_call_logged(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._post = MagicMock()
        pr.log_tool_call("execute", "git commit -m 'test'")
        assert pr._tool_calls == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_observability.py::TestProgressReporter -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement progress_reporter.py**

```python
# agent/observability/progress_reporter.py
"""Live issue comment updater — edits a GitHub issue comment with progress."""

import logging
import os
import time

import requests

logger = logging.getLogger("progress_reporter")


class ProgressReporter:
    """Updates a GitHub issue comment with real-time agent progress.

    Creates a new comment on init (or reuses comment_id), then edits it
    as phases complete. Progress is shown as a markdown table.
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
        # Set any previous "running" phase to "done"
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
        # Only post every 5 tool calls to avoid rate limiting
        if self._tool_calls % 5 == 0:
            self._post()

    def finalize(self, success: bool = True, result: str = "") -> None:
        """Final update — mark all phases done or failed."""
        for p in self._phases:
            if p["status"] == "running":
                p["status"] = "done" if success else "failed"
        self._post(final=True, result=result)

    def _format_progress(self, final: bool = False, result: str = "") -> str:
        """Build the markdown progress comment."""
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)

        status_icon = {"pending": "\u2b1c", "running": "\u23f3", "done": "\u2705", "failed": "\u274c"}

        lines = ["### Agent Progress\n"]

        # Progress bar
        bar_parts = []
        for p in self._phases:
            icon = status_icon.get(p["status"], "\u2b1c")
            bar_parts.append(f"{icon} {p['name']}")
        if bar_parts:
            lines.append(" | ".join(bar_parts))
            lines.append("")

        # Stats
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
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

        # Use the source repo for comments (the repo where the issue lives)
        source_owner, source_name = self.source_repo.split("/", 1)

        try:
            if self.comment_id:
                # Edit existing comment
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/comments/{self.comment_id}"
                requests.patch(url, headers=headers, json={"body": body}, timeout=10)
            else:
                # Create new comment
                url = f"https://api.github.com/repos/{source_owner}/{source_name}/issues/{self.issue_number}/comments"
                resp = requests.post(url, headers=headers, json={"body": body}, timeout=10)
                if resp.ok:
                    self.comment_id = resp.json().get("id")
        except Exception:
            logger.debug("Failed to update progress comment", exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_observability.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/observability/progress_reporter.py tests/test_observability.py
git commit -m "feat: add live issue comment progress reporter"
```

---

### Task 4: Pass comment ID from workflow to agent

**Files:**
- Modify: `.github/workflows/agent.yml`

- [ ] **Step 1: Add COMMENT_ID output to Extract task step**

In the `Extract task from comment` step, add:

```javascript
// After the existing core.setOutput calls:
core.setOutput('comment_id', context.payload.comment ? context.payload.comment.id : '');
```

- [ ] **Step 2: Pass COMMENT_ID and SOURCE_ISSUE_REPO to Run agent step**

Add to the `Run agent` step env block:

```yaml
PROGRESS_COMMENT_ID: ${{ steps.extract.outputs.comment_id }}
SOURCE_ISSUE_REPO: ${{ github.repository }}
SOURCE_ISSUE_NUMBER: ${{ steps.extract.outputs.issue_number }}
```

Note: `SOURCE_ISSUE_REPO` already exists in the env. `PROGRESS_COMMENT_ID` is new.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/agent.yml
git commit -m "feat: pass comment ID to agent for live progress updates"
```

---

## Chunk 3: Layer C — Streaming Callback Handler

### Task 5: Create streaming_callback.py

**Files:**
- Create: `agent/observability/streaming_callback.py`
- Test: `tests/test_observability.py` (append)

- [ ] **Step 1: Write failing tests for AgentStreamingCallback**

Append to `tests/test_observability.py`:

```python
from agent.observability.streaming_callback import AgentStreamingCallback
from unittest.mock import MagicMock
from uuid import uuid4


class TestAgentStreamingCallback:
    def test_on_tool_start_logs_group(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_tool_start(
            serialized={"name": "execute"},
            input_str="git status",
            run_id=uuid4(),
        )
        out = capsys.readouterr().out
        assert "::group::" in out
        assert "execute" in out

    def test_on_tool_end_closes_group(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_tool_end(output="done", run_id=uuid4())
        out = capsys.readouterr().out
        assert "::endgroup::" in out

    def test_on_tool_start_calls_progress_reporter(self):
        reporter = MagicMock()
        cb = AgentStreamingCallback(progress_reporter=reporter)
        cb.on_tool_start(
            serialized={"name": "execute"},
            input_str="git commit",
            run_id=uuid4(),
        )
        reporter.log_tool_call.assert_called_once()

    def test_on_tool_error_emits_gh_error(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_tool_error(error=Exception("fail"), run_id=uuid4())
        out = capsys.readouterr().out
        assert "::error::" in out

    def test_on_chat_model_start_logs(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_chat_model_start(
            serialized={"id": ["langchain", "chat_models", "ChatOpenAI"]},
            messages=[[]],
            run_id=uuid4(),
        )
        out = capsys.readouterr().out
        assert "::group::" in out
        assert "LLM" in out

    def test_tool_call_counter(self):
        cb = AgentStreamingCallback()
        cb.on_tool_start(serialized={"name": "a"}, input_str="", run_id=uuid4())
        cb.on_tool_end(output="", run_id=uuid4())
        cb.on_tool_start(serialized={"name": "b"}, input_str="", run_id=uuid4())
        cb.on_tool_end(output="", run_id=uuid4())
        assert cb.tool_call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_observability.py::TestAgentStreamingCallback -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement streaming_callback.py**

```python
# agent/observability/streaming_callback.py
"""LangChain callback handler that captures tool calls for observability."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .gh_actions import gh_error, gh_notice

logger = logging.getLogger("streaming_callback")


class AgentStreamingCallback(BaseCallbackHandler):
    """Callback handler that emits GitHub Actions log groups per tool call
    and feeds progress updates to ProgressReporter.

    Usage:
        callback = AgentStreamingCallback(progress_reporter=reporter)
        agent.ainvoke(input, config={"callbacks": [callback]})
    """

    def __init__(self, progress_reporter=None):
        super().__init__()
        self.progress_reporter = progress_reporter
        self.tool_call_count = 0
        self._active_groups: dict[UUID, str] = {}

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        snippet = str(input_str)[:80].replace("\n", " ")
        print(f"::group::Tool: {tool_name} — {snippet}", flush=True)
        self._active_groups[run_id] = tool_name
        self.tool_call_count += 1

        if self.progress_reporter:
            self.progress_reporter.log_tool_call(tool_name, snippet)

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        # Print truncated output then close group
        out_str = str(output)
        if len(out_str) > 500:
            print(f"(output: {len(out_str)} chars)", flush=True)
        print("::endgroup::", flush=True)
        self._active_groups.pop(run_id, None)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = self._active_groups.pop(run_id, "unknown")
        gh_error(f"Tool {tool_name} failed: {error}")
        print("::endgroup::", flush=True)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model_id = serialized.get("id", ["unknown"])
        model_name = model_id[-1] if isinstance(model_id, list) else str(model_id)
        msg_count = sum(len(batch) for batch in messages)
        print(f"::group::LLM call — {model_name} ({msg_count} messages)", flush=True)
        self._active_groups[run_id] = "llm"

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        gh_error(f"LLM call failed: {error}")
        if run_id in self._active_groups:
            print("::endgroup::", flush=True)
            self._active_groups.pop(run_id, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_observability.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/observability/streaming_callback.py tests/test_observability.py
git commit -m "feat: add streaming callback handler for tool-level observability"
```

---

## Chunk 4: Wire Everything Together

### Task 6: Wire all 3 layers into run_standalone.py

**Files:**
- Modify: `agent/run_standalone.py`

- [ ] **Step 1: Add ProgressReporter initialization after sandbox setup**

```python
# After sandbox setup, before model loading:
from agent.observability import ProgressReporter, AgentStreamingCallback, gh_group, gh_notice, write_step_summary

progress = ProgressReporter(
    github_token=github_token,
    repo_owner=repo_owner,
    repo_name=repo_name,
    issue_number=issue_number,
    comment_id=int(os.environ.get("PROGRESS_COMMENT_ID", "0")) or None,
    source_repo=os.environ.get("SOURCE_ISSUE_REPO", f"{repo_owner}/{repo_name}"),
)
progress.start_phase("Setup")
```

- [ ] **Step 2: Add phase tracking around major sections**

```python
# After middleware assembly:
progress.complete_phase("Setup")
progress.start_phase(f"Agent ({skill_id or 'swe-coder'})")

# Create callback
streaming_cb = AgentStreamingCallback(progress_reporter=progress)
```

- [ ] **Step 3: Pass callback to agent.ainvoke()**

Change:
```python
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": task}]},
    config=invoke_config,
)
```

To:
```python
invoke_config["callbacks"] = [streaming_cb]
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": task}]},
    config=invoke_config,
)
```

- [ ] **Step 4: Add post-execution phases**

```python
# After agent finishes:
progress.complete_phase(f"Agent ({skill_id or 'swe-coder'})")

# Before push:
progress.start_phase("Push & PR")

# After push:
progress.complete_phase("Push & PR")

# At the very end:
progress.finalize(success=has_changes or not use_default_tools, result=agent_response[:500])
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 156+ original + new observability tests all pass

- [ ] **Step 6: Run linter**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: All checks passed

- [ ] **Step 7: Commit**

```bash
git add agent/run_standalone.py agent/observability/__init__.py
git commit -m "feat: wire observability (log groups + progress + callbacks) into agent runner"
```

---

### Task 7: Update workflow to pass comment ID

**Files:**
- Modify: `.github/workflows/agent.yml`

- [ ] **Step 1: Add comment_id output to ALL extract steps**

For each trigger job (run-agent, run-agent-on-open, run-agent-on-label, etc.), add to the extract step:

```javascript
core.setOutput('comment_id', context.payload.comment ? String(context.payload.comment.id) : '');
```

- [ ] **Step 2: Add PROGRESS_COMMENT_ID env to ALL Run agent steps**

```yaml
PROGRESS_COMMENT_ID: ${{ steps.extract.outputs.comment_id }}
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/agent.yml
git commit -m "feat: pass comment ID to all agent jobs for live progress"
```

---

### Task 8: Final integration test

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -v`
Expected: All tests pass

- [ ] **Step 2: Run linter**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: Clean

- [ ] **Step 3: Verify observability import works end-to-end**

Run:
```bash
uv run python3 -c "
from agent.observability import gh_group, gh_notice, gh_warning, gh_error, write_step_summary, ProgressReporter, AgentStreamingCallback
print('All observability imports OK')
pr = ProgressReporter(github_token='', repo_owner='o', repo_name='r', issue_number=1)
print(f'ProgressReporter enabled={pr.enabled}')
cb = AgentStreamingCallback(progress_reporter=pr)
print(f'AgentStreamingCallback tool_call_count={cb.tool_call_count}')
print('Integration check passed')
"
```
Expected: `All observability imports OK`, `Integration check passed`

- [ ] **Step 4: Final commit with all changes**

```bash
git add -A
git commit -m "feat: complete agent observability system (log groups + live progress + streaming)"
```
