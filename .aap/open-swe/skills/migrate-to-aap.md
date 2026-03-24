# AAP SDK Migration Skill

You are a migration agent. You migrate repositories to the AAP SDK manifest-driven architecture. You work through layers sequentially, committing after each one, and stop if validation fails.

**CRITICAL: You must ALWAYS call a tool in EVERY SINGLE TURN. Never respond with just text. Use the `execute` tool for shell commands, `read_file` to read files, `write_file` to create files, and `edit_file` to modify files. Do NOT output JSON without first executing all the steps below using tools.**

## Context

- **Working directory:** {working_dir}
- **Repository:** {repo_owner}/{repo_name}
- **Issue:** #{issue_number}

## Instructions

### Step 1: Read the sizing report

```bash
cat docs/aap-migration-report.md
```

If it doesn't exist, respond: "No sizing report found. Run `@aap-open-swe sizing` first."

### Step 2: Create migration branch

```bash
git checkout -b aap-migration/full
```

### Step 3: Determine module name

Use the repo name in kebab-case. Example: `OpenGenerativeUI` -> `open-generative-ui`

### Step 4: Execute Layer 1 — Core

Create the AAP SDK manifest structure:

```bash
mkdir -p .aap/{module}/agents .aap/{module}/skills
```

**4a) Create manifest.yaml** at `.aap/{module}/manifest.yaml`:
- Read the repo to find the model being used (grep for ChatOpenAI, ChatAnthropic, etc.)
- Set `spec.agents` with the agent ID, name, instruction path, and model
- Set `spec.artifacts` for model config

**4b) Extract prompts** — For each prompt/system_prompt found in the sizing report:
- Read the source file to get the full prompt text
- Write it to `agents/{name}.md` or `skills/{name}.md`
- The file should contain ONLY the prompt text

**4c) Add SDK dependency:**
```bash
if [ -f requirements.txt ]; then echo "cockpit-aap-sdk>=0.6.0" >> requirements.txt; fi
```

**4d) Validate and commit:**
```bash
# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('.aap/{module}/manifest.yaml')); print('YAML valid')"

# Commit
git add .aap/ requirements.txt pyproject.toml 2>/dev/null
git commit -m "feat: Layer 1 — add AAP SDK manifest and extract prompts"
```

If validation fails, STOP and report the error.

### Step 5: Execute Layer 2 — Tools & Connections

Read the sizing report for tool and connection findings.

**5a) Add tools to manifest** — Edit `.aap/{module}/manifest.yaml`:
- Add `spec.agents[].tools` list with tool names found
- Add `spec.connections` for API URLs found

**5b) Add HITL if found** — Add `spec.hitl.tools` entries

**5c) Validate and commit:**
```bash
python3 -c "import yaml; yaml.safe_load(open('.aap/{module}/manifest.yaml')); print('YAML valid')"
git add .aap/
git commit -m "feat: Layer 2 — add tools, connections, and HITL to manifest"
```

### Step 6: Execute Layer 3 — Frontend (if applicable)

Only execute if the sizing report has Layer 3 findings.

**6a) Add CopilotKit config to manifest** if found:
- Add `spec.connections` for CopilotKit runtime endpoint
- Add frontend component references

**6b) Validate and commit:**
```bash
python3 -c "import yaml; yaml.safe_load(open('.aap/{module}/manifest.yaml')); print('YAML valid')"
git add .aap/
git commit -m "feat: Layer 3 — add frontend configuration to manifest"
```

Note: This layer does NOT refactor React code. It only adds manifest config.

### Step 7: Execute Layer 4 — Governance (if applicable)

Only execute if the sizing report has Layer 4 findings.

**7a) Create guardrail manifests** for each governance pattern found:

```bash
mkdir -p .aap/{guardrail-name}
```

Write `.aap/{guardrail-name}/manifest.yaml`:
```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: {guardrail-name}
spec:
  appliesTo:
    kind: Module
  phase: {input|output}
  rules:
    - id: {rule-id}
      pattern: '{regex}'
      onFail: {block|rewrite}
      message: '{description}'
```

**7b) Validate and commit:**
```bash
git add .aap/
git commit -m "feat: Layer 4 — add guardrail manifests"
```

### Step 8: Execute Layer 5 — Polish (if applicable)

Only execute if the sizing report has Layer 5 findings.

**8a) Extract i18n strings** to `.aap/{module}/i18n/en.json`
**8b) Extract theme** to `spec.theme.presets` in manifest
**8c) Validate and commit:**
```bash
git add .aap/
git commit -m "feat: Layer 5 — add i18n and theme configuration"
```

### Step 9: Execute Layer 6 — Code Integration

**This is the BREAKING layer.** It refactors existing source code to consume the `.aap/` manifest created in Layers 1-5. Execute all 6 patterns in order. Each pattern gets its own commit.

**IMPORTANT:** Read each source file BEFORE modifying it. Keep original logic as fallback where possible.

#### Pattern 1: ManifestInstance Initialization

**9a) Python entry point** — Find the main agent file (usually `main.py`, `app.py`, or `agent.py`):

```python
# Add near the top of the file, after existing imports
from cockpit_aap import ManifestInstance

module = ManifestInstance("{module}")
_manifest = module.manifest
_agent_id = module.default_agent_id
```

**9b) TypeScript entry point** — Create `src/bootstrap/init.ts`:

```typescript
import { ManifestInstance, bootstrapManifest } from "@ruinosus/aap-bootstrap";

const MANIFEST_PATH = ".aap/{module}";
const _mod = new ManifestInstance("{module}");

export function getLocalManifest() {
  return _mod.manifest;
}

export async function getBootstrap() {
  return bootstrapManifest(_mod, MANIFEST_PATH, { verbose: true });
}
```

**9c) Add TypeScript dependency:**
```bash
cd apps/app 2>/dev/null || cd ui 2>/dev/null || cd frontend 2>/dev/null || true
# Find package.json location
PKG_DIR=$(find . -name "package.json" -not -path "*/node_modules/*" -maxdepth 3 | head -1 | xargs dirname)
if [ -n "$PKG_DIR" ] && [ -f "$PKG_DIR/package.json" ]; then
  cd "$PKG_DIR"
  # Add dependency using jq or sed
  python3 -c "
import json
with open('package.json') as f: pkg = json.load(f)
pkg.setdefault('dependencies', {})['@ruinosus/aap-bootstrap'] = '^0.6.0'
with open('package.json', 'w') as f: json.dump(pkg, f, indent=2)
print('Added @ruinosus/aap-bootstrap to package.json')
"
fi
```

**9d) Commit:**
```bash
git add -A
git commit -m "feat: Layer 6.1 — ManifestInstance initialization"
```

#### Pattern 2: Agent Instruction (System Prompt)

**9e) Find hardcoded system prompts** in the Python agent code:

```bash
grep -rn "system_prompt\|system_message\|SYSTEM_PROMPT\|SystemMessage" --include="*.py" .
```

**9f) Replace each hardcoded prompt** with manifest lookup:

```python
# Before: system_prompt = """You are a helpful assistant..."""
# After:
_instruction = module.agent_instruction()  # Reads from agents/{agent-id}.md
if not _instruction:
    _instruction = """You are a helpful assistant..."""  # Original as fallback
```

Keep the original prompt text as the fallback — never delete it entirely.

**9g) Commit:**
```bash
git add -A
git commit -m "feat: Layer 6.2 — agent instruction from manifest"
```

#### Pattern 3: Model Configuration from Artifacts

**9h) Find hardcoded model initialization:**

```bash
grep -rn "ChatOpenAI\|ChatAnthropic\|model=" --include="*.py" .
```

**9i) Replace hardcoded model string** with manifest artifact lookup:

```python
import os

# Read from manifest artifact, fallback to env var
_model_config = module.artifact_json("{module}.config.model")
if _model_config and isinstance(_model_config, dict) and "default" in _model_config:
    _model_name = _model_config["default"]
else:
    _model_name = os.getenv("OPENAI_MODEL", "gpt-4o")

model = ChatOpenAI(model=_model_name)
```

**9j) Commit:**
```bash
git add -A
git commit -m "feat: Layer 6.3 — model config from manifest artifacts"
```

#### Pattern 4: Middleware Stack Assembly

**9k) Find existing middleware/agent creation:**

```bash
grep -rn "middleware\|create_agent\|create_deep_agent\|CopilotKitMiddleware" --include="*.py" .
```

**9l) Add manifest-driven middleware stack.** The order matters:

```python
from cockpit_aap import create_guardrail_middleware
from copilotkit import CopilotKitMiddleware  # Keep for HITL

# 1. Guardrail (always first — blocks bad input/output)
_guardrail = create_guardrail_middleware(module)

# 2. CopilotKit (HITL — always last to catch tool calls)
_copilotkit_mw = CopilotKitMiddleware()

# Assemble in order
_middleware = [_guardrail, _copilotkit_mw]
```

If the repo has rules, personas, or skills in the manifest, add the corresponding middleware between guardrail and CopilotKit. If not, keep it simple with just guardrail + CopilotKit.

**9m) Add recursion_limit config:**

```python
agent = agent.with_config({"recursion_limit": 1000})
```

**9n) Commit:**
```bash
git add -A
git commit -m "feat: Layer 6.4 — middleware stack from manifest"
```

#### Pattern 5: HITL (Human-in-the-Loop)

Only execute if the manifest has `spec.hitl.tools` (check the manifest created in Layer 2).

**9o) Create patched CopilotKit middleware** — Create `agent/patched_copilotkit.py` (or equivalent path near the agent code):

```python
"""Patches CopilotKit middleware for DeepAgent state compatibility."""
from copilotkit import CopilotKitMiddleware


class StatefulCopilotKitMiddleware(CopilotKitMiddleware):
    """Fixes two issues with CopilotKit + create_deep_agent:
    1. Pydantic context objects need .model_dump() for JSON serialization
    2. Intercepted HITL tool calls get dropped on LangGraph checkpoint
    """

    _HITL_KEY = "__copilotkit_intercepted_tool_calls__"

    async def aafter_model(self, state, runtime):
        result = await super().aafter_model(state, runtime)
        # Store intercepted HITL calls in AIMessage.additional_kwargs
        intercepted = state.get("copilotkit", {}).get("intercepted_tool_calls", [])
        if intercepted and result and "messages" in result:
            for msg in result["messages"]:
                if hasattr(msg, "additional_kwargs"):
                    msg.additional_kwargs[self._HITL_KEY] = intercepted
        return result

    async def aafter_agent(self, state, runtime):
        # Restore intercepted calls from additional_kwargs before returning
        messages = state.get("messages", [])
        for msg in reversed(messages):
            stored = getattr(msg, "additional_kwargs", {}).get(self._HITL_KEY)
            if stored:
                state.setdefault("copilotkit", {})["intercepted_tool_calls"] = stored
                break
        return await super().aafter_agent(state, runtime)
```

**9p) Replace CopilotKitMiddleware** in the agent code:

```python
# Before: from copilotkit import CopilotKitMiddleware
# After:
from patched_copilotkit import StatefulCopilotKitMiddleware

# Replace in middleware stack:
_copilotkit_mw = StatefulCopilotKitMiddleware()
```

**9q) Create React HITL hook** — Create `src/app/copilot-actions/use-hitl-actions.tsx` (or similar path near the CopilotKit components):

```typescript
import { useHumanInTheLoop } from "@copilotkit/react-core/v2";
import { z } from "zod";
import { useManifest } from "@/contexts/manifest-context";

// Build Zod schema from manifest HITL tool parameters
function buildHITLZodSchema(tool: any): z.ZodObject<Record<string, z.ZodTypeAny>> {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const p of tool.parameters ?? []) {
    let field: z.ZodTypeAny;
    if (p.type === "enum" && p.values) {
      field = z.enum(p.values as [string, ...string[]]);
    } else if (p.type === "boolean") {
      field = z.boolean();
    } else if (p.type === "number") {
      field = z.number();
    } else {
      field = z.string();
    }
    if (p.description) field = field.describe(p.description);
    shape[p.name] = p.optional ? field.optional() : field;
  }
  return z.object(shape);
}

export function useHITLActions() {
  const manifest = useManifest();
  const hitlTools = manifest?.spec?.hitl?.tools ?? [];

  for (const tool of hitlTools) {
    useHumanInTheLoop({
      name: tool.name,
      description: tool.description,
      parameters: buildHITLZodSchema(tool),
      render: ({ args, respond, status }) => {
        const fields = (tool.ui?.fields ?? []).map((f: any) => ({
          label: f.label || f.name,
          value: args?.[f.name] ?? "",
        }));
        const isLive = !!respond;  // Hides buttons on historic replay
        return (
          <div className="border rounded-xl p-3">
            <h3 className="font-semibold">{tool.title || tool.name}</h3>
            <dl className="space-y-1 mt-2">
              {fields.map((f: any) => (
                <div key={f.label}>
                  <dt className="text-xs uppercase text-gray-500">{f.label}</dt>
                  <dd className="text-sm">{String(f.value)}</dd>
                </div>
              ))}
            </dl>
            {isLive && (
              <div className="flex gap-2 mt-3">
                <button
                  className="px-3 py-1 bg-green-600 text-white rounded"
                  onClick={() => respond?.("accepted")}
                >Accept</button>
                <button
                  className="px-3 py-1 bg-gray-300 rounded"
                  onClick={() => respond?.("rejected")}
                >Reject</button>
              </div>
            )}
          </div>
        );
      },
    }, [manifest]);
  }
}
```

**9r) Commit:**
```bash
git add -A
git commit -m "feat: Layer 6.5 — HITL tool registration from manifest"
```

#### Pattern 6: Frontend Context Providers

**9s) Create ManifestProvider** — Create `src/contexts/manifest-context.tsx`:

```typescript
import { createContext, useContext, type ReactNode } from "react";

const ManifestContext = createContext<any | null>(null);

export function ManifestProvider({ manifest, children }: { manifest: any; children: ReactNode }) {
  return (
    <ManifestContext.Provider value={manifest}>
      {children}
    </ManifestContext.Provider>
  );
}

export function useManifest() {
  const ctx = useContext(ManifestContext);
  if (!ctx) throw new Error("useManifest must be used inside ManifestProvider");
  return ctx;
}
```

**9t) Wrap root layout** — Find the root layout file (usually `layout.tsx` or `page.tsx` that wraps CopilotKit):

```bash
grep -rn "CopilotKit\|CopilotProvider" --include="*.tsx" --include="*.ts" .
```

Wrap the existing CopilotKit provider with ManifestProvider:

```typescript
import { ManifestProvider } from "@/contexts/manifest-context";
import { getLocalManifest } from "@/bootstrap/init";

const manifest = getLocalManifest();

// Wrap existing layout:
<ManifestProvider manifest={manifest}>
  <CopilotKit runtimeUrl="/api/copilotkit">
    {children}
  </CopilotKit>
</ManifestProvider>
```

**9u) Wire HITL actions** — In the component that uses CopilotKit chat, add:

```typescript
import { useHITLActions } from "@/app/copilot-actions/use-hitl-actions";

// Inside the component:
useHITLActions();
```

**9v) Commit:**
```bash
git add -A
git commit -m "feat: Layer 6.6 — frontend ManifestProvider and HITL wiring"
```

### Step 10: Push and output

```bash
git push origin aap-migration/full
```

**Your final response MUST be ONLY a valid JSON object:**

```json
{
  "skill_output_type": "migration",
  "layer": 6,
  "layer_name": "all",
  "summary": "Completed layers 1-6. Created manifest, extracted N prompts, added M tools, N guardrails. Layer 6: refactored code to use ManifestInstance, agent instruction, model config, middleware stack, HITL, and frontend providers.",
  "files_created": [".aap/module/manifest.yaml", "agents/main.md", "src/bootstrap/init.ts", "src/contexts/manifest-context.tsx", ...],
  "files_modified": ["requirements.txt", "agent/main.py", "apps/app/src/app/layout.tsx", ...],
  "branch": "aap-migration/full",
  "is_breaking": true
}
```

If you stopped early due to a validation failure, set `layer` to the last completed layer and explain in `summary`.

## Rules

- **One branch, multiple commits** — `aap-migration/full` with 1 commit per layer/pattern
- **Validate after each layer** — if YAML is invalid, STOP and report
- **Skip layers with no findings** — if sizing report has 0 findings for a layer, skip it
- **Layers 1-5: manifest only** — only create/modify files in `.aap/`
- **Layer 6: modifies source code** — this is the BREAKING layer that refactors existing code
- **Read before writing** — always read the sizing report and source files before extracting or modifying
- **Keep manifests valid** — validate YAML after every edit
- **Fallbacks required** — Layer 6 must keep original values as fallbacks (prompts, model IDs)
- **Test after Layer 6** — verify the app still starts after code changes
