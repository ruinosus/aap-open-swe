# AAP SDK Migration Skills Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 2 skills (`aap-sizing` + `migrate-to-aap`) that analyze external repos and migrate them to AAP SDK manifest-driven architecture in 5 incremental layers.

**Architecture:** Skills are markdown instruction files + manifest entries. The sizing skill is read-only (analysis + report). The migration skill executes changes per layer, each as a separate PR. Both use the existing `run_standalone.py` pipeline with guardrails.

**Tech Stack:** cockpit-aap-sdk 0.6.0, Pydantic schemas, GitHub Actions, Python + TypeScript pattern matching

---

## File Structure

```
Created:
  .aap/open-swe/skills/aap-sizing.md           — sizing skill instruction (read-only analysis)
  .aap/open-swe/skills/migrate-to-aap.md        — migration skill instruction (5 layers)
  .aap/sizing-read-only/manifest.yaml            — guardrail: sizing cannot modify files
  agent/schemas.py                                — add SizingFinding, SizingOutput, MigrationOutput
  tests/test_migration_schemas.py                 — schema validation tests

Modified:
  .aap/open-swe/manifest.yaml                    — add 2 skills (aap-sizing, migrate-to-aap)
  agent/schemas.py                                — append new schemas + update SKILL_SCHEMAS
  .github/workflows/agent.yml                     — add sizing/migrate to skill command regex
  tests/test_skills.py                            — update skill count from 5 to 7
```

---

## Chunk 1: Schemas + Manifest Entries

### Task 1: Add Pydantic schemas for sizing and migration output

**Files:**
- Modify: `agent/schemas.py` (append after SKILL_SCHEMAS)
- Create: `tests/test_migration_schemas.py`

- [ ] **Step 1: Write failing tests for new schemas**

Create `tests/test_migration_schemas.py`:

```python
"""Tests for migration skill schemas."""

from agent.schemas import SizingFinding, SizingLayerSummary, SizingOutput, MigrationOutput


def test_sizing_finding_valid():
    f = SizingFinding(
        layer=1,
        category="prompt",
        file="apps/agent/src/agent.py",
        line=15,
        description="SYSTEM_PROMPT (2.3K chars)",
        impact="high",
        code_snippet="SYSTEM_PROMPT = \"\"\"You are...",
        language="python",
    )
    assert f.layer == 1
    assert f.impact == "high"


def test_sizing_layer_summary():
    s = SizingLayerSummary(
        layer=1,
        name="core",
        findings_count=15,
        estimated_effort="2-3h",
        is_breaking=False,
        applicable=True,
    )
    assert s.name == "core"
    assert not s.is_breaking


def test_sizing_output_valid():
    o = SizingOutput(
        repo_url="https://github.com/CopilotKit/OpenGenerativeUI",
        repo_type="external",
        languages=["python", "typescript"],
        total_findings=47,
        findings=[],
        layers=[],
        proposed_structure=[".aap/open-generative-ui/manifest.yaml"],
    )
    assert o.skill_output_type == "sizing"
    assert o.repo_type == "external"


def test_migration_output_valid():
    o = MigrationOutput(
        layer=1,
        layer_name="core",
        summary="Created .aap/ structure with 12 prompts extracted",
        files_created=[".aap/open-generative-ui/manifest.yaml"],
        files_modified=["pyproject.toml"],
        branch="aap-migration/layer-1-core",
        is_breaking=False,
    )
    assert o.skill_output_type == "migration"
    assert not o.is_breaking


def test_sizing_output_schema_has_additional_properties_false():
    schema = SizingOutput.model_json_schema()
    assert schema.get("additionalProperties") is False


def test_migration_output_schema_has_additional_properties_false():
    schema = MigrationOutput.model_json_schema()
    assert schema.get("additionalProperties") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_migration_schemas.py -v 2>&1 | head -20
```

Expected: FAIL — `SizingFinding`, `SizingOutput`, etc. not defined.

- [ ] **Step 3: Implement schemas in agent/schemas.py**

Append to `agent/schemas.py` before `SKILL_SCHEMAS`:

```python
class SizingFinding(_StrictSchema):
    """A single finding from repository analysis."""

    layer: int = Field(description="Migration layer (1-5)")
    category: str = Field(description="Finding category: prompt, model_config, tool, hitl, i18n, theme, connection, guardrail, form, persona")
    file: str = Field(description="Relative file path")
    line: int = Field(description="Line number")
    description: str = Field(description="Human-readable finding description")
    impact: str = Field(description="One of: high, medium, low")
    code_snippet: str = Field(description="First 200 chars of matched code")
    language: str = Field(description="Source language: python or typescript")


class SizingLayerSummary(_StrictSchema):
    """Summary for one migration layer."""

    layer: int = Field(description="Layer number (1-5)")
    name: str = Field(description="Layer name: core, tools, frontend, governance, polish")
    findings_count: int = Field(description="Number of findings in this layer")
    estimated_effort: str = Field(description="Estimated effort (e.g., '2-3h')")
    is_breaking: bool = Field(description="Whether this layer modifies functional code")
    applicable: bool = Field(description="False if no findings for this layer")


class SizingOutput(_StrictSchema):
    """Structured output for the aap-sizing skill."""

    skill_output_type: str = Field(default="sizing", description="Always 'sizing'")
    repo_url: str = Field(description="Repository URL analyzed")
    repo_type: str = Field(description="'internal' or 'external'")
    languages: list[str] = Field(default_factory=list, description="Languages detected")
    total_findings: int = Field(description="Total number of findings")
    findings: list[SizingFinding] = Field(default_factory=list, description="All findings")
    layers: list[SizingLayerSummary] = Field(default_factory=list, description="Per-layer summaries")
    proposed_structure: list[str] = Field(default_factory=list, description="Proposed .aap/ file paths")


class MigrationOutput(_StrictSchema):
    """Structured output for the migrate-to-aap skill."""

    skill_output_type: str = Field(default="migration", description="Always 'migration'")
    layer: int = Field(description="Layer number executed (1-5)")
    layer_name: str = Field(description="Layer name")
    summary: str = Field(description="Summary of changes made")
    files_created: list[str] = Field(default_factory=list, description="New files created")
    files_modified: list[str] = Field(default_factory=list, description="Existing files modified")
    branch: str = Field(default="", description="Branch name")
    is_breaking: bool = Field(default=False, description="Whether changes are breaking")
```

Then update `SKILL_SCHEMAS`:

```python
SKILL_SCHEMAS: dict[str, type[BaseModel]] = {
    "code-review": ReviewOutput,
    "security-scan": ReviewOutput,
    "doc-generator": PROutput,
    "test-generator": PROutput,
    "project-docs": PROutput,
    "aap-sizing": SizingOutput,
    "migrate-to-aap": MigrationOutput,
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_migration_schemas.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -q --ignore=tests/test_guardrails_e2e.py
```

Expected: All tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add agent/schemas.py tests/test_migration_schemas.py
git commit -m "feat: add Pydantic schemas for aap-sizing and migrate-to-aap skills"
```

### Task 2: Add skills to manifest + update workflow

**Files:**
- Modify: `.aap/open-swe/manifest.yaml` (add 2 skills after project-docs)
- Modify: `.github/workflows/agent.yml` (add sizing/migrate to skill regex)
- Modify: `tests/test_skills.py` (update skill count)

- [ ] **Step 1: Add skills to manifest.yaml**

Add after the `test-generator` skill entry in `.aap/open-swe/manifest.yaml`:

```yaml
    - id: aap-sizing
      name: AAP SDK Sizing
      description: Analyzes a repository and generates an AAP SDK migration report with findings organized in 5 layers
      instruction: skills/aap-sizing.md
      trigger: on_demand
      auto_invoke:
        triggers: ["sizing", "migration report", "analyze repo", "migration analysis", "aap sizing"]

    - id: migrate-to-aap
      name: AAP SDK Migration
      description: Migrates a repository to AAP SDK manifest-driven architecture in incremental layers
      instruction: skills/migrate-to-aap.md
      trigger: on_demand
      auto_invoke:
        triggers: ["migrate", "migration", "migrate to aap", "aap migration", "migrate layer"]
```

- [ ] **Step 2: Update workflow skill command regex**

In `.github/workflows/agent.yml`, update BOTH `skillMatch` regex patterns (in `run-agent` and `run-agent-pr` jobs) to include sizing and migrate:

```javascript
const skillMatch = body.match(/@aap-open-swe\s+(review|security|docs|tests|project-docs|sizing|migrate)\b/i);
const skillMap = {
  'review': 'code-review',
  'security': 'security-scan',
  'docs': 'project-docs',
  'tests': 'test-generator',
  'project-docs': 'project-docs',
  'sizing': 'aap-sizing',
  'migrate': 'migrate-to-aap',
};
```

- [ ] **Step 3: Update test_skills.py**

Change skill count assertion from 5 to 7 and add new skill IDs:

```python
def test_get_skills_loads_7_skills():
    ...
    assert len(skills) == 7
    ids = [s.id for s in skills]
    assert "aap-sizing" in ids
    assert "migrate-to-aap" in ids
```

- [ ] **Step 4: Verify manifest loads**

```bash
source .venv/bin/activate && python3 -c "
from agent.aap_config import get_skills, _load_manifest
_load_manifest.cache_clear()
skills = get_skills()
print(f'Skills: {len(skills)}')
for s in skills:
    print(f'  {s.id}: {s.name}')
"
```

Expected: 7 skills listed including aap-sizing and migrate-to-aap.

- [ ] **Step 5: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -q --ignore=tests/test_guardrails_e2e.py
```

- [ ] **Step 6: Validate workflow YAML**

```bash
source .venv/bin/activate && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/agent.yml')); print('YAML valid')"
```

- [ ] **Step 7: Commit**

```bash
git add .aap/open-swe/manifest.yaml .github/workflows/agent.yml tests/test_skills.py
git commit -m "feat: add aap-sizing and migrate-to-aap skills to manifest + workflow"
```

---

## Chunk 2: Sizing Skill Instruction

### Task 3: Create the aap-sizing skill instruction

**Files:**
- Create: `.aap/open-swe/skills/aap-sizing.md`

- [ ] **Step 1: Create the sizing skill instruction**

Create `.aap/open-swe/skills/aap-sizing.md` with the complete skill prompt. The instruction must tell the agent to:

1. **Determine repo type** — if the repo URL is different from the current repo, it's external (fork first)
2. **Clone/checkout** the target repo
3. **Scan Python files** (.py) for:
   - Prompts: variables with `PROMPT`, `INSTRUCTION`, `SYSTEM` in name, string >100 chars
   - Model configs: `ChatOpenAI(`, `init_chat_model(`, `make_model(`, `ChatAnthropic(`
   - Tools: `@tool` decorator, `def ` + tool registration patterns
   - HITL: `interrupt_on`, approval/confirmation patterns
   - Guardrails: regex filters, content moderation, PII handling
   - Configs: hardcoded URLs, constants used as config
   - i18n: hardcoded user-facing strings in `return "..."`, `print("...")`
4. **Scan TypeScript files** (.ts/.tsx) for:
   - CopilotKit: `useCopilotChat`, `useCopilotAction`, `<CopilotKit`, `/api/copilotkit`
   - React hooks: `useQuery`, `useMutation` for API calls
   - Forms: form components with hardcoded labels
   - Themes: hardcoded hex colors, HSL values, Tailwind theme config
   - Personas: role-based conditional rendering
   - i18n: hardcoded English strings in JSX
5. **Classify each finding** into layers 1-5 with impact (high/medium/low)
6. **Generate the sizing report** as markdown
7. **Create branch** `aap-migration/sizing` and commit `docs/aap-migration-report.md`
8. **Push** and output structured JSON

The instruction should include template variables `{working_dir}`, `{repo_owner}`, `{repo_name}`, `{issue_number}` and specific search commands:

```bash
# Python prompts
grep -rn "PROMPT\|INSTRUCTION\|SYSTEM_MSG\|system_prompt" --include="*.py" .

# Python model configs
grep -rn "ChatOpenAI\|ChatAnthropic\|init_chat_model\|make_model" --include="*.py" .

# Python tools
grep -rn "@tool\|def .*tool" --include="*.py" .

# TypeScript CopilotKit
grep -rn "useCopilotChat\|useCopilotAction\|CopilotKit\|copilotkit" --include="*.ts" --include="*.tsx" .

# TypeScript hardcoded strings
grep -rn "\"[A-Z][^\"]{50,}\"" --include="*.ts" --include="*.tsx" .
```

The instruction must end with: output ONLY a valid JSON object matching the SizingOutput schema.

- [ ] **Step 2: Verify skill instruction loads**

```bash
source .venv/bin/activate && python3 -c "
from agent.aap_config import get_skill_instruction, _load_manifest
_load_manifest.cache_clear()
instr = get_skill_instruction('aap-sizing')
print(f'Loaded: {len(instr)} chars')
assert len(instr) > 500
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add .aap/open-swe/skills/aap-sizing.md
git commit -m "feat: add aap-sizing skill instruction for repository analysis"
```

---

## Chunk 3: Migration Skill Instruction

### Task 4: Create the migrate-to-aap skill instruction

**Files:**
- Create: `.aap/open-swe/skills/migrate-to-aap.md`

- [ ] **Step 1: Create the migration skill instruction**

Create `.aap/open-swe/skills/migrate-to-aap.md`. The instruction must:

1. **Read the sizing report** from `docs/aap-migration-report.md` (must exist from prior sizing)
2. **Parse the --layer argument** from the task (core/tools/frontend/governance/polish or 1-5)
3. **Execute the layer**:

**Layer 1 (core):** Create `.aap/<module>/manifest.yaml`, extract prompts to `agents/*.md` and `skills/*.md`, extract model configs to artifacts, add `cockpit-aap-sdk` dependency. Do NOT modify functional code.

**Layer 2 (tools):** Add `spec.agents[].tools` to manifest, create `spec.connections` for API URLs, add `spec.hitl.tools` for HITL patterns. Only modify manifest YAML.

**Layer 3 (frontend):** Refactor React imports to use `MCPProvider`, `useTool()`, `useToolQuery()`. Add persona context. Replace hardcoded CopilotKit config. Mark PR as BREAKING.

**Layer 4 (governance):** Create `kind: Guardrail` manifests for detected patterns. Add `spec.classification` to module manifest.

**Layer 5 (polish):** Extract i18n strings to `i18n/en.json` + `pt-BR.json` skeleton. Extract theme to `spec.theme.presets`. Add `spec.recognition` if applicable.

4. **Branch naming:** `aap-migration/layer-{N}-{name}`
5. **Commit and push**
6. **Output** structured JSON matching MigrationOutput schema

Template variables: `{working_dir}`, `{repo_owner}`, `{repo_name}`, `{issue_number}`

- [ ] **Step 2: Verify skill instruction loads**

```bash
source .venv/bin/activate && python3 -c "
from agent.aap_config import get_skill_instruction, _load_manifest
_load_manifest.cache_clear()
instr = get_skill_instruction('migrate-to-aap')
print(f'Loaded: {len(instr)} chars')
assert len(instr) > 500
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add .aap/open-swe/skills/migrate-to-aap.md
git commit -m "feat: add migrate-to-aap skill instruction for 5-layer migration"
```

---

## Chunk 4: Guardrails

### Task 5: Create guardrail manifests for migration skills

**Files:**
- Create: `.aap/sizing-read-only/manifest.yaml`

- [ ] **Step 1: Create sizing read-only guardrail**

```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: sizing-read-only
  description: Ensures aap-sizing skill cannot modify any files (analysis only)
spec:
  appliesTo:
    kind: Skill
    when: "id == 'aap-sizing'"
  phase: input
  rules:
    - id: read-only
      category: scope
      onFail: block
      message: 'Sizing skill is read-only and cannot modify files'
  scope:
    allow_writes: false
```

- [ ] **Step 2: Verify guardrail resolves**

```bash
source .venv/bin/activate && python3 -c "
import asyncio
from cockpit_aap import ManifestInstance, resolve_guardrails
async def test():
    mi = ManifestInstance('open-swe')
    gs = await resolve_guardrails(mi)
    names = [g.get('metadata', {}).get('name', '') if isinstance(g, dict) else g.metadata.name for g in gs]
    print(f'Guardrails: {len(gs)}')
    print(f'Names: {names}')
    assert 'sizing-read-only' in names or any('sizing' in str(n) for n in names)
    print('OK')
asyncio.run(test())
"
```

- [ ] **Step 3: Commit**

```bash
git add .aap/sizing-read-only/
git commit -m "feat: add sizing-read-only guardrail manifest"
```

---

## Chunk 5: Update run_standalone.py for migration skills

### Task 6: Ensure migration skills use correct tool config

**Files:**
- Modify: `agent/run_standalone.py`

- [ ] **Step 1: Add migration skills to PR skills list**

In `run_standalone.py`, the `pr_skills` tuple determines which skills get default tools (vs `tools=[]`). Add the migration skills:

```python
pr_skills = ("doc-generator", "test-generator", "project-docs", "migrate-to-aap")
```

Note: `aap-sizing` is NOT in this list — it's read-only and uses `tools=[]` for safety. But it needs `execute` to run grep/find commands. So add it to a new category:

```python
# Skills that need read-only tools (execute for grep/find, but guardrail blocks writes)
analysis_skills = ("aap-sizing",)
pr_skills = ("doc-generator", "test-generator", "project-docs", "migrate-to-aap")
use_default_tools = skill_id in pr_skills or skill_id in analysis_skills
```

- [ ] **Step 2: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -q --ignore=tests/test_guardrails_e2e.py
```

- [ ] **Step 3: Commit**

```bash
git add agent/run_standalone.py
git commit -m "feat: configure migration skills tool access in run_standalone"
```

---

## Chunk 6: Testing + Validation

### Task 7: Run full test suite and lint

- [ ] **Step 1: Lint**

```bash
source .venv/bin/activate && uv run ruff check . && uv run ruff format --check . && echo "ALL CLEAN"
```

Fix any issues found.

- [ ] **Step 2: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -q --ignore=tests/test_guardrails_e2e.py
```

Expected: All tests pass.

- [ ] **Step 3: Verify all 7 skills load**

```bash
source .venv/bin/activate && python3 -c "
from agent.aap_config import get_skills, get_skill_instruction, _load_manifest
_load_manifest.cache_clear()
skills = get_skills()
print(f'Skills: {len(skills)}')
for s in skills:
    instr = get_skill_instruction(s.id)
    print(f'  {s.id}: {len(instr)} chars')
assert len(skills) == 7
print('All 7 skills loaded OK')
"
```

- [ ] **Step 4: Validate YAML**

```bash
source .venv/bin/activate && python3 -c "
import yaml
yaml.safe_load(open('.github/workflows/agent.yml'))
yaml.safe_load(open('.aap/open-swe/manifest.yaml'))
yaml.safe_load(open('.aap/sizing-read-only/manifest.yaml'))
print('All YAML valid')
"
```

- [ ] **Step 5: Commit any fixes**

```bash
git add -A && git commit -m "fix: lint and test fixes for migration skills"
```

### Task 8: Push and test

- [ ] **Step 1: Push to main**

```bash
git push
```

- [ ] **Step 2: Test sizing on-demand**

Create a test issue and trigger sizing:

```bash
gh issue create --title "Test: AAP SDK sizing" --body "Test the sizing skill on this repo"
gh issue comment <ISSUE_NUMBER> --body "@aap-open-swe sizing"
```

- [ ] **Step 3: Monitor workflow**

```bash
sleep 60 && gh run list --repo ruinosus/aap-open-swe --limit 3
```

Verify `run-agent` triggered with `SKILL_ID=aap-sizing`.

- [ ] **Step 4: Check results**

Verify the agent posted a sizing report comment on the issue.
