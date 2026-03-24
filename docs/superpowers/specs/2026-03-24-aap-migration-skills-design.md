# AAP SDK Migration Skills — Design Spec

## Summary

Two new skills for the Open SWE agent that automate migrating external repositories
to the AAP SDK manifest-driven architecture. The migration is non-destructive,
incremental, and organized in 5 independent layers that can be applied selectively.

**Skills:**
- `aap-sizing` — Analyzes a repository and generates a migration report (read-only)
- `migrate-to-aap` — Executes the migration in layers, each as a separate PR

**Scope:** Python + TypeScript repositories. Covers backend (agents, LangGraph),
frontend (CopilotKit, React), HITL, governance, i18n, theming, and more.

## Goals

- **Zero-risk analysis** — sizing never modifies the target repo
- **Incremental adoption** — each layer delivers value independently
- **Report-first** — human reviews the plan before any code changes
- **Full SDK coverage** — not just prompts, but tools, HITL, i18n, themes, governance
- **Works for internal and external repos** — direct branch or fork

## Non-Goals

- Migrating non-Python/TypeScript repos (Go, Java, etc.)
- Auto-merging PRs (always draft, human reviews)
- Migrating infrastructure (Docker, K8s, CI/CD)

---

## Architecture

```
User: @aap-open-swe sizing <repo_url>
    |
    v
aap-sizing skill (read-only)
    |-- Clone repo (or fork if external)
    |-- Scan Python files (.py) for: prompts, model configs, tools, HITL, guardrails, i18n
    |-- Scan TypeScript files (.ts/.tsx) for: CopilotKit, hooks, forms, actions, themes
    |-- Classify findings into 5 layers
    |-- Generate sizing report (markdown)
    |-- Create branch: aap-migration/sizing
    |-- PR with docs/aap-migration-report.md
    |-- Comment summary on issue
    v
User reviews report, chooses layers to migrate
    |
    v
User: @aap-open-swe migrate --layer=core (or 1, 2, 3, 4, 5)
    |
    v
migrate-to-aap skill (executes per layer)
    |-- Read sizing report as input
    |-- Execute layer-specific migration
    |-- Create branch: aap-migration/layer-N-<name>
    |-- PR with changes for that layer
    |-- Comment summary on issue
    v
Repeat for each layer the user wants
```

---

## The 5 Migration Layers

### Layer 1: Core (manifest + agents + prompts + configs)

**What it creates:**
- `.aap/<module>/manifest.yaml` with apiVersion, kind: Module, metadata, spec
- `agents/*.md` — extracted system prompts
- `skills/*.md` — extracted skill instructions
- `spec.artifacts` — model configs, connection URLs, hardcoded settings

**What it modifies:**
- Adds `cockpit-aap-sdk` to `requirements.txt` / `pyproject.toml` / `package.json`
- Does NOT modify functional code (safe, non-breaking)

**What sizing looks for:**

| Pattern | Python | TypeScript |
|---------|--------|------------|
| System prompts | Variables named `*PROMPT*`, `*INSTRUCTION*`, `*SYSTEM*` with strings >100 chars | Template literals >100 chars assigned to prompt-like variables |
| Agent creation | `create_deep_agent(system_prompt=...)`, `ChatOpenAI(...)` | `useCoAgent()`, agent config objects |
| Model configs | `ChatOpenAI(model=..., temperature=...)`, `init_chat_model(...)`, `make_model(...)` | `new OpenAI({model: ...})`, model config objects |
| Hardcoded configs | `API_URL = "..."`, `MAX_RETRIES = 3`, constants used as config | `const CONFIG = {...}`, inline env var usage |

### Layer 2: Tools & Connections (tool defs + MCP + HITL)

**What it creates:**
- `spec.agents[].tools` entries in manifest
- `spec.connections` with external API URLs
- `spec.hitl.tools` with HITL card definitions (if HITL patterns found)
- MCP tool schemas in manifest if applicable

**What it modifies:**
- Only the manifest file (non-breaking)

**What sizing looks for:**

| Pattern | Python | TypeScript |
|---------|--------|------------|
| Tool definitions | `@tool` decorator, tool registration functions | `defineTool()`, MCP tool schemas |
| MCP servers | `McpServer()`, server configs, stdio/HTTP setup | MCP server instances |
| API connections | `httpx.Client("https://...")`, `requests.get(url)` | `fetch("https://...")`, axios base URLs |
| HITL patterns | `interrupt_on`, approval flows, human confirmation prompts | `useCopilotAction()` with confirm, Zod schemas for user input |

### Layer 3: Frontend (CopilotKit + React hooks + forms + personas)

**What it creates:**
- `MCPProvider` wrapper component (if not present)
- Persona context setup (if role-based UI detected)

**What it modifies:**
- Refactors React hooks to use `useTool()`, `useToolQuery()` from SDK
- Replaces hardcoded CopilotKit config with manifest-driven setup
- Adds persona context if role-based UI switching detected
- Replaces manual form fields with `AIFieldBlock` / `ManifestSmartInput` where applicable
- **This layer is breaking — requires careful review**

**What sizing looks for:**

| Pattern | TypeScript/React |
|---------|-----------------|
| CopilotKit usage | `<CopilotKit>`, `useCopilotChat()`, `useCopilotAction()`, `/api/copilotkit` endpoints |
| Custom API hooks | `useQuery`/`useMutation` for API calls that could use `useTool()` |
| Form components | Form fields with hardcoded labels/validation that could use `AIFieldBlock` |
| Role-based UI | Conditional rendering based on user role (could use `usePersonaContext()`) |
| Action cards | Button/action patterns that map to `ActionCard` component |

### Layer 4: Governance (guardrails + policies + classification)

**What it creates:**
- `kind: Guardrail` manifests in `.aap/` for each detected pattern
- `spec.classification` in module manifest
- `kind: ConformancePolicy` if structural rules detected

**What it modifies:**
- Only creates new YAML files (non-breaking)

**What sizing looks for:**

| Pattern | Python + TypeScript |
|---------|---------------------|
| Input validation | Regex filters, content moderation, blocklist checks |
| Output filtering | PII scrubbing, secret detection, redaction logic |
| Access control | Role checks, auth middleware, permission guards |
| Cost tracking | Token counting, usage logging, billing logic |
| Data classification | Sensitivity labels, compliance markers, data types |

### Layer 5: Polish (i18n + themes + recognition + commands)

**What it creates:**
- `i18n/en.json` with extracted strings
- `i18n/pt-BR.json` skeleton (keys only, values marked for translation)
- `spec.theme.presets` in manifest
- `spec.recognition` if gamification patterns detected
- `spec.commands` if slash commands detected
- `spec.skills[].autoInvoke.triggers` if trigger patterns detected

**What it modifies:**
- Replaces hardcoded strings with i18n lookups (if opted in)
- Otherwise, only adds files (non-breaking)

**What sizing looks for:**

| Pattern | Python + TypeScript |
|---------|---------------------|
| i18n strings | Hardcoded user-facing text: labels, messages, errors, toasts, tooltips |
| Themes | Hardcoded colors (hex/rgb/hsl), CSS custom properties, Tailwind theme config |
| Gamification | XP systems, badge logic, achievement tracking, feedback collection |
| Commands | Slash commands, keyboard shortcuts, command palettes |
| Skills | Auto-invoke patterns, keyword matching, trigger detection |

---

## Sizing Report Format

```markdown
# AAP SDK Migration Report — [repo-name]

## Summary

| Metric | Value |
|--------|-------|
| Repository | owner/repo-name |
| Type | internal / external (fork) |
| Languages | Python, TypeScript |
| Total findings | 47 |
| Layers applicable | 1, 2, 3, 5 (4 not needed) |

## Layer Overview

| Layer | Name | Findings | Effort | Breaking? |
|-------|------|----------|--------|-----------|
| 1 | Core | 15 | 2-3h | No |
| 2 | Tools & Connections | 8 | 1-2h | No |
| 3 | Frontend | 12 | 3-4h | Yes |
| 4 | Governance | 5 | 1h | No |
| 5 | Polish | 7 | 2h | No |

## Detailed Findings

### Layer 1: Core (15 findings)

| # | Category | File | Line | Description | Impact |
|---|----------|------|------|-------------|--------|
| 1 | prompt | apps/agent/src/agent.py | 15 | SYSTEM_PROMPT (2.3K chars) | high |
| 2 | model_config | apps/agent/main.py | 22 | ChatOpenAI(model="gpt-4o", temperature=0) | high |
| 3 | artifact | apps/agent/config.py | 5 | MAX_RETRIES = 3 | low |
...

### Layer 2: Tools & Connections (8 findings)
...

### Layer 3: Frontend (12 findings)
...

### Layer 4: Governance (5 findings)
...

### Layer 5: Polish (7 findings)
...

## Proposed .aap/ Structure

.aap/
  [module-name]/
    manifest.yaml          # kind: Module — agents, artifacts, connections, etc.
    agents/
      main-agent.md        # extracted from SYSTEM_PROMPT
    skills/
      chart-skill.md       # extracted from CHART_PROMPT
      svg-skill.md
    i18n/
      en.json              # extracted user-facing strings
      pt-BR.json           # skeleton for translation
  [guardrail-name]/
    manifest.yaml          # kind: Guardrail — PII, secrets, etc.

## How to Migrate

# Review this report, then run each layer:
@aap-open-swe migrate --layer=core        # safe, non-breaking
@aap-open-swe migrate --layer=tools       # safe, non-breaking
@aap-open-swe migrate --layer=frontend    # BREAKING — review carefully
@aap-open-swe migrate --layer=governance  # safe, non-breaking
@aap-open-swe migrate --layer=polish      # safe, non-breaking
```

---

## Branching Strategy

| Scenario | Sizing Branch | Layer Branches |
|----------|--------------|----------------|
| Internal repo | `aap-migration/sizing` | `aap-migration/layer-1-core`, `layer-2-tools`, etc. |
| External repo | Fork → `aap-migration/sizing` | Fork → `aap-migration/layer-1-core`, etc. |

All PRs are created as **draft** — human must review and merge.

---

## Output Schemas

```python
class SizingFinding(BaseModel):
    layer: int                    # 1-5
    category: str                 # "prompt", "model_config", "tool", "hitl", "i18n", etc.
    file: str                     # relative path
    line: int                     # line number
    description: str              # human-readable finding
    impact: str                   # "high", "medium", "low"
    code_snippet: str             # first 200 chars of matched code
    language: str                 # "python", "typescript"

class SizingLayerSummary(BaseModel):
    layer: int
    name: str                     # "core", "tools", "frontend", "governance", "polish"
    findings_count: int
    estimated_effort: str         # "1-2h", "3-4h", etc.
    is_breaking: bool
    applicable: bool              # false if no findings for this layer

class SizingOutput(BaseModel):
    skill_output_type: str = "sizing"
    repo_url: str
    repo_type: str                # "internal" | "external"
    languages: list[str]
    total_findings: int
    findings: list[SizingFinding]
    layers: list[SizingLayerSummary]
    proposed_structure: list[str] # file paths for proposed .aap/

class MigrationOutput(BaseModel):
    skill_output_type: str = "migration"
    layer: int
    layer_name: str
    summary: str
    files_created: list[str]
    files_modified: list[str]
    branch: str
    is_breaking: bool
```

---

## Guardrails

| Guardrail | Skill | Scope |
|-----------|-------|-------|
| `sizing-read-only` | `aap-sizing` | Cannot modify any files (analysis only) |
| `layer-1-scope` | `migrate-to-aap` L1 | Can only create in `.aap/` + add dependency |
| `layer-2-scope` | `migrate-to-aap` L2 | Can only modify manifest YAML |
| `layer-3-scope` | `migrate-to-aap` L3 | Can modify `.ts`/`.tsx` frontend files |
| `layer-4-scope` | `migrate-to-aap` L4 | Can only create guardrail manifests in `.aap/` |
| `layer-5-scope` | `migrate-to-aap` L5 | Can create i18n JSON + modify manifest |
| `backup-before-change` | All layers | Must commit before any refactoring |

---

## Trigger Commands

```
# Sizing (analysis only)
@aap-open-swe sizing                     # analyze current repo
@aap-open-swe sizing <repo_url>          # analyze external repo (fork first)

# Migration (per layer)
@aap-open-swe migrate --layer=core       # or --layer=1
@aap-open-swe migrate --layer=tools      # or --layer=2
@aap-open-swe migrate --layer=frontend   # or --layer=3
@aap-open-swe migrate --layer=governance # or --layer=4
@aap-open-swe migrate --layer=polish     # or --layer=5
@aap-open-swe migrate --layer=all        # all layers sequentially
```

---

## Manifest Entries

```yaml
# In .aap/open-swe/manifest.yaml
skills:
  - id: aap-sizing
    name: AAP SDK Sizing
    description: Analyzes a repository and generates an AAP SDK migration report
    instruction: skills/aap-sizing.md
    trigger: on_demand
    auto_invoke:
      triggers: ["sizing", "migration report", "analyze repo", "migration analysis"]

  - id: migrate-to-aap
    name: AAP SDK Migration
    description: Migrates a repository to AAP SDK manifest-driven architecture
    instruction: skills/migrate-to-aap.md
    trigger: on_demand
    auto_invoke:
      triggers: ["migrate", "migration", "migrate to aap", "aap migration"]
```

---

## Workflow Integration

New jobs in `.github/workflows/agent.yml`:

```yaml
# On-demand skill commands already parsed by run-agent / run-agent-pr.
# The sizing and migrate commands map to SKILL_ID via the existing
# skillMatch regex. Add to the pattern:
#
#   /@aap-open-swe\s+(review|security|docs|tests|project-docs|sizing|migrate)\b/i
#
# And to skillMap:
#   'sizing': 'aap-sizing',
#   'migrate': 'migrate-to-aap',
```

---

## Success Criteria

1. `aap-sizing` produces accurate report for repos like OpenGenerativeUI
2. `migrate-to-aap --layer=core` creates valid `.aap/` structure that passes `aap validate`
3. Each layer's PR is self-contained and can be merged independently
4. No functional code is broken by layers 1, 2, 4, 5 (non-breaking)
5. Layer 3 (frontend) changes are clearly marked as breaking in the PR description
6. External repos are forked automatically before any changes
7. Guardrails prevent each skill from modifying files outside its scope

---

## Testing Strategy

| Test Type | What |
|-----------|------|
| Unit tests | Sizing patterns (regex matching for prompts, configs, tools, etc.) |
| Integration | Sizing against a sample repo fixture (small repo with known patterns) |
| E2E | Sizing + migrate layer 1 on a real repo with LLM |
| Guardrail tests | Verify each layer cannot write outside its scope |

---

## Dependencies

- `cockpit-aap-sdk >= 0.6.0` (already installed)
- `aap validate` CLI for validating generated manifests (optional, nice-to-have)
- GitHub API for fork creation (external repos)

---

## Files to Create

```
New:
  .aap/open-swe/skills/aap-sizing.md          # sizing skill instruction
  .aap/open-swe/skills/migrate-to-aap.md      # migration skill instruction
  agent/schemas.py                              # add SizingOutput, MigrationOutput
  .aap/sizing-read-only/manifest.yaml          # guardrail: sizing is read-only
  .aap/migration-layer-scope/manifest.yaml     # guardrail: per-layer file scope
  tests/test_migration_skills.py               # unit + integration tests

Modified:
  .aap/open-swe/manifest.yaml                 # add 2 skills
  .github/workflows/agent.yml                 # add sizing/migrate to skill command parsing
```
