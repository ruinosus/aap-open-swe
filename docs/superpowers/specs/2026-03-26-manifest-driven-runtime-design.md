# Manifest-Driven Agent Runtime — Design Spec

## Summary

Eliminate 80+ hardcoded values across 22 files by making the AAP manifest the
true single source of truth. Every string, template, skill routing rule, git
identity, emoji, and report format comes from the manifest or SDK — zero
hardcoded business logic in Python.

**Goal:** `agent/` contains only orchestration code. All behavior is declared
in `.aap/open-swe/manifest.yaml`.

**Scope:** Python agent code only. Workflow YAML reads from manifest outputs.

**Breaking:** No — external interfaces (issue comments, PRs, GH Actions) stay identical.

---

## Principles

1. **If it's a string the user sees, it's in the manifest** (i18n, templates, names)
2. **If it's a routing decision, it's in the manifest** (skill categories, branch patterns)
3. **If it's repeated in 2+ places, it's in the manifest** (git identity, namespace)
4. **Code reads, manifest declares** — Python never contains business policy

---

## Current Problems (80+ hardcoded values)

### 1. Skill routing scattered everywhere

```python
# runner/standalone.py
review_skills = ("code-review", "security-scan")          # line 227
pr_skills = ("doc-generator", "test-generator", ...)      # line 228
analysis_skills = ("aap-sizing",)                          # line 229
skill_branch_names = {"aap-sizing": "aap-migration/sizing", ...}  # line 341

# middleware/output_validator.py — SAME lists duplicated
review_skills = ("code-review", "security-scan")           # line 74

# observability/execution_report.py — SAME skills duplicated
skill_descriptions = {"code-review": "Review PR...", ...}  # line 122

# skills/schemas.py — SAME mapping
SKILL_SCHEMAS = {"code-review": ReviewOutput, ...}         # line 140
```

**Same skill IDs repeated in 9 files.** Adding a new skill requires editing all 9.

### 2. Report templates hardcoded in Python

```python
# execution_report.py
lines = ["## Agent Execution Report", "",
         f"**{status_icon} {status}** | **Duration:** {duration}...",
         "### Objective", f"> {objective}", ...]

# progress_reporter.py
lines = ["### Agent Execution\n", ...]

# sizing_formatter.py
lines.append("## 📊 AAP SDK Migration — Sizing Report")
```

Every report format is a Python string. Changing a header or adding a field
requires a code change + deploy.

### 3. Git identity in 3 places

```python
# runner/standalone.py:96
sandbox.execute("git config user.name 'aap-open-swe[bot]'")

# middleware/open_pr.py:137
backend.execute("git config user.name 'open-swe[bot]'")

# tools/commit_and_open_pr.py:165
backend.execute("git config user.name 'open-swe[bot]'")
```

Three different bot names across the codebase.

### 4. Namespace "open-swe" appears 20+ times

```python
# config/manifest.py
ManifestInstance("open-swe")
_mi().artifact_value("open-swe.config.model", ...)
_mi().artifact_value("open-swe.config.recursion_limit", ...)
# ... 20 more
```

---

## Solution: Manifest Extensions

### New manifest sections

```yaml
# .aap/open-swe/manifest.yaml
apiVersion: cockpit.io/v1
kind: Module
metadata:
  name: open-swe
  displayName: AAP Open SWE

spec:
  # ── Existing sections (already there) ─────
  agents: [...]
  skills: [...]
  artifacts: [...]
  connections: [...]
  rules: [...]
  i18n: { ... }
  theme: { ... }
  telemetry: { ... }

  # ── NEW: Skill routing metadata ───────────
  #
  # Each skill gets routing metadata that eliminates
  # hardcoded lists in Python.
  skills:
    - id: code-review
      name: Code Review
      description: "Reviews PRs with inline comments"
      instruction: skills/code-review.md
      category: review               # NEW: review | pr | analysis | migration
      output_format: structured       # NEW: structured | freeform
      branch_pattern: ""              # NEW: empty = no branch needed
      triggers:
        - "review"
        - "code review"

    - id: security-scan
      name: Security Scan
      description: "Scans for OWASP Top 10, secrets, injection"
      instruction: skills/security-scan.md
      category: review
      output_format: structured
      branch_pattern: ""

    - id: migrate-to-aap
      name: AAP Migration
      description: "Migrates repos to AAP SDK manifest architecture"
      instruction: skills/migrate-to-aap.md
      category: migration
      output_format: freeform
      branch_pattern: "aap-migration/full"

    - id: aap-sizing
      name: AAP Sizing
      description: "Analyzes repos for migration sizing"
      instruction: skills/aap-sizing.md
      category: analysis
      output_format: freeform
      branch_pattern: "aap-migration/sizing"

    - id: doc-generator
      name: Doc Generator
      description: "Generates project documentation"
      instruction: skills/doc-generator.md
      category: pr
      output_format: freeform
      branch_pattern: ""

    - id: test-generator
      name: Test Generator
      description: "Generates unit tests"
      instruction: skills/test-generator.md
      category: pr
      output_format: freeform
      branch_pattern: ""

    - id: project-docs
      name: Project Docs
      description: "Updates README and project docs"
      instruction: skills/project-docs.md
      category: pr
      output_format: freeform
      branch_pattern: ""

    - id: respond-review
      name: Respond to Review
      description: "Auto-replies to PR review comments"
      instruction: ""
      category: utility              # NEW: no agent needed
      output_format: none
      branch_pattern: ""

  # ── NEW: Git identity ────────────────────
  git:
    author_name: "aap-open-swe[bot]"
    author_email: "aap-open-swe@users.noreply.github.com"
    default_branch_pattern: "aap-open-swe/issue-{issue_number}"
    protected_branches:
      - main
      - master

  # ── NEW: Report templates (Handlebars) ───
  templates:
    execution_report: templates/execution-report.hbs
    progress_comment: templates/progress-comment.hbs
    sizing_report: templates/sizing-report.hbs
    review_summary: templates/review-summary.hbs
    pr_description: templates/pr-description.hbs

  # ── NEW: UI/formatting constants ──────────
  formatting:
    status_icons:
      success: "\u2705"
      failure: "\u274c"
      running: "\u23f3"
      pending: "\u2b1c"
    severity_icons:
      critical: "\U0001f534"
      high: "\U0001f534"
      medium: "\U0001f7e1"
      low: "\U0001f7e2"
    layer_icons:
      1: "\U0001f9f1"
      2: "\U0001f527"
      3: "\U0001f3a8"
      4: "\U0001f6e1"
      5: "\u2728"
      6: "\U0001f4bb"
```

### Handlebars templates

```handlebars
{{! .aap/open-swe/templates/execution-report.hbs }}

## Agent Execution Report

**{{status_icon}} {{status}}** | **Duration:** {{duration}} | **Cost:** {{cost}}

### Objective
> {{objective}}

### What was done
{{summary}}

{{#if guardrail_suggestions}}
**Suggested guardrails** ({{len guardrail_suggestions}}):
{{#each guardrail_suggestions}}
- `{{name}}` — {{description}} ({{phase}}/{{action}})
{{/each}}
{{/if}}

### Metrics
| Metric | Value |
|--------|-------|
| **Skill** | `{{skill_id}}` |
| **Model** | `{{model_id}}` |
{{#if llm_calls}}| LLM calls | {{llm_calls}} |{{/if}}
{{#if total_tokens}}| Input tokens | {{format_number input_tokens}} |
| Output tokens | {{format_number output_tokens}} |
| Total tokens | {{format_number total_tokens}} |{{/if}}
{{#if tool_calls}}| Tool calls | {{tool_calls}} |{{/if}}
| Duration | {{duration}} |
{{#if estimated_cost}}| **Estimated cost** | **{{cost}}** |{{/if}}

{{#if raw_output}}
<details>
<summary>Raw agent output</summary>

{{raw_output}}

</details>
{{/if}}
```

```handlebars
{{! .aap/open-swe/templates/sizing-report.hbs }}

## {{formatting.layer_icons.1}} AAP SDK Migration — Sizing Report

| Metric | Value |
|--------|-------|
| **Repository** | {{repo_url}} |
| **Type** | {{repo_type_label}} |
| **Languages** | {{join languages ", "}} |
| **Total Findings** | **{{total_findings}}** |

### Layers

| Layer | Name | Findings | Breaking? |
|-------|------|----------|-----------|
{{#each layers}}
| {{lookup ../formatting.layer_icons layer}} {{layer}} | **{{name}}** | {{count}} | {{#if is_breaking}}⚠️ Yes{{else}}✅ No{{/if}} |
{{/each}}

{{#if findings}}
<details>
<summary>📋 Detailed Findings ({{len findings}})</summary>

| # | Layer | Impact | File | Description |
|---|-------|--------|------|-------------|
{{#each findings}}
| {{@index}} | L{{layer}} | {{lookup ../formatting.severity_icons impact}} {{impact}} | `{{file}}` | {{truncate description 80}} |
{{/each}}

</details>
{{/if}}

### Next Steps

```
{{#each layers}}
{{#if applicable}}@aap-open-swe migrate --layer={{id}}        # {{lookup ../formatting.layer_icons layer}} {{#if is_breaking}}⚠️ BREAKING{{else}}Safe{{/if}}
{{/if}}
{{/each}}
```
```

### New config/manifest.py — reading skill metadata

```python
# Before: hardcoded in 9 files
review_skills = ("code-review", "security-scan")
pr_skills = ("doc-generator", "test-generator", "project-docs")

# After: from manifest
def get_skills_by_category(category: str) -> list:
    return [s for s in _mi().skills() if getattr(s, "category", "") == category]

def get_skill_branch(skill_id: str) -> str:
    skill = _mi().skill(skill_id)
    return getattr(skill, "branch_pattern", "") if skill else ""

def is_structured_output_skill(skill_id: str) -> bool:
    skill = _mi().skill(skill_id)
    return getattr(skill, "output_format", "") == "structured"

def get_git_identity() -> tuple[str, str]:
    git = _mi().manifest.spec.get("git", {})
    return (
        git.get("author_name", "open-swe[bot]"),
        git.get("author_email", "open-swe@users.noreply.github.com"),
    )
```

### New execution_report.py — template rendering

```python
# Before: 200+ lines of Python string formatting
lines = ["## Agent Execution Report", "", ...]

# After: ~20 lines — load template, render with context
from cockpit_aap.scribe import render_template  # or custom Handlebars

def build_execution_report(**kwargs) -> str:
    template = _mi().manifest.spec.templates.get("execution_report", "")
    if template:
        # Load .hbs file and render
        template_content = Path(template).read_text()
        return render_template(template_content, kwargs)
    # Fallback to simple format
    return _simple_report(**kwargs)
```

---

## What changes in code

### runner/standalone.py

| Before | After |
|--------|-------|
| `review_skills = ("code-review", "security-scan")` | `get_skills_by_category("review")` |
| `pr_skills = ("doc-generator", ...)` | `get_skills_by_category("pr")` |
| `skill_branch_names = {"aap-sizing": ...}` | `get_skill_branch(skill_id)` |
| `sandbox.execute("git config user.name 'aap-open-swe[bot]'")` | `name, email = get_git_identity()` |
| `if skill_id in ("code-review", "security-scan")` | `if is_structured_output_skill(skill_id)` |
| `if skill_id == "aap-sizing": format_sizing(...)` | `template = get_template("sizing_report")` |
| `if skill_id == "respond-review"` | `if skill.category == "utility"` |

### execution_report.py

| Before | After |
|--------|-------|
| 200+ lines of f-string formatting | Template file + render call |
| Hardcoded skill descriptions | `skill.description` from manifest |
| Hardcoded status icons | `formatting.status_icons` from manifest |

### sizing_formatter.py

| Before | After |
|--------|-------|
| 110 lines of emoji maps + formatting | Template file + render call |
| Hardcoded layer emoji | `formatting.layer_icons` from manifest |
| Hardcoded "@aap-open-swe" references | `metadata.name` from manifest |

### progress_reporter.py

| Before | After |
|--------|-------|
| Hardcoded "### Agent Execution" | Template from manifest |
| Hardcoded status icons | `formatting.status_icons` from manifest |

### skills/review/poster.py

| Before | After |
|--------|-------|
| `"Code Review" if ... else "Security Scan"` | `skill.name` from manifest |
| `f"### AAP Open SWE — {skill_name}"` | Template from manifest |

### middleware/output_validator.py

| Before | After |
|--------|-------|
| `review_skills = ("code-review", ...)` | `get_skills_by_category("review")` |

### All git operations (3 files)

| Before | After |
|--------|-------|
| `"aap-open-swe[bot]"` (3 different values!) | `get_git_identity()` (single source) |

---

## Implementation approach

### Phase 1: Manifest extensions (non-breaking)

1. Add `category`, `output_format`, `branch_pattern` to each skill in manifest
2. Add `spec.git` section
3. Add `spec.formatting` section with icons
4. Add `spec.templates` section pointing to .hbs files
5. Create .hbs template files in `.aap/open-swe/templates/`
6. Add helper functions to `config/manifest.py`

### Phase 2: Code migration (file by file)

For each hardcoded value:
1. Replace with manifest read
2. Run tests
3. Commit

Order: config helpers first, then runner, then execution_report, then
sizing_formatter, then progress_reporter, then review poster, then middleware.

### Phase 3: Template engine integration

1. Implement Handlebars rendering (use SDK's scribe or standalone lib)
2. Replace execution_report.py string formatting with template
3. Replace sizing_formatter.py with template
4. Replace progress comment with template
5. Replace review summary with template

---

## SDK features to leverage

| SDK Feature | How to use it | Replaces |
|---|---|---|
| `skill.category` (new field) | Classify skills without hardcoded lists | 4 hardcoded tuples |
| `mi.manifest.spec.git` | Single git identity config | 3 hardcoded bot names |
| `mi.manifest.spec.formatting` | Icons/emoji from manifest | 10+ hardcoded emoji maps |
| Handlebars templates | Report rendering | 400+ lines of f-strings |
| `mi.skill(id).name` | Display names from manifest | Hardcoded "Code Review" strings |
| `mi.skill(id).description` | Skill descriptions | Hardcoded description map |
| `rules_instruction_snippet()` | Auto-inject rules into prompts | Not used today |
| `create_middleware_stack()` | Auto-build middleware | Manual assembly |
| `create_langgraph_agent()` | Agent factory with HITL | 50+ lines of setup |
| `ConversationPort` | Persist conversations | Not used today |
| `CostEmitter/Enforcer` | Budget enforcement | Our custom cost tracking |

---

## SDK suggestions (for AAP SDK team)

### Needed for this feature

1. **`spec.skills[].category`** — New optional field for skill classification
   (review, pr, analysis, migration, utility). Currently not in the SDK schema.

2. **`spec.git`** — New optional section for git identity and branch patterns.
   Currently not in the SDK schema.

3. **`spec.templates`** — New optional section mapping template names to .hbs files.
   Currently not in the SDK schema.

4. **`spec.formatting`** — New optional section for UI constants (icons, colors).
   Currently not in the SDK schema.

5. **`skill.output_format`** — New optional field ("structured" | "freeform" | "none").
   Currently not in the SDK schema.

6. **`skill.branch_pattern`** — New optional field for VCS branch naming.
   Currently not in the SDK schema.

7. **Python Handlebars renderer** — The SDK has TypeScript templates
   (`@ruinosus/aap-templates`) but no Python equivalent. Need either:
   - Port the template engine to Python
   - Or add `pybars3` / `chevron` as a dependency

---

## Success criteria

1. Zero hardcoded skill IDs in Python (all from manifest)
2. Zero hardcoded report templates (all from .hbs files)
3. Zero hardcoded git identity (all from manifest)
4. Zero hardcoded emoji/icons (all from manifest)
5. Adding a new skill = 1 manifest entry + 1 instruction .md file (no Python changes)
6. Changing a report format = edit .hbs template (no Python changes)
7. All 182 tests pass
8. Existing issue comments / PR reviews look identical
