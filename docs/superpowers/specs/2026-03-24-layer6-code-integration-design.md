# Layer 6: Code Integration — Design Spec

## Summary

Layer 6 is the final migration layer that **refactors existing source code** to consume
the AAP SDK manifest instead of using hardcoded prompts, model configs, tools, HITL,
and frontend patterns. Layers 1-5 only create `.aap/` files without touching code.
Layer 6 is the one that makes the code actually USE those files.

**Reference Implementation:** `apps/aap-launchpad/` in the AAP SDK monorepo
(`/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/`).

**Scope:** Python (agent backend) + TypeScript/React (frontend)

**Breaking:** Yes — this layer modifies functional code.

---

## The 6 Integration Patterns

### Pattern 1: ManifestInstance Initialization

**What:** Every app that uses the AAP SDK starts by creating a `ManifestInstance` singleton
that reads the `.aap/<module>/manifest.yaml` and provides typed access to all config.

**Python — Before:**
```python
# apps/agent/main.py
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-5.4-2026-03-05")
system_prompt = """You are a helpful assistant..."""
```

**Python — After:**
```python
# apps/agent/main.py
from cockpit_aap import ManifestInstance

module = ManifestInstance("open-generative-ui")
_manifest = module.manifest
_agent_id = module.default_agent_id

# Now everything reads from manifest
```

**TypeScript — Before:**
```typescript
// apps/app/src/app/api/copilotkit/route.ts
const runtime = new CopilotRuntime({
  agents: { default: defaultAgent },
  a2ui: { injectA2UITool: true },
});
```

**TypeScript — After:**
```typescript
// apps/app/src/bootstrap/init.ts
import { ManifestInstance, bootstrapManifest } from "@ruinosus/aap-bootstrap";

const _mod = new ManifestInstance("open-generative-ui");

export function getLocalManifest() {
  return _mod.manifest;
}

export async function getBootstrap() {
  return bootstrapManifest(sdk, MANIFEST_PATH, { verbose: true });
}
```

**Key Files in Launchpad:**
- Python: `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/agent/main.py` (lines 179-185)
- TypeScript: `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/src/bootstrap/init.ts`

**What the migrate agent needs to do:**
1. Find the main entry point of the Python agent (usually `main.py` or `app.py`)
2. Add `from cockpit_aap import ManifestInstance` import
3. Add `module = ManifestInstance("<module-name>")` near the top
4. Find the main entry point of the TypeScript app (usually `layout.tsx` or `route.ts`)
5. Create `src/bootstrap/init.ts` with ManifestInstance setup
6. Add `@ruinosus/aap-bootstrap` to `package.json` dependencies

---

### Pattern 2: Agent Instruction (System Prompt)

**What:** Replace hardcoded system prompts with `module.agent_instruction()` which reads
from `agents/<id>.md` files referenced in the manifest.

**Python — Before:**
```python
system_prompt = f"""
    You are a helpful assistant that helps users understand CopilotKit and LangGraph.
    Be brief in your explanations, 1 to 2 sentences.
    When demonstrating charts, always call the query_data tool first.
    ... (500+ chars)
"""

agent = create_agent(
    model=model,
    system_prompt=system_prompt,
    tools=[...],
)
```

**Python — After:**
```python
# Read instruction from manifest (agents/main-agent.md)
_instruction = module.agent_instruction()  # Uses default agent
# Or for a specific agent:
# _instruction = module.agent_instruction("main-agent")

# Fallback if manifest not available
if not _instruction:
    _instruction = "You are a helpful assistant..."

agent = create_agent(
    model=model,
    system_prompt=_instruction,
    tools=[...],
)
```

**Key Files in Launchpad:**
- `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/agent/main.py` (lines 229-240)
- Helper: `cockpit_aap.manifest.helpers.get_manifest_agent_instruction()`

**What the migrate agent needs to do:**
1. Find all variables containing system prompts (identified in sizing report Layer 1)
2. Replace the hardcoded string with `module.agent_instruction("<agent-id>")`
3. The prompt text already exists in `agents/<id>.md` (created in Layer 1)
4. Add fallback: `if not _instruction: _instruction = "<original prompt>"`

---

### Pattern 3: Model Configuration from Artifacts

**What:** Replace hardcoded model initialization with manifest artifact lookup.

**Python — Before:**
```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-5.4-2026-03-05")
```

**Python — After:**
```python
import os
from langchain_openai import ChatOpenAI

# Read from manifest artifact, fallback to env var
_model_config = module.artifact_json("open-generative-ui.config.model")
if _model_config and isinstance(_model_config, dict) and "default" in _model_config:
    _model_name = _model_config["default"]
else:
    _model_name = os.getenv("OPENAI_MODEL", "gpt-4o")

model = ChatOpenAI(model=_model_name)
```

**Key Files in Launchpad:**
- `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/agent/main.py` (lines 241-260)

**What the migrate agent needs to do:**
1. Find all model initialization calls (identified in sizing report Layer 1)
2. Replace hardcoded model string with `module.artifact_json("<module>.config.model")`
3. Keep env var fallback for backwards compatibility
4. The artifact key already exists in manifest (created in Layer 1)

---

### Pattern 4: Middleware Stack Assembly

**What:** Replace manual middleware/guard logic with declarative manifest-driven middleware.
The Launchpad assembles middleware in a specific order that matters:

```
Guardrail → Rules → Cost → Persona → Skills → CopilotKit/HITL
```

**Python — Before (typical LangGraph agent):**
```python
from copilotkit import CopilotKitMiddleware

agent = create_agent(
    model=model,
    tools=[query_data, *todo_tools, generate_form],
    middleware=[CopilotKitMiddleware()],
    state_schema=AgentState,
    system_prompt=system_prompt,
)
```

**Python — After (manifest-driven stack):**
```python
from cockpit_aap import ManifestInstance, create_guardrail_middleware
from cockpit_aap.runtime import GuardrailMiddleware
from agent.middleware import ManifestSkillMiddleware
from copilotkit import CopilotKitMiddleware  # Keep for HITL

module = ManifestInstance("open-generative-ui")

# 1. Guardrail middleware (from kind: Guardrail manifests in .aap/)
_guardrail = create_guardrail_middleware(module)

# 2. Rules middleware (from manifest spec.rules)
_manifest_rules = module.rules() or []
# ... create rules middleware if rules exist

# 3. Persona middleware (from manifest spec.personas)
# ... create persona middleware if personas exist

# 4. Skill middleware (from manifest spec.skills)
_skill_middleware = ManifestSkillMiddleware(module.manifest) if module.manifest else None

# 5. CopilotKit middleware (HITL — always last)
_copilotkit_mw = CopilotKitMiddleware()

# Assemble in order
_middleware = [_guardrail]
if _manifest_rules:
    _middleware.append(_rules_mw)
if _skill_middleware:
    _middleware.append(_skill_middleware)
_middleware.append(_copilotkit_mw)

agent = create_agent(
    model=model,
    tools=[query_data, *todo_tools, generate_form],
    middleware=_middleware,
    state_schema=AgentState,
    system_prompt=_instruction,
)
```

**Key Files in Launchpad:**
- `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/agent/main.py` (lines 186-389)
- Guardrail: lines 186-190
- Rules: lines 269-319
- Cost: lines 192-206
- Persona: lines 331-384
- Skills: lines 386-388
- CopilotKit: line 388

**Middleware Order Matters:**
1. **Guardrail** — blocks dangerous input/output BEFORE anything else
2. **Rules** — business rules BEFORE expensive LLM calls
3. **Cost** — budget enforcement BEFORE LLM call
4. **Persona** — injects persona context into system prompt
5. **Skills** — injects active skill instructions based on trigger detection
6. **CopilotKit** — HITL tool interception (must be LAST to catch tool calls)

**What the migrate agent needs to do:**
1. Find existing middleware array in `create_agent()` or `create_deep_agent()` call
2. Add guardrail middleware from manifest (always, as first)
3. Add skill middleware if manifest has skills
4. Keep existing CopilotKit middleware but move to end
5. Add recursion_limit config: `.with_config({"recursion_limit": 1000})`

---

### Pattern 5: HITL (Human-in-the-Loop)

**What:** HITL is the most complex pattern. It involves:
- **Manifest:** `spec.hitl.tools[]` defines HITL tool schemas
- **Python:** `StatefulCopilotKitMiddleware` intercepts HITL tool calls
- **React:** `useHumanInTheLoop()` hook registers HITL tools with Zod schemas built from manifest
- **UI:** `ActionCard` component renders HITL cards with approve/reject buttons

#### 5a. Manifest HITL Definition

```yaml
# .aap/open-generative-ui/manifest.yaml
spec:
  hitl:
    tools:
      - name: confirm_visualization
        title: "Visualization Preview"
        description: "Show the user a preview of the generated visualization before rendering"
        parameters:
          - name: title
            type: string
            description: "Title of the visualization"
          - name: description
            type: string
            description: "What the visualization shows"
          - name: html_preview
            type: string
            description: "HTML preview snippet"
        ui:
          fields:
            - name: title
              label: "Title"
            - name: description
              label: "Description"
            - name: html_preview
              label: "Preview"
```

#### 5b. Python HITL Middleware

The Launchpad uses a `StatefulCopilotKitMiddleware` that patches CopilotKit's middleware
with two critical fixes:

**Fix 1: Pydantic Serialization**
AG-UI Context objects are Pydantic models that need `.model_dump()` before JSON serialization.

**Fix 2: HITL State Persistence**
`create_deep_agent` only declares `messages` in state schema, so the CopilotKit
`intercepted_tool_calls` key gets dropped. The fix stores intercepted calls in
`AIMessage.additional_kwargs` so they survive LangGraph checkpoints.

**Key File:** `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/agent/patched_copilotkit.py` (144 lines)

```python
class StatefulCopilotKitMiddleware(CopilotKitMiddleware):
    """Patches CopilotKit middleware for DeepAgent state compatibility."""

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

#### 5c. React HITL Registration

**Key File:** `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/src/app/copilot-actions/use-hitl-actions.tsx` (246 lines)

**Step 1: Build Zod schema from manifest HITL tool parameters**
```typescript
function buildHITLZodSchema(tool: ManifestHITLTool): z.ZodObject<Record<string, z.ZodTypeAny>> {
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
```

**Step 2: Register each HITL tool with useHumanInTheLoop**
```typescript
import { useHumanInTheLoop } from "@copilotkit/react-core/v2";

const tool = manifest.spec.hitl.tools.find(t => t.name === "confirm_visualization");

useHumanInTheLoop({
  name: tool.name,
  description: tool.description,
  parameters: buildHITLZodSchema(tool),
  render: ({ args, respond, status }) => {
    return (
      <ActionCard
        title={tool.title}
        status={status}
        fields={mapArgsToFields(args, tool.ui.fields)}
        isLive={!!respond}  // CRITICAL: hides buttons on historic replay
        onAccept={() => respond?.("accepted")}
        onReject={() => respond?.("rejected")}
      />
    );
  },
}, [manifest]);
```

**Step 3: ActionCard isLive guard**
```typescript
// The isLive={!!respond} pattern prevents duplicate approvals on page reload.
// When respond is undefined (historic message replay), buttons are hidden.
const showButtons = !actionTaken && !isAccepted && isLive !== false;
```

#### 5d. What the migrate agent needs to do for HITL

1. **In manifest:** Add `spec.hitl.tools[]` entries for each approval/confirmation pattern found in the code
2. **In Python agent:** Replace `CopilotKitMiddleware()` with `StatefulCopilotKitMiddleware()` (copy from Launchpad)
3. **In React:** Create `use-hitl-actions.tsx` with `buildHITLZodSchema()` + `useHumanInTheLoop()` for each HITL tool
4. **In React:** Create or reuse `ActionCard` component with `isLive` guard

---

### Pattern 6: Frontend Context Providers

**What:** Wrap the React app with manifest-driven context providers so all components
can access manifest data, personas, themes, and i18n.

**Before:**
```typescript
// apps/app/src/app/layout.tsx
export default function Layout({ children }) {
  return (
    <CopilotKit runtimeUrl="/api/copilotkit">
      {children}
    </CopilotKit>
  );
}
```

**After:**
```typescript
// apps/app/src/app/layout.tsx
import { ManifestProvider } from "@/contexts/manifest-context";
import { PersonaProvider } from "@/contexts/persona-context";
import { getLocalManifest } from "@/bootstrap/init";

const manifest = getLocalManifest();

export default function Layout({ children }) {
  return (
    <ManifestProvider manifest={manifest}>
      <PersonaProvider manifest={manifest} defaultPersona="developer">
        <CopilotKit runtimeUrl="/api/copilotkit">
          {children}
        </CopilotKit>
      </PersonaProvider>
    </ManifestProvider>
  );
}
```

**ManifestProvider implementation:**
```typescript
// contexts/manifest-context.tsx
import { createContext, useContext } from "react";
import type { Manifest } from "@ruinosus/aap-bootstrap";

const ManifestContext = createContext<Manifest | null>(null);

export function ManifestProvider({ manifest, children }) {
  return (
    <ManifestContext.Provider value={manifest}>
      {children}
    </ManifestContext.Provider>
  );
}

export function useManifest(): Manifest {
  const ctx = useContext(ManifestContext);
  if (!ctx) throw new Error("useManifest must be inside ManifestProvider");
  return ctx;
}
```

**PersonaProvider implementation:**
```typescript
// contexts/persona-context.tsx
// Reads spec.personas from manifest
// Provides: persona, activePersona, personas, switchPersona,
//           allowedTools, allowedPanels, allowedSkills
```

**Key Files in Launchpad:**
- `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/src/contexts/manifest-context.tsx`
- `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/src/contexts/persona-context.tsx`
- `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/src/contexts/tenant-context.tsx`
- `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/src/app/launchpad-client.tsx` (lines 517-531)

**What the migrate agent needs to do:**
1. Create `src/contexts/manifest-context.tsx` (ManifestProvider + useManifest hook)
2. Create `src/bootstrap/init.ts` (ManifestInstance singleton)
3. Wrap root layout with `<ManifestProvider manifest={manifest}>`
4. If personas exist: create `src/contexts/persona-context.tsx` and add `<PersonaProvider>`
5. Replace hardcoded strings with i18n lookups where applicable

---

## Artifact Persistence Patterns

Beyond the 6 patterns above, the Launchpad also shows two artifact persistence patterns
that may apply to migrated repos:

### Client-side (localStorage)

For transient state (journey progress, user preferences):
```typescript
// Scoped by userId
const storageKey = `module-state-${userId}`;
const [state, setState] = useState(() => JSON.parse(localStorage.getItem(storageKey) || "{}"));
useEffect(() => { localStorage.setItem(storageKey, JSON.stringify(state)); }, [state]);
```

### Server-side (MCP Artifacts)

For durable state (session history, conversation metadata):
```typescript
// Via MCP JSON-RPC endpoint
const result = await callTool("search_artifacts", { query: key, search_type: "key" });
await callTool("update_artifact", { id: result.artifacts[0].id, value: JSON.stringify(data) });
```

### Conversation Persistence (Python)

```python
from cockpit_aap.conversation import create_conversation_store

conv_store = await create_conversation_store(
    database_url=os.getenv("DATABASE_URL"),  # Postgres
    sqlite_path=".aap/module/memory/conversations.db",  # SQLite fallback
)
checkpointer = conv_store.as_checkpointer()

agent = create_deep_agent(
    model=model,
    checkpointer=checkpointer,  # Enables multi-session persistence
    ...
)
```

---

## Multi-Agent Routing

The Launchpad defines 2 agents in manifest and routes based on backend availability:

```yaml
# manifest.yaml
spec:
  agents:
    - id: main-agent          # Primary (DeepAgent)
    - id: standard-agent      # Fallback (simpler)
```

```python
# Python: register whichever agent is available
try:
    add_langgraph_fastapi_endpoint(app, agent=deep_agent, path=f"/{agent_id}")
except:
    # Fallback to simpler agent
    pass
```

```typescript
// React: route to available backend
const agentId = hasDeepAgent ? "main-agent" : "standard-agent";
<CopilotChatConfigurationProvider agentId={agentId} />
```

---

## Migration Execution Order

When the migrate agent executes Layer 6, it should follow this order:

1. **Pattern 1** first — ManifestInstance init (everything depends on this)
2. **Pattern 2** — Agent instruction (quick win, low risk)
3. **Pattern 3** — Model config (quick win, low risk)
4. **Pattern 4** — Middleware stack (moderate complexity)
5. **Pattern 5** — HITL (highest complexity, requires frontend + backend)
6. **Pattern 6** — Frontend providers (requires frontend changes)

Each pattern should be a separate commit to enable incremental review.

---

## Dependencies Added by Layer 6

### Python
```
cockpit-aap-sdk>=0.6.0              # Already added in Layer 1
```

### TypeScript/React
```
@ruinosus/aap-bootstrap              # Manifest parsing, helpers
@ruinosus/aap-react                  # React hooks (useTool, useManifest)
zod                                   # Already likely present (CopilotKit dep)
```

---

## Testing Strategy for Layer 6

1. **Smoke test:** After each pattern, verify the app still starts (`python main.py`, `bun dev`)
2. **Unit test:** Verify ManifestInstance loads correctly
3. **Integration test:** Verify agent responds to a simple prompt
4. **HITL test:** Verify ActionCard renders and approve/reject works
5. **Regression test:** Run existing test suite to catch breakage

---

## Success Criteria

1. App starts and functions identically to before migration
2. All prompts come from `.aap/` manifest (not hardcoded)
3. Model can be changed by editing manifest YAML (not code)
4. HITL tools are defined in manifest and rendered from manifest schemas
5. Frontend wraps with ManifestProvider
6. No hardcoded prompts, model IDs, or tool definitions remain in source code
