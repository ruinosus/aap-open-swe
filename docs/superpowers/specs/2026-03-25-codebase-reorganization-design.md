# Codebase Reorganization — Design Spec

## Summary

Reorganize the `agent/` directory from a flat dump of 50+ files into a layered,
feature-first structure that supports both entry points (standalone runner +
webapp server) as first-class citizens. Migrate `aap_config.py` to use AAP SDK
v0.9.0 `ManifestInstance` convenience methods, eliminating ~280 lines of
accessor boilerplate (333 → ~50 lines, 34 → 18 functions).

**Goal:** A new contributor opens the repo and understands the structure in 30
seconds. When adding a new skill or adapter, the location is obvious.

**Scope:** File moves, import updates, `aap_config.py` rewrite. No behavior changes.

**Breaking:** No — all public interfaces stay the same, only internal paths change.

---

## Current State (problems)

- `agent/` is a flat dump: 50+ files, no hierarchy
- `run_standalone.py` (567 lines) is a God Object — setup, prompt, middleware, invoke, push, report
- `webapp.py` (1528 lines) is a webhook monster
- `utils/` has 15 files with no coherence (5 github_*.py files)
- `review_poster.py` and `review_responder.py` loose in the root
- `schemas.py` mixes 6 different output types
- `aap_config.py` has 34 accessor functions, all reimplementing what the SDK does
- 70% of code (35 files, ~5500 lines) is webapp-only, mixed with the 14 standalone files
- `utils/messages.py` is dead code (imported by nothing)

---

## Target Structure

```
agent/
  # ── Layer 1: Entry Points ──────────────────
  runner/                     # GitHub Actions standalone
    __init__.py
    standalone.py             # Main entry point (slim orchestrator)
    sizing_formatter.py       # _format_sizing_markdown() extracted
  server/                     # LangGraph webapp + server
    __init__.py
    webapp.py                 # Webhook handlers (from agent/webapp.py)
    graph.py                  # LangGraph graph (from agent/server.py)
    prompt.py                 # System prompt builder (from agent/prompt.py)
    encryption.py             # Token encryption (from agent/encryption.py)
    agents_md.py              # AGENTS.md parser (from agent/utils/agents_md.py)
    multimodal.py             # Image handling (from agent/utils/multimodal.py)
    langsmith.py              # LangSmith trace URL (from agent/utils/langsmith.py)

  # ── Layer 2: Core ──────────────────────────
  config/                     # Manifest-driven configuration
    __init__.py               # Exports get_manifest, get_model_id, etc.
    manifest.py               # ManifestInstance wrapper (SDK v0.8.0)
    model.py                  # make_model() factory (from agent/utils/model.py)
  skills/                     # Skill-specific logic
    __init__.py
    schemas.py                # All Pydantic output schemas (from agent/schemas.py)
    review/
      __init__.py
      poster.py               # PR review posting (from agent/review_poster.py)
      responder.py            # Review reply automation (from agent/review_responder.py)
  middleware/                  # No changes — already organized
    __init__.py
    check_message_queue.py
    ensure_no_empty_msg.py
    open_pr.py
    output_validator.py
    repo_protection.py
    tool_error_handler.py
  observability/               # No changes — already organized
    __init__.py
    execution_report.py
    gh_actions.py
    progress_reporter.py
    streaming_callback.py

  # ── Layer 3: Adapters ──────────────────────
  github/                     # All GitHub API interactions
    __init__.py
    auth.py                   # GitHub App auth (from agent/utils/auth.py)
    comments.py               # Comment posting (merge utils/github_comments.py + utils/comments.py)
    app.py                    # App token management (merge utils/github_app.py + github_token.py)
    users.py                  # User-email mapping (from agent/utils/github_user_email_map.py)
    api.py                    # Core GitHub API (from agent/utils/github.py)
    repo.py                   # Repo utilities (from agent/utils/repo.py)
  slack/
    __init__.py
    client.py                 # Slack API (from agent/utils/slack.py)
  linear/
    __init__.py
    client.py                 # Linear API (merge utils/linear.py + linear_team_repo_map.py)
  sandbox/                    # Sandbox providers
    __init__.py
    state.py                  # State management (merge utils/sandbox.py + sandbox_paths.py + sandbox_state.py)
    providers/                # (from agent/integrations/)
      __init__.py
      daytona.py
      langsmith.py
      local.py
      modal.py
      runloop.py
  tools/                      # No changes — already organized
    __init__.py
    commit_and_open_pr.py
    fetch_url.py
    github_comment.py
    http_request.py
    linear_comment.py
    slack_thread_reply.py
```

---

## File Move Map

### Deletes

| File | Reason |
|------|--------|
| `agent/aap_config.py` | Replaced by `config/manifest.py` using SDK v0.8.0 |
| `agent/utils/messages.py` | Dead code — imported by nothing |
| `agent/utils/` (directory) | All files moved to domain-specific packages |

### Moves (no content changes)

| From | To |
|------|-----|
| `agent/webapp.py` | `agent/server/webapp.py` |
| `agent/server.py` | `agent/server/graph.py` |
| `agent/prompt.py` | `agent/server/prompt.py` |
| `agent/encryption.py` | `agent/server/encryption.py` |
| `agent/utils/agents_md.py` | `agent/server/agents_md.py` |
| `agent/utils/multimodal.py` | `agent/server/multimodal.py` |
| `agent/utils/langsmith.py` | `agent/server/langsmith.py` |
| `agent/utils/model.py` | `agent/config/model.py` |
| `agent/schemas.py` | `agent/skills/schemas.py` |
| `agent/review_poster.py` | `agent/skills/review/poster.py` |
| `agent/review_responder.py` | `agent/skills/review/responder.py` |
| `agent/utils/auth.py` | `agent/github/auth.py` |
| `agent/utils/github.py` | `agent/github/api.py` |
| `agent/utils/github_comments.py` | `agent/github/comments.py` |
| `agent/utils/repo.py` | `agent/github/repo.py` |
| `agent/utils/slack.py` | `agent/slack/client.py` |
| `agent/utils/sandbox.py` | `agent/sandbox/state.py` (base) |
| `agent/integrations/daytona.py` | `agent/sandbox/providers/daytona.py` |
| `agent/integrations/langsmith.py` | `agent/sandbox/providers/langsmith.py` |
| `agent/integrations/local.py` | `agent/sandbox/providers/local.py` |
| `agent/integrations/modal.py` | `agent/sandbox/providers/modal.py` |
| `agent/integrations/runloop.py` | `agent/sandbox/providers/runloop.py` |

### Merges (combine related files)

| Files | Into | What changes |
|-------|------|--------------|
| `utils/github_app.py` + `utils/github_token.py` | `github/app.py` | Combine encrypt/decrypt + token resolution |
| `utils/github_user_email_map.py` | `github/users.py` | Rename only |
| `utils/github_comments.py` + `utils/comments.py` | `github/comments.py` | Merge comment utilities |
| `utils/linear.py` + `utils/linear_team_repo_map.py` | `linear/client.py` | Merge Linear API + team mapping |
| `utils/sandbox.py` + `utils/sandbox_paths.py` + `utils/sandbox_state.py` | `sandbox/state.py` | Merge sandbox state management |

### Rewrites

| File | What changes |
|------|--------------|
| `agent/aap_config.py` → `agent/config/manifest.py` | Full rewrite using SDK v0.9.0 ManifestInstance |
| `agent/run_standalone.py` → `agent/runner/standalone.py` | Extract `_format_sizing_markdown` to `sizing_formatter.py` |

---

## config/manifest.py — SDK v0.9.0 Migration

### Before: aap_config.py (333 lines, 34 functions)

```python
# Example of the repetitive pattern (repeated 22 times):
def get_model_id():
    val = _artifact_value("open-swe.config.model")
    if val:
        return val
    return os.getenv("OPEN_SWE_MODEL", "anthropic:claude-opus-4-6")
```

### After: config/manifest.py (~50 lines)

SDK v0.9.0 now has all 6 convenience methods we requested. The `_artifact()`
and `_artifact_json()` helpers are no longer needed — the SDK handles
env fallback + default natively.

```python
"""Manifest-driven configuration using AAP SDK v0.9.0."""

from cockpit_aap import ManifestInstance

_instance: ManifestInstance | None = None


def _mi() -> ManifestInstance:
    global _instance
    if _instance is None:
        _instance = ManifestInstance("open-swe")
    return _instance


# ── Manifest ─────────────────────────────────
def get_manifest():
    return _mi().manifest

# ── Model ────────────────────────────────────
def get_model_config() -> dict:
    """Returns {model_id, temperature, max_tokens} from manifest + env."""
    return _mi().model_config(default_model="openai:gpt-4o")

def get_model_id() -> str:
    return get_model_config()["model_id"]

def get_model_temperature() -> float:
    return get_model_config()["temperature"]

def get_model_max_tokens() -> int:
    return get_model_config()["max_tokens"]

# ── Agent ────────────────────────────────────
def get_agent_instruction(agent_id: str = "swe-coder") -> str | None:
    return _mi().agent_instruction(agent_id)

# ── Skills ───────────────────────────────────
def get_skills():
    return _mi().skills()

def get_skill(skill_id: str):
    return _mi().skill(skill_id)

def get_skill_instruction(skill_id: str) -> str | None:
    return _mi().skill_instruction(skill_id)

# ── Rules ────────────────────────────────────
def get_rules():
    return _mi().rules()

# ── Guardrails ───────────────────────────────
def get_guardrails(phase: str | None = None):
    return _mi().guardrails(phase=phase)

# ── Config values ────────────────────────────
def get_recursion_limit() -> int:
    return int(_mi().artifact_value(
        "open-swe.config.recursion_limit",
        env_fallback="OPEN_SWE_RECURSION_LIMIT",
        default="1000",
    ))

def get_allowed_github_orgs() -> frozenset[str]:
    raw = _mi().artifact_value(
        "open-swe.config.allowed_github_orgs",
        env_fallback="ALLOWED_GITHUB_ORGS",
        default="",
    )
    return frozenset(o.strip().lower() for o in raw.split(",") if o.strip())

def get_sandbox_type() -> str:
    return _mi().artifact_value(
        "open-swe.config.sandbox_type",
        env_fallback="SANDBOX_TYPE",
        default="langsmith",
    )

def get_langgraph_url() -> str:
    return _mi().artifact_value(
        "open-swe.config.langgraph_url",
        env_fallback="LANGGRAPH_URL",
        default="http://localhost:2024",
    )

# ── Mappings ─────────────────────────────────
def get_linear_team_to_repo() -> dict:
    return _mi().artifact_json(
        "open-swe.mappings.linear_team_to_repo",
        env_fallback="LINEAR_TEAM_TO_REPO_JSON",
    )

def get_github_user_email_map() -> dict:
    return _mi().artifact_json(
        "open-swe.mappings.github_user_email",
        env_fallback="GITHUB_USER_EMAIL_MAP_JSON",
    )

# ── Telemetry ────────────────────────────────
def is_telemetry_enabled() -> bool:
    return _mi().is_telemetry_enabled()

def get_telemetry_service_name() -> str:
    return _mi().telemetry_service_name(default="open-swe")

# ── i18n ─────────────────────────────────────
def get_i18n_message(key: str, locale: str = "en", **kwargs) -> str:
    return _mi().localized_content("i18n", key, locale) or key

# ── Connections ──────────────────────────────
def get_connection_endpoint(connection_id: str) -> str | None:
    conn = _mi().connection(connection_id)
    return conn.endpoint if conn else None
```

**Result:** 333 lines → ~50 lines. 34 functions → 18 functions.
Zero custom helpers — every function is a direct SDK delegation.
The `_artifact()` and `_artifact_json()` helpers from v0.8.0 spec are gone
because SDK v0.9.0 now handles env fallback + default natively.

---

## runner/standalone.py — Extraction

The current `run_standalone.py` (567 lines) will be split:

| Extracted to | What | Lines |
|---|---|---|
| `runner/sizing_formatter.py` | `format_sizing_markdown()` function | ~110 |
| `runner/standalone.py` | Everything else (agent setup, invoke, report) | ~460 |

The `standalone.py` remains the entry point. No other structural changes — the
observability wiring, middleware setup, and execution report logic stay in place
since they're specific to the runner.

---

## Import Update Strategy

All internal imports use relative paths within `agent/`:

```python
# Before:
from agent.aap_config import get_model_id, get_manifest
from agent.review_poster import post_pr_review
from agent.utils.model import make_model

# After:
from agent.config import get_model_id, get_manifest
from agent.skills.review.poster import post_pr_review
from agent.config.model import make_model
```

The `config/__init__.py` re-exports all functions from `manifest.py` so existing
callers can do `from agent.config import get_model_id` (same interface, new path).

---

## Test Updates

Tests import from `agent.*` paths. All imports need updating:

| Test file | Imports to update |
|---|---|
| `test_skills.py` | `agent.aap_config` → `agent.config` |
| `test_migration_schemas.py` | `agent.schemas` → `agent.skills.schemas` |
| `test_review_poster.py` | `agent.review_poster` → `agent.skills.review.poster` |
| `test_review_responder.py` | `agent.review_responder` → `agent.skills.review.responder` |
| `test_repo_protection.py` | No change (middleware path unchanged) |
| `test_observability.py` | No change (observability path unchanged) |
| `test_sandbox_paths.py` | `agent.utils.sandbox_paths` → `agent.sandbox.state` |
| Others | Update as needed per move map |

---

## What Does NOT Change

These directories are already well-organized and stay as-is:

- `agent/middleware/` — 7 files, clear purpose
- `agent/observability/` — 5 files, clear purpose
- `agent/tools/` — 6 files, clear purpose
- `.aap/` — manifest structure
- `.github/workflows/` — CI/CD
- `tests/` — structure follows source (update imports only)
- `docs/` — design specs and plans

---

## Migration Order

1. **Create directory structure** — mkdir all new directories
2. **Move files** — git mv each file to new location
3. **Update imports** — fix all internal imports across the codebase
4. **Rewrite config/manifest.py** — replace aap_config.py with SDK v0.8.0
5. **Extract sizing_formatter.py** — split from run_standalone.py
6. **Create __init__.py files** — re-export for backwards compatibility
7. **Update tests** — fix test imports
8. **Run tests** — verify 182 tests still pass
9. **Run linter** — verify ruff clean
10. **Delete old files** — remove utils/, integrations/, aap_config.py, messages.py

Each step is a separate commit for easy review/revert.

---

## Success Criteria

1. All 182 tests pass
2. Ruff lint clean
3. `python agent/runner/standalone.py` works (with env vars)
4. No file in `agent/` root except `__init__.py`
5. Every directory has a clear, single purpose
6. `aap_config.py` is gone, replaced by ~80 lines using SDK v0.8.0
7. `utils/` directory is gone
8. `integrations/` directory is gone
