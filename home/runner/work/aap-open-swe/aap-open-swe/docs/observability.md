# Agent Observability

The `agent/observability` package makes every GitHub Actions run fully transparent — structured log groups, live issue comment progress, and per-tool streaming visibility.

## Architecture

Three independent layers compose together:

```
GitHub Actions runner
│
├── Layer A — gh_actions.py
│   ├── ::group:: / ::endgroup::   (collapsible log sections)
│   ├── ::notice:: / ::warning:: / ::error::  (annotations)
│   └── GITHUB_STEP_SUMMARY        (markdown execution report)
│
├── Layer B — progress_reporter.py
│   └── GitHub REST API → POST/PATCH issue comment
│       (phase bar + tool-call counter, updated in real time)
│
└── Layer C — streaming_callback.py  (LangChain BaseCallbackHandler)
    ├── on_tool_start  → opens ::group::, calls Layer B
    ├── on_tool_end    → closes ::group::
    ├── on_tool_error  → emits ::error::, closes ::group::
    ├── on_chat_model_start → opens ::group:: for LLM call
    ├── on_llm_end     → closes ::group::
    └── on_llm_error   → emits ::error::, closes ::group::
```

Each layer works independently but they are wired together in `agent/run_standalone.py`.

---

## Layer A — GitHub Actions Log Formatting (`gh_actions.py`)

### Functions

#### `gh_group(title: str)` — context manager

Wraps a block of output in a collapsible log group.

```python
from agent.observability import gh_group

with gh_group("Sandbox setup"):
    sandbox = LocalShellBackend(...)
    sandbox.execute("git config user.name 'bot'")
```

GitHub Actions renders this as a collapsed section titled **Sandbox setup**.  All `print()` calls inside the block appear when the section is expanded.

> **Security note:** `title` is sanitised — newlines are stripped and `::` sequences are escaped to prevent log injection.

#### `gh_notice(msg)` / `gh_warning(msg)` / `gh_error(msg)`

Emit GitHub Actions [workflow annotations](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#setting-a-notice-message) that appear in the Actions UI summary.

```python
from agent.observability import gh_notice, gh_warning, gh_error

gh_notice("Model: anthropic:claude-opus-4-6")
gh_warning("Skill not found, falling back to swe-coder")
gh_error("Push failed: 403 Forbidden")
```

#### `write_step_summary(content: str)`

Appends markdown to `$GITHUB_STEP_SUMMARY`.  No-op when the environment variable is not set (e.g., local development).

```python
from agent.observability import write_step_summary

write_step_summary("## Execution Summary\n\n| Key | Value |\n|-----|-------|\n| Skill | doc-generator |")
```

---

## Layer B — Live Progress Reporter (`progress_reporter.py`)

`ProgressReporter` creates a GitHub issue comment on the first call and edits it as phases complete.  This gives users real-time feedback without polling the Actions log.

### Constructor

```python
ProgressReporter(
    github_token: str,
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    comment_id: int | None = None,   # reuse an existing comment
    source_repo: str | None = None,  # "owner/repo" where the issue lives
)
```

If `github_token` or `issue_number` is falsy, the reporter is **disabled** (`enabled=False`) and all methods become no-ops — safe for local development.

### Phase lifecycle

```python
progress = ProgressReporter(github_token=token, repo_owner="acme",
                            repo_name="myrepo", issue_number=42)

progress.start_phase("Setup")        # ⏳ Setup
progress.start_phase("Agent")        # ✅ Setup | ⏳ Agent  (previous auto-completed)
progress.complete_phase("Agent")     # ✅ Setup | ✅ Agent
progress.fail_phase("Push", "403")   # ✅ Setup | ✅ Agent | ❌ Push
progress.finalize(success=True)      # final edit with result snippet
```

### Tool-call logging

```python
progress.log_tool_call("execute", "git commit -m 'fix'")
```

Increments the internal counter and updates the "Last tool" row.  To avoid GitHub API rate limits, the comment is only re-posted every **5 tool calls**.

### Comment format

```markdown
### Agent Progress

⏳ Agent (doc-generator)

| Metric | Value |
|--------|-------|
| Tool calls | 23 |
| Elapsed | 1m42s |
| Last tool | `execute` git add -A |
```

---

## Layer C — Streaming Callback (`streaming_callback.py`)

`AgentStreamingCallback` is a LangChain `BaseCallbackHandler` that intercepts every tool call and LLM invocation.

### Usage

```python
from agent.observability import AgentStreamingCallback, ProgressReporter

progress = ProgressReporter(...)
callback = AgentStreamingCallback(progress_reporter=progress)

result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": task}]},
    config={"callbacks": [callback]},
)

print(f"Total tool calls: {callback.tool_call_count}")
```

### What it does per event

| Event | Action |
|-------|--------|
| `on_tool_start` | Opens `::group::Tool: <name> — <snippet>`, increments counter, calls `progress.log_tool_call()` |
| `on_tool_end` | Prints truncated output (≤500 chars), closes `::endgroup::` |
| `on_tool_error` | Emits `::error::`, closes `::endgroup::` |
| `on_chat_model_start` | Opens `::group::LLM call — <model> (<n> messages)` |
| `on_llm_end` | Closes `::endgroup::` |
| `on_llm_error` | Emits `::error::`, closes `::endgroup::` |

---

## Wiring in `run_standalone.py`

The three layers are wired together in `run_agent()`:

```python
# Layer B — initialise progress reporter
progress = ProgressReporter(
    github_token=github_token,
    repo_owner=repo_owner,
    repo_name=repo_name,
    issue_number=issue_number,
    comment_id=int(os.environ.get("PROGRESS_COMMENT_ID", "0")) or None,
    source_repo=os.environ.get("SOURCE_ISSUE_REPO", f"{repo_owner}/{repo_name}"),
)

# Layer A — wrap phases in log groups
with gh_group("Sandbox setup"):
    sandbox = LocalShellBackend(...)

# Layer C — attach callback to agent invocation
streaming_cb = AgentStreamingCallback(progress_reporter=progress)
invoke_config["callbacks"] = [streaming_cb]

progress.start_phase(f"Agent ({skill_id})")
result = await agent.ainvoke(input, config=invoke_config)
progress.complete_phase(f"Agent ({skill_id})")

# Layer A — write step summary
write_step_summary(summary_markdown)

# Layer B — final comment update
progress.finalize(success=True)
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `PROGRESS_COMMENT_ID` | ID of an existing issue comment to edit (set by the workflow from `context.payload.comment.id`) |
| `SOURCE_ISSUE_REPO` | `owner/repo` where the triggering issue lives (may differ from the target repo on forks) |

---

## Testing

Unit tests live in `tests/test_observability.py` and cover all three layers without making real HTTP calls or GitHub API requests.

```bash
uv run pytest tests/test_observability.py -v
```
