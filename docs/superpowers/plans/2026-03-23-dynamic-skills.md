# Dynamic Skills Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 manifest-driven skills (code-review, security-scan, doc-generator, test-generator) to the existing SWE agent so behavior changes dynamically based on context — zero Python per new skill.

**Architecture:** Skills are declared in `manifest.yaml` with instruction markdown files. The AAP SDK's `ManifestSkillAdapter` detects triggers and injects skill instructions into the agent's system prompt. GitHub Actions workflow routes events to the correct `SKILL_ID`.

**Tech Stack:** cockpit-aap-sdk 0.5.0, ManifestInstance, ManifestSkillAdapter, GitHub Actions, GitHub Reviews API

---

## File Structure

```
Modified:
  agent/aap_config.py              — add get_skills(), get_skill_adapter(), get_skill_instruction()
  agent/run_standalone.py           — accept SKILL_ID, skill-aware prompt + output routing
  .aap/open-swe/manifest.yaml      — add skills: section with 4 skills
  .github/workflows/agent.yml      — add PR review, doc-gen, test-gen, on-demand jobs
  test_mvp.py                       — extend with skill loading test

Created:
  .aap/open-swe/skills/code-review.md
  .aap/open-swe/skills/security-scan.md
  .aap/open-swe/skills/doc-generator.md
  .aap/open-swe/skills/test-generator.md
  agent/review_poster.py            — GitHub Reviews API integration (inline comments)
  tests/test_skills.py              — unit tests for skill adapter integration
```

---

## Chunk 1: Manifest Skills + Skill Instruction Files

### Task 1: Add skill instruction markdown files

**Files:**
- Create: `.aap/open-swe/skills/code-review.md`
- Create: `.aap/open-swe/skills/security-scan.md`
- Create: `.aap/open-swe/skills/doc-generator.md`
- Create: `.aap/open-swe/skills/test-generator.md`

- [ ] **Step 1: Create skills directory**

```bash
mkdir -p .aap/open-swe/skills
```

- [ ] **Step 2: Write code-review.md**

Create `.aap/open-swe/skills/code-review.md` with the code review skill prompt. The prompt must instruct the agent to:
- Read the PR diff (`git diff main...HEAD` or `git diff origin/main...HEAD`)
- Analyze for: bugs, logic errors, code smells, naming, standards adherence
- Output structured JSON with this exact format:

```json
{
  "skill_output_type": "review",
  "summary": "Short summary of findings",
  "score": "N/10",
  "comments": [
    {"file": "path/to/file.py", "line": 42, "message": "Description", "severity": "critical|high|medium|low"}
  ]
}
```

- Never suggest fixes (review only)
- Be constructive, not nitpicky
- Focus on real issues, not style preferences

- [ ] **Step 3: Write security-scan.md**

Create `.aap/open-swe/skills/security-scan.md`. Prompt must instruct agent to:
- Read the PR diff
- Check for: OWASP Top 10, hardcoded secrets, dependency CVEs, injection patterns, auth issues, insecure crypto
- Classify by severity (critical/high/medium/low)
- Output same structured JSON format with `"skill_output_type": "review"`

- [ ] **Step 4: Write doc-generator.md**

Create `.aap/open-swe/skills/doc-generator.md`. Prompt must instruct agent to:
- Analyze changed files (`git diff HEAD~1` for merge, or full repo scan on-demand)
- Identify functions/classes/modules without docstrings or docs
- Generate/update documentation (docstrings, README sections, docs/*.md)
- Commit changes and push to a new branch
- Output JSON with `"skill_output_type": "pr"`

- [ ] **Step 5: Write test-generator.md**

Create `.aap/open-swe/skills/test-generator.md`. Prompt must instruct agent to:
- Identify source files with no corresponding test file or low coverage
- Follow existing test patterns in the repo (detect pytest/jest/etc.)
- Generate tests that actually pass (run them before committing)
- Commit and push to new branch
- Output JSON with `"skill_output_type": "pr"`

- [ ] **Step 6: Commit**

```bash
git add .aap/open-swe/skills/
git commit -m "feat: add skill instruction files for 4 skills"
```

### Task 2: Add skills section to manifest.yaml

**Files:**
- Modify: `.aap/open-swe/manifest.yaml:21` (after agents section, before artifacts)

- [ ] **Step 1: Add skills section to manifest.yaml**

Add after the `agents:` section (after line 50, before `# ─── Artifacts`):

```yaml
  # ─── Skills ──────────────────────────────────────────────
  skills:
    - id: code-review
      name: Code Review
      description: Reviews PR diffs for bugs, logic errors, code smells, and standards adherence
      instruction: skills/code-review.md
      trigger: pull_request
      auto_invoke:
        triggers: ["review", "code review", "PR review", "review this"]

    - id: security-scan
      name: Security Scan
      description: Scans PR diffs for OWASP Top 10, hardcoded secrets, CVEs, and injection patterns
      instruction: skills/security-scan.md
      trigger: pull_request
      auto_invoke:
        triggers: ["security", "vulnerability", "CVE", "secrets", "security scan"]

    - id: doc-generator
      name: Doc Generator
      description: Generates and updates documentation for new or modified code
      instruction: skills/doc-generator.md
      trigger: push_main
      auto_invoke:
        triggers: ["docs", "documentation", "generate docs", "update docs"]

    - id: test-generator
      name: Test Generator
      description: Generates unit tests for code with low or no test coverage
      instruction: skills/test-generator.md
      trigger: label_needs_tests
      auto_invoke:
        triggers: ["tests", "test coverage", "generate tests", "needs-tests", "add tests"]
```

- [ ] **Step 2: Verify manifest loads with skills**

```bash
source .venv/bin/activate && python3 -c "
from cockpit_aap import ManifestInstance
mi = ManifestInstance('open-swe')
skills = mi.skills()
print(f'Skills loaded: {len(skills)}')
for s in skills:
    print(f'  - {s.id}: {s.name}')
"
```

Expected: 4 skills listed.

- [ ] **Step 3: Commit**

```bash
git add .aap/open-swe/manifest.yaml
git commit -m "feat: add 4 skills to manifest (code-review, security-scan, doc-gen, test-gen)"
```

---

## Chunk 2: Python Skill Integration (aap_config + run_standalone)

### Task 3: Add skill accessors to aap_config.py

**Files:**
- Modify: `agent/aap_config.py:266` (append after guardrails section)
- Test: `tests/test_skills.py`

- [ ] **Step 1: Write failing tests for skill accessors**

Create `tests/test_skills.py`:

```python
"""Tests for skill adapter integration."""

import pytest


def test_get_skills_returns_list():
    from agent.aap_config import get_skills
    skills = get_skills()
    assert isinstance(skills, list)


def test_get_skills_loads_4_skills():
    from agent.aap_config import get_skills, _load_manifest
    _load_manifest.cache_clear()
    skills = get_skills()
    assert len(skills) == 4
    ids = [s.id for s in skills]
    assert "code-review" in ids
    assert "security-scan" in ids
    assert "doc-generator" in ids
    assert "test-generator" in ids


def test_get_skill_by_id():
    from agent.aap_config import get_skill, _load_manifest
    _load_manifest.cache_clear()
    skill = get_skill("code-review")
    assert skill is not None
    assert skill.id == "code-review"
    assert skill.name == "Code Review"


def test_get_skill_unknown_returns_none():
    from agent.aap_config import get_skill
    assert get_skill("nonexistent-skill") is None


def test_get_skill_adapter_builds():
    from agent.aap_config import get_skill_adapter, _load_manifest
    _load_manifest.cache_clear()
    adapter = get_skill_adapter()
    assert adapter is not None
    assert hasattr(adapter, "detect_triggers")
    assert hasattr(adapter, "build_skill_system_prompt")


def test_skill_adapter_detects_review_trigger():
    from agent.aap_config import get_skill_adapter, _load_manifest
    _load_manifest.cache_clear()
    adapter = get_skill_adapter()
    activated = adapter.detect_triggers("please review this PR")
    ids = [s.id for s in activated]
    assert "code-review" in ids


def test_skill_adapter_detects_security_trigger():
    from agent.aap_config import get_skill_adapter, _load_manifest
    _load_manifest.cache_clear()
    adapter = get_skill_adapter()
    activated = adapter.detect_triggers("check for security vulnerabilities")
    ids = [s.id for s in activated]
    assert "security-scan" in ids


def test_get_skill_instruction_returns_content():
    from agent.aap_config import get_skill_instruction, _load_manifest
    _load_manifest.cache_clear()
    instruction = get_skill_instruction("code-review")
    assert instruction
    assert len(instruction) > 100  # non-trivial content
    assert "review" in instruction.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_skills.py -v 2>&1 | head -30
```

Expected: FAIL — `get_skills`, `get_skill`, `get_skill_adapter`, `get_skill_instruction` not defined.

- [ ] **Step 3: Implement skill accessors in aap_config.py**

Add to `agent/aap_config.py` after the guardrails section (after line 286):

```python
# ─── Skills ────────────────────────────────────────────────


def get_skills() -> list:
    """Get all skills from manifest."""
    mi = get_manifest()
    if mi is not None:
        try:
            return mi.skills()
        except Exception:
            logger.warning("Failed to load skills from manifest", exc_info=True)
    return []


def get_skill(skill_id: str):
    """Get a specific skill by ID."""
    mi = get_manifest()
    if mi is not None:
        try:
            return mi.skill(skill_id)
        except Exception:
            pass
    return None


def get_skill_instruction(skill_id: str) -> str:
    """Get the instruction content for a skill."""
    skill = get_skill(skill_id)
    if skill and skill.instruction:
        # ManifestInstance resolves file refs automatically
        if isinstance(skill.instruction, str):
            return skill.instruction
    return ""


def get_skill_adapter():
    """Create a ManifestSkillAdapter from manifest skills."""
    if not _HAS_AAP_SDK:
        return None
    try:
        from cockpit_aap import create_manifest_skill_adapter
        return create_manifest_skill_adapter(get_skills())
    except Exception:
        logger.warning("Failed to create skill adapter", exc_info=True)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_skills.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
source .venv/bin/activate && python -m pytest tests/ -q
```

Expected: 93+ passed (85 existing + 8 new), 0 failed.

- [ ] **Step 6: Commit**

```bash
git add agent/aap_config.py tests/test_skills.py
git commit -m "feat: add skill accessors and adapter to aap_config"
```

### Task 4: Create review_poster.py for GitHub Reviews API

**Files:**
- Create: `agent/review_poster.py`
- Test: `tests/test_review_poster.py`

- [ ] **Step 1: Write failing tests for review_poster**

Create `tests/test_review_poster.py`:

```python
"""Tests for GitHub Reviews API poster."""

import json
import pytest


def test_parse_review_output_valid_json():
    from agent.review_poster import parse_review_output
    raw = json.dumps({
        "skill_output_type": "review",
        "summary": "Found 1 issue",
        "score": "8/10",
        "comments": [
            {"file": "src/main.py", "line": 10, "message": "Bug here", "severity": "high"}
        ]
    })
    result = parse_review_output(raw)
    assert result is not None
    assert result["summary"] == "Found 1 issue"
    assert len(result["comments"]) == 1


def test_parse_review_output_no_json():
    from agent.review_poster import parse_review_output
    result = parse_review_output("Just a plain text response with no JSON")
    assert result is None


def test_parse_review_output_wrong_type():
    from agent.review_poster import parse_review_output
    raw = json.dumps({"skill_output_type": "pr", "summary": "test"})
    result = parse_review_output(raw)
    assert result is None


def test_format_review_summary():
    from agent.review_poster import format_review_summary
    review = {
        "summary": "Found 2 issues",
        "score": "7/10",
        "comments": [
            {"file": "a.py", "line": 1, "message": "Bug", "severity": "high"},
            {"file": "b.py", "line": 2, "message": "Style", "severity": "low"},
        ]
    }
    md = format_review_summary(review, "code-review")
    assert "### AAP Open SWE — Code Review" in md
    assert "7/10" in md
    assert "high" in md.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_review_poster.py -v 2>&1 | head -20
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement review_poster.py**

Create `agent/review_poster.py`:

```python
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
        review_comments.append({
            "path": c["file"],
            "line": c.get("line", 1),
            "body": f"**[{c.get('severity', 'info').upper()}]** {c['message']}",
        })

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_review_poster.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/review_poster.py tests/test_review_poster.py
git commit -m "feat: add review_poster for GitHub Reviews API inline comments"
```

### Task 5: Update run_standalone.py to support SKILL_ID

**Files:**
- Modify: `agent/run_standalone.py`

- [ ] **Step 1: Add SKILL_ID support to run_standalone.py**

Modify `agent/run_standalone.py` to:

1. Accept `SKILL_ID` env var (line ~30, in imports add `get_skill_instruction`, `get_skill_adapter`)
2. Accept `PR_NUMBER` env var (needed for review posting)
3. Build skill-aware system prompt (line ~51, after loading manifest_instruction)
4. Route output based on skill type (line ~108, after agent finishes)

Key changes:

**Imports (line ~22):** Add `get_skill_instruction, get_skill_adapter` to the import from `agent.aap_config`.

**After model creation (line ~48):** Add skill-aware prompt building:

```python
skill_id = os.environ.get("SKILL_ID", "")
pr_number = int(os.environ.get("PR_NUMBER", "0"))

# Build system prompt — skill overrides base if specified
if skill_id and skill_id not in ("swe-coder", ""):
    skill_instruction = get_skill_instruction(skill_id)
    if skill_instruction:
        system_prompt = skill_instruction.format(
            working_dir=repo_dir,
            repo_owner=repo_owner,
            repo_name=repo_name,
            pr_number=pr_number,
            issue_number=issue_number,
        )
    else:
        logger.warning("Skill %s not found, falling back to swe-coder", skill_id)
        # fall through to existing manifest_instruction logic
```

**After agent finishes (line ~108):** Add review posting for review-type skills:

```python
# Post review if skill is review-type
if skill_id in ("code-review", "security-scan") and pr_number:
    from agent.review_poster import parse_review_output, post_pr_review
    review = parse_review_output(agent_response)
    if review:
        post_pr_review(repo_owner, repo_name, pr_number, review, skill_id)
    else:
        logger.warning("Could not parse structured review from agent output")
```

- [ ] **Step 2: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -q
```

Expected: All tests pass (existing + new).

- [ ] **Step 3: Commit**

```bash
git add agent/run_standalone.py
git commit -m "feat: add SKILL_ID support to run_standalone for dynamic skill execution"
```

---

## Chunk 3: GitHub Actions Workflow

### Task 6: Add new workflow jobs for skills

**Files:**
- Modify: `.github/workflows/agent.yml`

- [ ] **Step 1: Add `pull_request` trigger to workflow `on:` section**

Add to the `on:` block at top of agent.yml:

```yaml
  pull_request:
    types: [opened, synchronize]
```

- [ ] **Step 2: Add `run-review` job**

Add new job that triggers on PRs, runs code-review + security-scan:

```yaml
  # ─── Trigger: PR opened/updated → code-review + security-scan ──
  run-review:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Setup uv
        uses: astral-sh/setup-uv@v4
      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv sync --all-extras
          uv pip install cockpit-aap-sdk
      - name: Run code review
        env:
          SKILL_ID: code-review
          TASK: "Review the PR diff and provide inline feedback"
          REPO_DIR: ${{ github.workspace }}
          REPO_OWNER: ${{ github.repository_owner }}
          REPO_NAME: ${{ github.event.repository.name }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          ISSUE_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPEN_SWE_MODEL: ${{ vars.OPEN_SWE_MODEL || 'anthropic:claude-sonnet-4-6' }}
          SANDBOX_TYPE: local
        run: |
          source .venv/bin/activate
          PYTHONPATH=. python agent/run_standalone.py
      - name: Run security scan
        env:
          SKILL_ID: security-scan
          TASK: "Scan the PR diff for security vulnerabilities"
          REPO_DIR: ${{ github.workspace }}
          REPO_OWNER: ${{ github.repository_owner }}
          REPO_NAME: ${{ github.event.repository.name }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          ISSUE_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPEN_SWE_MODEL: ${{ vars.OPEN_SWE_MODEL || 'anthropic:claude-sonnet-4-6' }}
          SANDBOX_TYPE: local
        run: |
          source .venv/bin/activate
          PYTHONPATH=. python agent/run_standalone.py
```

- [ ] **Step 3: Add `run-doc-gen` job**

Triggers when a PR is merged to main:

```yaml
  # ─── Trigger: PR merged to main → doc-generator ──
  run-doc-gen:
    if: |
      github.event_name == 'pull_request' &&
      github.event.action == 'closed' &&
      github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      # Same setup steps as above, then:
      - name: Run doc generator
        env:
          SKILL_ID: doc-generator
          TASK: "Analyze recent changes and generate/update documentation"
          # ... same env vars, OPEN_SWE_MODEL uses sonnet
        run: |
          source .venv/bin/activate
          PYTHONPATH=. python agent/run_standalone.py
      - name: Create Pull Request
        if: steps.agent.outputs.has_changes == 'true'
        # Same PR creation logic as existing jobs
```

Note: Add `closed` to `pull_request.types` in the `on:` trigger.

- [ ] **Step 4: Add `run-test-gen` job**

Triggers when label `needs-tests` is added to an issue:

```yaml
  # ─── Trigger: Label 'needs-tests' → test-generator ──
  run-test-gen:
    if: |
      github.event_name == 'issues' &&
      github.event.action == 'labeled' &&
      github.event.label.name == 'needs-tests'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      # Same setup, with SKILL_ID=test-generator
      # Same PR creation + comment logic as existing jobs
```

- [ ] **Step 5: Update on-demand comment handler to parse skill names**

Modify the existing `run-agent` job's "Build task" step to detect skill commands:

```javascript
// In the extract step script:
const comment = context.payload.comment.body;
const skillMatch = comment.match(/@aap-open-swe\s+(review|security|docs|tests)\b/i);
const skillMap = {
  'review': 'code-review',
  'security': 'security-scan',
  'docs': 'doc-generator',
  'tests': 'test-generator',
};
const skillId = skillMatch ? skillMap[skillMatch[1].toLowerCase()] || '' : '';
core.setOutput('skill_id', skillId);
```

Then pass `SKILL_ID: ${{ steps.extract.outputs.skill_id }}` to the agent run step.

- [ ] **Step 6: Lint check the workflow**

```bash
source .venv/bin/activate && python -c "import yaml; yaml.safe_load(open('.github/workflows/agent.yml'))" && echo "YAML valid"
```

Expected: "YAML valid"

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/agent.yml
git commit -m "feat: add workflow jobs for code-review, security-scan, doc-gen, test-gen skills"
```

---

## Chunk 4: Testing + Validation

### Task 7: Run full test suite and lint

- [ ] **Step 1: Run lint + format**

```bash
source .venv/bin/activate && uv run ruff check . && uv run ruff format --check . && echo "ALL CLEAN"
```

Fix any issues found.

- [ ] **Step 2: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -q
```

Expected: 93+ tests pass (85 existing + 8 skill tests + 4 review_poster tests), 0 failed.

- [ ] **Step 3: Verify skill loading end-to-end locally**

```bash
source .venv/bin/activate && python3 -c "
from agent.aap_config import get_skills, get_skill_adapter, get_skill_instruction, _load_manifest
_load_manifest.cache_clear()
skills = get_skills()
print(f'Skills: {len(skills)}')
for s in skills:
    instr = get_skill_instruction(s.id)
    print(f'  {s.id}: {len(instr)} chars instruction')
adapter = get_skill_adapter()
activated = adapter.detect_triggers('please review this PR for security issues')
print(f'Activated for review+security: {[s.id for s in activated]}')
"
```

Expected: 4 skills, each with instruction content, and both code-review + security-scan activated.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "fix: lint and test fixes for skills integration"
```

### Task 8: Push and test E2E

- [ ] **Step 1: Push to main**

```bash
git push
```

- [ ] **Step 2: Create a test PR to trigger code-review + security-scan**

```bash
git checkout -b test/skills-e2e
echo "# Test file for skills" > test_skills_e2e.py
git add test_skills_e2e.py
git commit -m "test: trigger skills E2E test"
git push -u origin test/skills-e2e
gh pr create --title "test: skills E2E validation" --body "Testing code-review and security-scan skills"
```

- [ ] **Step 3: Monitor workflow execution**

```bash
sleep 15 && gh run list --repo ruinosus/aap-open-swe --limit 3
```

Verify `run-review` job triggered and completed successfully.

- [ ] **Step 4: Check PR for inline review comments**

```bash
gh pr view <PR_NUMBER> --comments
```

Verify the agent posted inline review comments and a summary.

- [ ] **Step 5: Clean up test PR**

```bash
gh pr close <PR_NUMBER> --delete-branch
```

- [ ] **Step 6: Update manifest roadmap status**

Update `manifest.yaml` lifecycle section — change `aap-sdk-integration` status to `completed` and add skills entry.

- [ ] **Step 7: Final commit**

```bash
git add .aap/open-swe/manifest.yaml
git commit -m "feat: mark SDK integration complete, add skills to roadmap"
git push
```
