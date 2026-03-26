# Codebase Reorganization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `agent/` from a flat dump into a layered feature-first structure, and migrate `aap_config.py` to AAP SDK v0.9.0.

**Architecture:** Three layers — entry points (runner/, server/), core (config/, skills/, middleware/, observability/), adapters (github/, slack/, linear/, sandbox/, tools/). Each move is a git mv + import fix. Tests must pass after every task.

**Tech Stack:** Python 3.12, cockpit-aap-sdk v0.9.0, pytest, ruff

**Spec:** `docs/superpowers/specs/2026-03-25-codebase-reorganization-design.md`

---

## Strategy

The safest way to refactor imports without breaking everything is:

1. **Create new directory + `__init__.py` with re-exports**
2. **`git mv` files to new locations**
3. **Update imports in moved files** (internal references)
4. **Update imports in consumers** (tests, other modules)
5. **Run tests after each task**
6. **Delete old directories only after everything passes**

Each task moves one logical group of files. Tasks are ordered so no task depends on a later task.

---

## Chunk 1: Foundation — Create directory structure + config migration

### Task 1: Create directory structure

**Files:**
- Create: `agent/runner/__init__.py`
- Create: `agent/server/__init__.py`
- Create: `agent/config/__init__.py`
- Create: `agent/skills/__init__.py`
- Create: `agent/skills/review/__init__.py`
- Create: `agent/github/__init__.py`
- Create: `agent/slack/__init__.py`
- Create: `agent/linear/__init__.py`
- Create: `agent/sandbox/__init__.py`
- Create: `agent/sandbox/providers/__init__.py`

- [ ] **Step 1: Create all directories with empty __init__.py**

```bash
mkdir -p agent/runner agent/server agent/config agent/skills/review agent/github agent/slack agent/linear agent/sandbox/providers

for dir in agent/runner agent/server agent/config agent/skills agent/skills/review agent/github agent/slack agent/linear agent/sandbox agent/sandbox/providers; do
  touch "$dir/__init__.py"
done
```

- [ ] **Step 2: Run tests to verify nothing broke**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 182 passed

- [ ] **Step 3: Commit**

```bash
git add agent/runner agent/server agent/config agent/skills agent/github agent/slack agent/linear agent/sandbox
git commit -m "chore: create directory structure for reorganization"
```

---

### Task 2: Migrate aap_config.py to config/manifest.py (SDK v0.9.0)

**Files:**
- Create: `agent/config/manifest.py`
- Modify: `agent/config/__init__.py`
- Modify: `agent/utils/model.py` → copy to `agent/config/model.py`
- Test: `tests/test_skills.py` (update imports)

- [ ] **Step 1: Bump cockpit-aap-sdk to v0.9.0**

```bash
# In pyproject.toml, update the dependency
sed -i '' 's/cockpit-aap-sdk>=0.6.0/cockpit-aap-sdk>=0.9.0/' pyproject.toml 2>/dev/null || \
sed -i 's/cockpit-aap-sdk>=0.6.0/cockpit-aap-sdk>=0.9.0/' pyproject.toml
```

If the dependency is in requirements.txt instead:
```bash
sed -i '' 's/cockpit-aap-sdk>=0.6.0/cockpit-aap-sdk>=0.9.0/' requirements.txt 2>/dev/null || true
```

- [ ] **Step 2: Create config/manifest.py**

Write `agent/config/manifest.py` with the SDK v0.9.0 code from the spec. This file replaces `aap_config.py` with ~50 lines using direct SDK delegation.

- [ ] **Step 3: Copy model.py to config/**

```bash
cp agent/utils/model.py agent/config/model.py
```

- [ ] **Step 4: Create config/__init__.py with re-exports**

```python
# agent/config/__init__.py
from .manifest import (
    get_agent_instruction,
    get_allowed_github_orgs,
    get_connection_endpoint,
    get_github_user_email_map,
    get_guardrails,
    get_i18n_message,
    get_langgraph_url,
    get_linear_team_to_repo,
    get_manifest,
    get_model_config,
    get_model_id,
    get_model_max_tokens,
    get_model_temperature,
    get_recursion_limit,
    get_rules,
    get_sandbox_type,
    get_skill,
    get_skill_instruction,
    get_skills,
    get_telemetry_service_name,
    is_telemetry_enabled,
)
from .model import make_model
```

- [ ] **Step 5: Update all imports from `agent.aap_config` to `agent.config`**

Search and replace across all files:
```bash
grep -rn "from agent.aap_config" agent/ tests/ --include="*.py"
```

For each match, change `from agent.aap_config import X` to `from agent.config import X`.

Also update `from agent.utils.model import make_model` to `from agent.config import make_model`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 182 passed

- [ ] **Step 7: Run linter**

Run: `uv run ruff check . && uv run ruff format --check .`

- [ ] **Step 8: Commit**

```bash
git add agent/config/ pyproject.toml requirements.txt
git add -u  # captures modified files
git commit -m "feat: migrate aap_config to config/manifest.py (SDK v0.9.0)"
```

---

## Chunk 2: Move entry points

### Task 3: Move run_standalone.py to runner/

**Files:**
- Move: `agent/run_standalone.py` → `agent/runner/standalone.py`
- Create: `agent/runner/sizing_formatter.py`
- Modify: `.github/workflows/agent.yml` (update PYTHONPATH entry point)

- [ ] **Step 1: Extract sizing_formatter.py**

Read `agent/run_standalone.py`, copy the `_format_sizing_markdown()` function (lines 17-123) to `agent/runner/sizing_formatter.py`:

```python
# agent/runner/sizing_formatter.py
"""Format sizing JSON output as rich markdown for GitHub issue comments."""
import json

def format_sizing_markdown(agent_response: str) -> str:
    # ... (the existing function, renamed without underscore)
```

- [ ] **Step 2: Move run_standalone.py**

```bash
git mv agent/run_standalone.py agent/runner/standalone.py
```

- [ ] **Step 3: Update standalone.py**

In `agent/runner/standalone.py`:
- Replace `_format_sizing_markdown` call with import from `agent.runner.sizing_formatter`
- Delete the `_format_sizing_markdown` function body
- Update any relative imports

- [ ] **Step 4: Update runner/__init__.py**

```python
# agent/runner/__init__.py
from .standalone import main, run_agent
```

- [ ] **Step 5: Update workflow YAML**

In `.github/workflows/agent.yml`, every `python agent/run_standalone.py` becomes `python -m agent.runner.standalone`.

Search for all occurrences:
```bash
grep -n "run_standalone" .github/workflows/agent.yml
```

Replace each with `python -m agent.runner.standalone`.

- [ ] **Step 6: Update Makefile if needed**

```bash
grep -n "run_standalone" Makefile
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 182 passed

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move run_standalone.py to runner/standalone.py"
```

---

### Task 4: Move webapp + server files to server/

**Files:**
- Move: `agent/webapp.py` → `agent/server/webapp.py`
- Move: `agent/server.py` → `agent/server/graph.py`
- Move: `agent/prompt.py` → `agent/server/prompt.py`
- Move: `agent/encryption.py` → `agent/server/encryption.py`

- [ ] **Step 1: Move files**

```bash
git mv agent/webapp.py agent/server/webapp.py
git mv agent/server.py agent/server/graph.py
git mv agent/prompt.py agent/server/prompt.py
git mv agent/encryption.py agent/server/encryption.py
```

- [ ] **Step 2: Update internal imports in moved files**

In each moved file, update imports like:
- `from agent.prompt import X` → `from agent.server.prompt import X`
- `from agent.encryption import X` → `from agent.server.encryption import X`
- `from agent.server import X` → `from agent.server.graph import X`

- [ ] **Step 3: Update langgraph.json if it exists**

```bash
grep -rn "agent/server" langgraph.json 2>/dev/null || echo "No langgraph.json"
```

Update graph path reference if needed.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 182 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move webapp + server files to server/"
```

---

## Chunk 3: Move core modules

### Task 5: Move skills (schemas, review)

**Files:**
- Move: `agent/schemas.py` → `agent/skills/schemas.py`
- Move: `agent/review_poster.py` → `agent/skills/review/poster.py`
- Move: `agent/review_responder.py` → `agent/skills/review/responder.py`

- [ ] **Step 1: Move files**

```bash
git mv agent/schemas.py agent/skills/schemas.py
git mv agent/review_poster.py agent/skills/review/poster.py
git mv agent/review_responder.py agent/skills/review/responder.py
```

- [ ] **Step 2: Create skills __init__.py re-exports**

```python
# agent/skills/__init__.py
from .schemas import SKILL_SCHEMAS, ReviewOutput, MigrationOutput, SizingOutput, PROutput
```

```python
# agent/skills/review/__init__.py
from .poster import post_pr_review, parse_review_output
from .responder import respond_to_review
```

- [ ] **Step 3: Update imports in consumers**

```bash
grep -rn "from agent.schemas import\|from agent.review_poster import\|from agent.review_responder import" agent/ tests/ --include="*.py"
```

Update each:
- `from agent.schemas import X` → `from agent.skills.schemas import X`
- `from agent.review_poster import X` → `from agent.skills.review.poster import X`
- `from agent.review_responder import X` → `from agent.skills.review.responder import X`

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 182 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move schemas + review to skills/"
```

---

## Chunk 4: Move adapters

### Task 6: Move GitHub utilities

**Files:**
- Move: `agent/utils/auth.py` → `agent/github/auth.py`
- Move: `agent/utils/github.py` → `agent/github/api.py`
- Move: `agent/utils/github_comments.py` → `agent/github/comments.py`
- Merge: `agent/utils/github_app.py` + `agent/utils/github_token.py` → `agent/github/app.py`
- Move: `agent/utils/github_user_email_map.py` → `agent/github/users.py`
- Move: `agent/utils/repo.py` → `agent/github/repo.py`
- Merge: `agent/utils/comments.py` into `agent/github/comments.py`

- [ ] **Step 1: Move simple files**

```bash
git mv agent/utils/auth.py agent/github/auth.py
git mv agent/utils/github.py agent/github/api.py
git mv agent/utils/github_comments.py agent/github/comments.py
git mv agent/utils/github_user_email_map.py agent/github/users.py
git mv agent/utils/repo.py agent/github/repo.py
```

- [ ] **Step 2: Merge github_app.py + github_token.py into github/app.py**

Read both files, combine into `agent/github/app.py`. Delete originals:
```bash
git rm agent/utils/github_app.py agent/utils/github_token.py
```

- [ ] **Step 3: Merge comments.py into github/comments.py**

Append contents of `agent/utils/comments.py` to `agent/github/comments.py`. Delete original:
```bash
git rm agent/utils/comments.py
```

- [ ] **Step 4: Create github/__init__.py**

```python
# agent/github/__init__.py
# Re-exports for backward compatibility
```

- [ ] **Step 5: Update all imports**

```bash
grep -rn "from agent.utils.auth\|from agent.utils.github\|from agent.utils.comments\|from agent.utils.repo" agent/ tests/ --include="*.py"
```

Update each to the new `agent.github.*` path.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 182 passed

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: consolidate GitHub utilities into github/"
```

---

### Task 7: Move Slack, Linear, Sandbox adapters

**Files:**
- Move: `agent/utils/slack.py` → `agent/slack/client.py`
- Merge: `agent/utils/linear.py` + `agent/utils/linear_team_repo_map.py` → `agent/linear/client.py`
- Merge: `agent/utils/sandbox.py` + `agent/utils/sandbox_paths.py` + `agent/utils/sandbox_state.py` → `agent/sandbox/state.py`
- Move: `agent/integrations/*.py` → `agent/sandbox/providers/*.py`

- [ ] **Step 1: Move Slack**

```bash
git mv agent/utils/slack.py agent/slack/client.py
```

- [ ] **Step 2: Merge Linear files**

Read `agent/utils/linear.py` and `agent/utils/linear_team_repo_map.py`, combine into `agent/linear/client.py`. Delete originals:
```bash
git rm agent/utils/linear.py agent/utils/linear_team_repo_map.py
```

- [ ] **Step 3: Merge Sandbox files**

Read `agent/utils/sandbox.py`, `agent/utils/sandbox_paths.py`, `agent/utils/sandbox_state.py`, combine into `agent/sandbox/state.py`. Delete originals:
```bash
git rm agent/utils/sandbox.py agent/utils/sandbox_paths.py agent/utils/sandbox_state.py
```

- [ ] **Step 4: Move integrations to sandbox/providers**

```bash
git mv agent/integrations/daytona.py agent/sandbox/providers/daytona.py
git mv agent/integrations/langsmith.py agent/sandbox/providers/langsmith.py
git mv agent/integrations/local.py agent/sandbox/providers/local.py
git mv agent/integrations/modal.py agent/sandbox/providers/modal.py
git mv agent/integrations/runloop.py agent/sandbox/providers/runloop.py
git rm agent/integrations/__init__.py
```

- [ ] **Step 5: Move remaining server-only utils**

```bash
git mv agent/utils/agents_md.py agent/server/agents_md.py
git mv agent/utils/multimodal.py agent/server/multimodal.py
git mv agent/utils/langsmith.py agent/server/langsmith.py
```

- [ ] **Step 6: Update all imports across codebase**

```bash
grep -rn "from agent.utils\.\|from agent.integrations\." agent/ tests/ --include="*.py"
```

Update each to the new path.

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -q`
Expected: 182 passed

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move Slack, Linear, Sandbox adapters to dedicated packages"
```

---

## Chunk 5: Cleanup

### Task 8: Delete old directories and dead code

**Files:**
- Delete: `agent/utils/` (should be empty now)
- Delete: `agent/integrations/` (should be empty now)
- Delete: `agent/aap_config.py` (replaced by config/manifest.py)
- Delete: `agent/utils/messages.py` (dead code — already moved/deleted with utils)

- [ ] **Step 1: Verify utils/ is empty**

```bash
ls agent/utils/
```

Should show only `__init__.py` and `model.py` (if not yet deleted). Delete the directory:

```bash
git rm -r agent/utils/
```

- [ ] **Step 2: Verify integrations/ is empty**

```bash
ls agent/integrations/
```

Should be empty. Delete:

```bash
git rm -r agent/integrations/
```

- [ ] **Step 3: Delete old aap_config.py**

```bash
git rm agent/aap_config.py
```

- [ ] **Step 4: Verify no imports reference old paths**

```bash
grep -rn "from agent.utils\.\|from agent.aap_config\|from agent.integrations\.\|from agent.server import\|from agent.run_standalone\|from agent.schemas\|from agent.review_poster\|from agent.review_responder\|from agent.prompt\|from agent.encryption\|from agent.webapp" agent/ tests/ --include="*.py"
```

Expected: no matches (or only within `__init__.py` re-exports).

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -v`
Expected: 182 passed

- [ ] **Step 6: Run linter**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: All checks passed

- [ ] **Step 7: Verify no file in agent/ root except __init__.py**

```bash
ls agent/*.py
```

Expected: only `agent/__init__.py`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: delete old utils/, integrations/, aap_config.py"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ --ignore=tests/test_guardrails_e2e.py -v`
Expected: 182 passed

- [ ] **Step 2: Run linter**

Run: `uv run ruff check . && uv run ruff format .`
Expected: clean

- [ ] **Step 3: Verify structure matches spec**

```bash
find agent/ -type f -name "*.py" | sort
```

Compare with the target structure in the spec.

- [ ] **Step 4: Verify imports work end-to-end**

```bash
uv run python3 -c "
from agent.config import get_model_id, get_manifest, get_skill_instruction, make_model
from agent.skills.schemas import SKILL_SCHEMAS, ReviewOutput
from agent.skills.review.poster import post_pr_review
from agent.skills.review.responder import respond_to_review
from agent.observability import build_execution_report, gh_group, ProgressReporter
from agent.middleware import ensure_no_empty_msg
print('All imports OK')
"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "refactor: complete codebase reorganization"
```
