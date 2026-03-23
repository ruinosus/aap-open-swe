# AAP Open SWE — Architecture

## Overview

AAP Open SWE is an autonomous coding agent that runs entirely inside GitHub Actions.
When triggered, it reads the issue/PR context, clones the repository, makes code changes
using an LLM (GPT-4o, Claude, etc.), and opens a draft Pull Request — all without any
external server, ngrok tunnel, or cloud sandbox.

### Architecture Diagram

![Architecture](trigger-flow.drawio.png)

```
GitHub Event (issue/comment/label/assign)
    |
    v
.github/workflows/agent.yml          <-- GitHub Actions workflow
    |
    |-- 1. React with eyes emoji
    |-- 2. Checkout repository
    |-- 3. Install Python + uv + deps
    |-- 4. Extract task from issue/comment
    |-- 5. Run agent (agent/run_standalone.py)
    |       |
    |       |-- Load config from .aap/open-swe/manifest.yaml
    |       |-- Create LocalShellBackend (runner = sandbox)
    |       |-- Build system prompt from manifest
    |       |-- Invoke Deep Agent with LLM
    |       |-- Agent uses tools: execute, read_file, write_file, edit_file, grep, glob
    |       |-- Agent commits + pushes to branch
    |       |
    |-- 6. Create draft Pull Request (if changes)
    |-- 7. Comment on issue with results
```

## How It Was Built

### Step 1: Fork Open SWE

We started from [langchain-ai/open-swe](https://github.com/langchain-ai/open-swe), an open-source
framework for internal coding agents. It uses LangGraph + Deep Agents for the agent loop.

### Step 2: Integrate AAP SDK

We added manifest-driven configuration via the AAP SDK:

- **`.aap/open-swe/manifest.yaml`** — All config lives here (model, connections, rules, guardrails, telemetry, i18n)
- **`agent/aap_config.py`** — 34 typed accessor functions that read from the manifest with env var fallback
- **`agent/server.py`** — Modified to load model ID, temperature, max tokens, and system prompt from the manifest
- **`agent/webapp.py`** — Modified to load default repo, Slack config, and allowed orgs from the manifest

### Step 3: Create Standalone Runner

The original Open SWE requires a LangGraph server (`langgraph dev`). We created
`agent/run_standalone.py` that runs the Deep Agent directly — no server needed.
This is what GitHub Actions calls.

### Step 4: Create GitHub Actions Workflow

`.github/workflows/agent.yml` defines 8 trigger types — 5 for the base swe-coder agent
and 3 for dynamic skills (code-review, security-scan, doc-gen, test-gen, project-docs).

### Step 5: Add Dynamic Skills

We added a manifest-driven skill system where adding a new behavior requires zero Python:

- **`.aap/open-swe/skills/*.md`** — Skill instruction files (system prompts)
- **`agent/schemas.py`** — Pydantic schemas for structured JSON output
- **`agent/review_poster.py`** — GitHub Reviews API integration (inline PR comments)
- **`agent/aap_config.py`** — Added `get_skills()`, `get_skill_adapter()`, etc.
- **`agent/run_standalone.py`** — Added `SKILL_ID` env var + `response_format` for structured output

## Skills System

### 5 Built-in Skills

| Skill | Auto Trigger | On-Demand | Output |
|-------|-------------|-----------|--------|
| `code-review` | PR opened/synchronize | `@aap-open-swe review` | Inline PR comments + summary |
| `security-scan` | PR opened/synchronize | `@aap-open-swe security` | Inline PR comments + severity |
| `doc-generator` | PR merged to main | `@aap-open-swe docstrings` | Draft PR with docstrings |
| `test-generator` | Label `needs-tests` | `@aap-open-swe tests` | Draft PR with tests |
| `project-docs` | PR merged to main | `@aap-open-swe docs` | Draft PR with .md updates |

### How Skills Work

```
GitHub Event → agent.yml routes to SKILL_ID
    → run_standalone.py loads skill instruction from manifest
    → Pydantic schema sets response_format (ProviderStrategy)
    → Agent executes with skill-specific prompt
    → Output: structured JSON (100% reliable via constrained decoding)
    → Review skills → GitHub Reviews API (inline comments)
    → PR skills → git commit + push + draft PR
```

### Adding a New Skill

Zero Python required — only 2 files:

1. Create `.aap/open-swe/skills/my-skill.md` (instruction prompt)
2. Add entry to `manifest.yaml` under `skills:`
3. (Optional) Add workflow job to `agent.yml` for auto-trigger

## Trigger System

### 8 Ways to Trigger the Agent

| # | Trigger | GitHub Event | Example |
|---|---------|-------------|---------|
| 1 | **Comment mention** | `issue_comment.created` | Comment `@aap-open-swe fix this bug` on any issue |
| 2 | **Issue created** | `issues.opened` | Create issue with `@aap-open-swe` in title or body |
| 3 | **Issue assigned** | `issues.assigned` | Assign the issue to user `aap-open-swe` |
| 4 | **Label added** | `issues.labeled` | Add label `aap-open-swe` to any issue |
| 5 | **PR comment** | `issue_comment.created` | Comment `@aap-open-swe` on a Pull Request |
| 6 | **PR review** | `pull_request.opened/sync` | Automatic code-review + security-scan |
| 7 | **PR merged** | `pull_request.closed+merged` | Automatic doc-generator |
| 8 | **Label needs-tests** | `issues.labeled` | Add label `needs-tests` to trigger test-generator |

### How Each Trigger Works

**Trigger 1 — Comment Mention** (most common):
```
User comments on issue: "@aap-open-swe implement the feature described above"
  -> Workflow extracts: issue title + body + comment text
  -> Agent receives full context as task
  -> Agent makes changes, opens draft PR
  -> Agent comments on issue with PR link
```

**Trigger 2 — Issue Created**:
```
User creates issue: "Add dark mode support @aap-open-swe"
  -> Workflow detects @aap-open-swe in title or body
  -> Agent receives issue title + body as task
  -> Same flow: changes -> PR -> comment
```

**Trigger 3 — Issue Assigned**:
```
User assigns issue to "aap-open-swe" (GitHub user/bot)
  -> Workflow detects assignee matches
  -> Agent receives issue title + body as task
  -> Same flow: changes -> PR -> comment
```

**Trigger 4 — Label Added**:
```
User adds label "aap-open-swe" to any existing issue
  -> Workflow detects label name matches
  -> Agent receives issue title + body as task
  -> Same flow: changes -> PR -> comment
```

**Trigger 5 — PR Comment**:
```
User comments on PR: "@aap-open-swe fix the linting errors"
  -> Workflow checks out the PR branch (not main)
  -> Agent makes changes on the PR branch
  -> Pushes directly to the PR branch
  -> Comments on PR with summary
```

## Configuration Layer

### Priority Order

```
1. Manifest artifact value (if non-empty)
       |
       v  (empty? fallback)
2. Environment variable
       |
       v  (not set? fallback)
3. Hardcoded default
```

### Key Configuration Points

| Config | Manifest Key | Env Var | Default |
|--------|-------------|---------|---------|
| Model | `open-swe.config.model` | `OPEN_SWE_MODEL` | `anthropic:claude-opus-4-6` |
| Temperature | `open-swe.config.model_temperature` | `OPEN_SWE_MODEL_TEMPERATURE` | `0` |
| Max Tokens | `open-swe.config.model_max_tokens` | `OPEN_SWE_MODEL_MAX_TOKENS` | `20000` |
| Default Repo Owner | `open-swe.config.default_repo_owner` | `DEFAULT_REPO_OWNER` | `""` |
| Sandbox Type | `open-swe.config.sandbox_type` | `SANDBOX_TYPE` | `langsmith` |

### Manifest Structure

```
.aap/open-swe/
  manifest.yaml              # agents, skills, artifacts, connections, rules, guardrails, ...
  agents/
    swe-coder.md             # Base agent system prompt (10K+ chars)
  skills/
    code-review.md           # Code review skill instruction
    security-scan.md         # Security scan skill instruction
    doc-generator.md         # Doc generator skill instruction
    test-generator.md        # Test generator skill instruction
    project-docs.md          # Project docs updater skill instruction
  i18n/
    en.json                  # English (9 categories)
    pt-BR.json               # Portuguese
```

## Agent Runtime

### Deep Agent Pipeline

```
System Prompt (from manifest)
    + Task (from issue/comment)
    + Tools (execute, read_file, write_file, edit_file, ls, glob, grep, commit_and_open_pr, github_comment, ...)
    + LocalShellBackend (GitHub Actions runner)
    |
    v
Deep Agent Loop:
    1. LLM reads task and decides next action
    2. Calls tool (e.g., execute "grep -r TODO src/")
    3. Gets tool result
    4. Decides next action or finishes
    5. Repeat until task complete
    |
    v
Git Operations:
    1. git add -A
    2. git commit -m "fix: address issue #N"
    3. git checkout -b aap-open-swe/issue-N
    4. git push (using GITHUB_TOKEN)
```

### Rules (6 built-in)

| Rule | Enforcement | Description |
|------|------------|-------------|
| `max-pr-files` | warn | PR touches > 50 files |
| `no-force-push` | block | Force push not allowed |
| `test-before-pr` | block | Tests must pass first |
| `no-full-test-suite` | warn | Only run related tests |
| `max-file-size` | warn | Files > 500 KB |
| `no-backup-files` | block | No .bak files |

### Guardrails

**Manifest Guardrails** (4 built-in, in `manifest.yaml`):

| Type | Action | Pattern |
|------|--------|---------|
| Input | Block | Destructive commands (`rm -rf /`, `DROP TABLE`) |
| Input | Block | Unsafe execution (`curl \| sh`, `eval()`) |
| Output | Block | Credentials (`password=`, `api_key=`) |
| Output | Block | Cloud keys (`AKIA...`, `sk-...`, `ghp_...`) |

**Skill Middleware Guardrails** (3, in `agent/middleware/`):

| Guardrail | Type | What it does |
|-----------|------|-------------|
| `skill_file_scope` | `@before_model` | Blocks writes outside skill scope (review = read-only, project-docs = .md only) |
| `secret_filter` | `@after_agent` | Redacts API keys, tokens, passwords from agent output |
| `output_validator` | `@after_agent` | Validates JSON structure before posting to GitHub |

See [GUARDRAILS.md](GUARDRAILS.md) for full documentation, testing strategy, and how to create new guardrails.

## Setup Guide

### Prerequisites

- GitHub repository (public for free Actions)
- OpenAI or Anthropic API key

### 1. Install in Your Repo

Copy the workflow file to your repository:

```bash
mkdir -p .github/workflows
curl -o .github/workflows/agent.yml \
  https://raw.githubusercontent.com/ruinosus/aap-open-swe/main/.github/workflows/agent.yml
```

### 2. Configure Secrets

Go to **Settings > Secrets and variables > Actions** and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key |

*At least one is required.

### 3. Configure Variables

Go to **Settings > Secrets and variables > Actions > Variables** and add:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPEN_SWE_MODEL` | `openai:gpt-4o` | Model to use |

### 4. Enable Workflow Permissions

Go to **Settings > Actions > General > Workflow permissions**:
- Select "Read and write permissions"
- Check "Allow GitHub Actions to create and approve pull requests"

### 5. Create the Label (optional)

For label-based triggering, create a label named `aap-open-swe` in your repository:

```bash
gh label create aap-open-swe --color 8b5cf6 --description "Trigger AAP Open SWE agent"
```

### 6. Test It

```bash
# Create a test issue
gh issue create --title "Add hello.py" --body "Create a hello.py that prints 'Hello World'"

# Trigger the agent
gh issue comment 1 --body "@aap-open-swe please implement this"
```

## Files Reference

| File | Purpose |
|------|---------|
| `.github/workflows/agent.yml` | 8-trigger GitHub Actions workflow |
| `agent/run_standalone.py` | Standalone agent runner with SKILL_ID + structured output |
| `agent/aap_config.py` | Manifest config layer (34 functions, incl. skill accessors) |
| `agent/middleware/output_validator.py` | Validates structured JSON output for review/PR skills |
| `agent/middleware/secret_filter.py` | Redacts credentials and API keys from agent output |
| `agent/middleware/skill_file_scope.py` | Enforces per-skill file write restrictions |
| `agent/schemas.py` | Pydantic schemas for structured JSON output (ReviewOutput, PROutput) |
| `agent/review_poster.py` | GitHub Reviews API integration (inline PR comments) |
| `agent/server.py` | Deep Agent creation (model + prompt + tools) |
| `agent/webapp.py` | FastAPI webhooks (for LangGraph server mode) |
| `.aap/open-swe/manifest.yaml` | Module manifest (source of truth) |
| `.aap/open-swe/agents/swe-coder.md` | Base agent system prompt |
| `.aap/open-swe/skills/*.md` | 5 skill instruction files |
| `.aap/open-swe/i18n/en.json` | English messages |
| `.aap/open-swe/i18n/pt-BR.json` | Portuguese messages |
| `test_mvp.py` | 4-stage integration test |
| `tests/test_skills.py` | Skill adapter integration tests |
| `tests/test_review_poster.py` | Review poster unit tests |
