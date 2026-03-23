# Dynamic Skills Architecture — Design Spec

## Summary

Extend AAP Open SWE from a single-purpose coding agent to a **skill-driven agent** where
behavior is determined dynamically by the manifest. One agent (`swe-coder`) gains multiple
skills that activate based on GitHub event context, using the AAP SDK's `ManifestSkillAdapter`.

## Goals

- **Zero Python changes per new skill** — adding a skill = manifest entry + markdown file
- **Hybrid triggers** — automatic activation by event type + on-demand via `@aap-open-swe <skill>`
- **Appropriate outputs** — review skills comment inline; generative skills open draft PRs
- **Cost-efficient** — review/scan skills use Sonnet; implementation stays on Opus

## Skills (Phase 1)

| ID | Name | Auto Trigger | On-Demand Trigger | Output |
|----|------|-------------|-------------------|--------|
| `code-review` | Code Review | `pull_request` opened/synchronize | `@aap-open-swe review` | Inline PR comments + summary |
| `security-scan` | Security Scan | `pull_request` opened/synchronize | `@aap-open-swe security` | Inline PR comments + severity summary |
| `doc-generator` | Doc Generator | `push` to main (merge) | `@aap-open-swe docs` | Draft PR with doc changes |
| `test-generator` | Test Generator | label `needs-tests` | `@aap-open-swe tests` | Draft PR with new tests |

## Roadmap (Phase 2)

| ID | Name | Trigger |
|----|------|---------|
| `ci-fixer` | CI Fixer | `workflow_run` failure |
| `issue-triager` | Issue Triager | `issues` opened |

## Architecture

### Principle: 1 Agent, N Skills, Manifest-Driven

```
manifest.yaml
├── agents:
│   └── swe-coder (base agent — coding tasks)
├── skills:
│   ├── code-review
│   ├── security-scan
│   ├── doc-generator
│   └── test-generator
└── ManifestSkillAdapter detects context → injects skill instruction into prompt
```

### Event → Skill Resolution Flow

```
GitHub Event
    │
    ▼
.github/workflows/agent.yml
    │
    ├─ pull_request (opened/synchronize)
    │   → SKILL_ID=code-review,security-scan (automatic, both run)
    │
    ├─ push to main (closed + merged PR)
    │   → SKILL_ID=doc-generator (automatic)
    │
    ├─ issue_comment "@aap-open-swe <skill>"
    │   → SKILL_ID parsed from comment (on-demand)
    │
    ├─ issues (labeled needs-tests)
    │   → SKILL_ID=test-generator (automatic)
    │
    └─ issues (opened/assigned/labeled aap-open-swe) [existing]
        → SKILL_ID=swe-coder (default, existing behavior)
    │
    ▼
run_standalone.py receives SKILL_ID env var
    │
    ▼
aap_config.get_skill(skill_id) → loads skill from manifest
    │
    ▼
ManifestSkillAdapter.build_skill_system_prompt()
    │  injects skill instruction into agent's base prompt
    ▼
Agent executes with skill-specific behavior
    │
    ▼
Output depends on skill type:
    ├─ review/scan → GitHub Reviews API (inline comments + summary)
    └─ gen/test → git commit + push + draft PR + comment
```

### Skill Adapter Integration

The AAP SDK provides `create_manifest_skill_adapter()` which:

1. Takes a list of `ManifestSkill` from the manifest
2. Detects triggers by matching keywords in conversation/context text
3. Injects matched skill instructions into the system prompt
4. Returns the augmented prompt — agent behavior changes dynamically

```python
from cockpit_aap import create_manifest_skill_adapter

mi = ManifestInstance("open-swe")
adapter = create_manifest_skill_adapter(mi.skills())
system_prompt = adapter.build_skill_system_prompt(context_text, base_prompt)
```

## Manifest Changes

### New `skills:` section in manifest.yaml

```yaml
spec:
  skills:
    - id: code-review
      name: Code Review
      description: Reviews PR diffs for bugs, logic errors, code smells, and standards adherence
      instruction: skills/code-review.md
      trigger: pull_request
      auto_invoke:
        triggers: ["review", "code review", "PR review"]

    - id: security-scan
      name: Security Scan
      description: Scans PR diffs for OWASP Top 10, hardcoded secrets, CVEs, injection patterns
      instruction: skills/security-scan.md
      trigger: pull_request
      auto_invoke:
        triggers: ["security", "vulnerability", "CVE", "secrets"]

    - id: doc-generator
      name: Doc Generator
      description: Generates and updates documentation for new or modified code
      instruction: skills/doc-generator.md
      trigger: push_main
      auto_invoke:
        triggers: ["docs", "documentation", "generate docs"]

    - id: test-generator
      name: Test Generator
      description: Generates unit tests for code with low or no test coverage
      instruction: skills/test-generator.md
      trigger: label_needs_tests
      auto_invoke:
        triggers: ["tests", "test coverage", "generate tests", "needs-tests"]
```

### New skill instruction files

```
.aap/open-swe/
  skills/
    code-review.md        # ~2-3K chars, review-specific prompt
    security-scan.md      # ~2-3K chars, security-specific prompt
    doc-generator.md      # ~2-3K chars, doc generation prompt
    test-generator.md     # ~2-3K chars, test generation prompt
```

## Code Changes

### 1. `agent/aap_config.py` — Add skill accessors

```python
def get_skill(skill_id: str) -> "ManifestSkill | None":
    mi = get_manifest()
    if mi is not None:
        try:
            return mi.skill(skill_id)
        except Exception:
            pass
    return None

def get_skills() -> list:
    mi = get_manifest()
    if mi is not None:
        try:
            return mi.skills()
        except Exception:
            pass
    return []

def get_skill_adapter():
    from cockpit_aap import create_manifest_skill_adapter
    return create_manifest_skill_adapter(get_skills())
```

### 2. `agent/run_standalone.py` — Accept SKILL_ID, use skill adapter

```python
skill_id = os.environ.get("SKILL_ID", "")

# Load base prompt from agent
manifest_instruction = get_agent_instruction()

# If skill specified, inject skill instruction into prompt
if skill_id:
    adapter = get_skill_adapter()
    system_prompt = adapter.build_skill_system_prompt(skill_id, base_prompt)
else:
    system_prompt = base_prompt  # default swe-coder behavior
```

Also needs new output modes:
- **Review mode** (code-review, security-scan): uses GitHub API to post PR review comments
- **PR mode** (doc-generator, test-generator): commits + pushes + outputs for PR creation

### 3. `.github/workflows/agent.yml` — New trigger jobs

New jobs to add:

| Job | Trigger | SKILL_ID |
|-----|---------|----------|
| `run-review` | `pull_request: [opened, synchronize]` | `code-review,security-scan` |
| `run-doc-gen` | `pull_request: [closed]` + merged | `doc-generator` |
| `run-skill-ondemand` | `issue_comment` + `@aap-open-swe <skill>` | parsed from comment |
| `run-test-gen` | `issues: [labeled]` + `needs-tests` | `test-generator` |

### 4. GitHub API Integration for Review Comments

For code-review and security-scan skills, `run_standalone.py` needs to:

1. Parse agent output for structured review comments (file, line, message, severity)
2. Use GitHub Reviews API (`POST /repos/{owner}/{repo}/pulls/{pr}/reviews`) to create review
3. Post inline comments at specific diff lines
4. Post summary comment with overall assessment

Output format from agent (structured JSON):
```json
{
  "summary": "Found 3 issues: 1 bug, 1 security, 1 style",
  "score": "7/10",
  "comments": [
    {"file": "src/auth.py", "line": 42, "message": "SQL injection risk", "severity": "critical"},
    {"file": "src/utils.py", "line": 15, "message": "Unused variable", "severity": "low"}
  ]
}
```

## Model Strategy

| Context | Model | Reason |
|---------|-------|--------|
| `swe-coder` (implementation) | `anthropic:claude-opus-4-6` | Complex reasoning, multi-file changes |
| `code-review` | `anthropic:claude-sonnet-4-6` | Fast, accurate for review tasks |
| `security-scan` | `anthropic:claude-sonnet-4-6` | Fast, good pattern matching |
| `doc-generator` | `anthropic:claude-sonnet-4-6` | Fast, good at summarization |
| `test-generator` | `anthropic:claude-sonnet-4-6` | Fast, good at pattern matching |

Configurable per-skill via manifest — change one line in YAML to switch model.

## Testing Strategy

- **Unit tests**: test skill adapter integration, trigger detection, prompt injection
- **Integration test**: extend `test_mvp.py` to verify skill loading from manifest
- **E2E test**: create test PR in GitHub to verify code-review skill runs end-to-end

## Success Criteria

1. Adding a new skill requires ONLY: manifest entry + markdown file (zero Python)
2. Code-review skill posts inline comments on PRs automatically
3. Security-scan runs alongside code-review on every PR
4. Doc-generator creates draft PR on merge to main
5. Test-generator creates draft PR when label `needs-tests` is added
6. All existing 85 tests continue passing
7. On-demand invocation via `@aap-open-swe <skill>` works for all 4 skills
