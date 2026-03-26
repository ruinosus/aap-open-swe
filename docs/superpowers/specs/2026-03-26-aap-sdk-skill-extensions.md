# AAP SDK — Skill Schema Extensions Request

**From:** aap-open-swe team
**SDK Version:** v0.9.0 (Python)
**Date:** 2026-03-26
**Priority:** High — blocks manifest-driven runtime feature

---

## Problem

`ManifestSkill` in the Python SDK discards unknown fields during parsing.
We added custom fields (`category`, `outputFormat`, `branchPattern`) to our
manifest YAML but they're silently dropped by the SDK type parser.

```yaml
# Our manifest.yaml
skills:
  - id: code-review
    name: Code Review
    category: review           # ← DROPPED by SDK
    outputFormat: structured   # ← DROPPED by SDK
    branchPattern: ""          # ← DROPPED by SDK
```

```python
skill = mi.skill("code-review")
skill.category       # AttributeError — field doesn't exist
skill.outputFormat   # AttributeError — field doesn't exist
```

This forces us to either:
- Read YAML directly (wrong — bypasses ManifestInstance)
- Hardcode routing logic in Python (what we're trying to eliminate)

---

## Requested Changes

### Option A: Add fields to ManifestSkill (preferred)

Add these fields to `ManifestSkill` in `cockpit_aap/manifest/types.py`:

```python
@dataclass
class ManifestSkill:
    id: str
    name: str
    description: str
    instruction: str
    # ... existing fields ...

    # NEW — Skill routing metadata
    category: str = ""          # review | pr | analysis | migration | utility
    outputFormat: str = "freeform"  # structured | freeform | none
    branchPattern: str = ""     # Git branch pattern for this skill's output
```

**Rationale:** These are generic enough to benefit all SDK consumers:
- `category` — every app needs to classify skills for routing
- `outputFormat` — determines if the skill uses structured output or tool calling
- `branchPattern` — VCS integration is common for coding agents

### Option B: Support extra fields passthrough

If adding specific fields is too opinionated, support `**extra` on all
manifest types:

```python
@dataclass
class ManifestSkill:
    # ... existing fields ...
    extra: dict = field(default_factory=dict)  # All unknown YAML fields
```

Then:
```python
skill = mi.skill("code-review")
skill.extra["category"]      # "review"
skill.extra["outputFormat"]   # "structured"
```

This is less clean but more flexible — any consumer can add custom fields
without SDK changes.

### Option C: Use artifacts for custom metadata

Store skill metadata as artifacts:

```yaml
artifacts:
  - key: open-swe.skills.code-review.category
    defaultValue: review
  - key: open-swe.skills.code-review.outputFormat
    defaultValue: structured
```

Then: `mi.artifact_value("open-swe.skills.code-review.category")`

**Problem:** This duplicates the skill ID in artifact keys and doesn't
scale well (2 artifacts per field per skill = 14+ artifacts for 7 skills).

---

## Also Requested

### 1. `spec.git` section support

```yaml
spec:
  git:
    authorName: "bot-name[bot]"
    authorEmail: "bot@users.noreply.github.com"
    defaultBranchPattern: "bot/issue-{issue_number}"
    protectedBranches: [main, master]
```

Currently not in the SDK schema. Every coding agent needs git identity config.

### 2. `spec.formatting` section support

```yaml
spec:
  formatting:
    statusIcons:
      success: "✅"
      failure: "❌"
      running: "⏳"
      pending: "⬜"
    severityIcons:
      critical: "🔴"
      high: "🔴"
      medium: "🟡"
      low: "🟢"
    layerIcons:
      1: "🧱"
      2: "🔧"
```

Currently not in the SDK schema. Used for reports and UI rendering.

### 3. `spec.templates` section support

```yaml
spec:
  templates:
    executionReport: templates/execution-report.hbs
    sizingReport: templates/sizing-report.hbs
    reviewSummary: templates/review-summary.hbs
```

Currently not in the SDK schema. Points to template files in the manifest
directory.

---

## Workaround We're Using

Until the SDK supports these fields, we use the artifact system as a
compatibility shim:

```python
# Instead of: skill.category
# We use: artifact with skill-id prefix
def get_skill_category(skill_id):
    return mi.artifact_value(f"open-swe.skills.{skill_id}.category")
```

This works but is ugly and requires maintaining artifact entries alongside
skill definitions.

---

## Impact

Without these changes, the aap-open-swe agent cannot achieve
"manifest as single source of truth" — skill routing, report formatting,
and git identity remain partially hardcoded in Python.
