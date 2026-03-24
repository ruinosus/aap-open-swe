# Launchpad Reference Files — Source of Truth for Migration

This document maps every file in the AAP SDK Launchpad that serves as reference
for the Layer 6 code integration patterns. Use this to find exact implementations.

**Launchpad root:** `/Users/jefferson.barnabe/projects/aap-sdk/apps/aap-launchpad/`

---

## Python Agent Files

| File | Lines | What it shows |
|------|-------|--------------|
| `agent/main.py` | 624 | **Complete agent setup** — ManifestInstance, instruction, model, middleware stack, tools, CopilotKit, conversation store, FastAPI endpoints |
| `agent/main.py:179-185` | | ManifestInstance initialization |
| `agent/main.py:229-240` | | Agent instruction from manifest with fallback |
| `agent/main.py:241-260` | | Model config from artifact with env var fallback |
| `agent/main.py:186-190` | | Guardrail middleware from manifest |
| `agent/main.py:269-319` | | Rules middleware from manifest |
| `agent/main.py:192-206` | | Cost middleware from manifest |
| `agent/main.py:331-384` | | Persona middleware from manifest |
| `agent/main.py:386-388` | | Skill middleware from manifest |
| `agent/main.py:403-412` | | Conversation store (Postgres/SQLite) |
| `agent/main.py:419-426` | | create_deep_agent with full middleware stack |
| `agent/main.py:435-443` | | LangGraph FastAPI endpoint registration |
| `agent/main.py:532-587` | | Conversation REST API (list/create/update/delete) |
| `agent/patched_copilotkit.py` | 144 | **StatefulCopilotKitMiddleware** — Pydantic fix + HITL state persistence |
| `agent/manifest_reader_tools.py` | 201 | Tools that let the agent read its own manifest (5 tools) |
| `agent/manifest_skill_tools.py` | 161 | Tools for lazy skill loading (3 tools) |
| `agent/manifest_skill_middleware.py` | ~100 | Middleware that injects skill instructions based on trigger keywords |
| `agent/persona_middleware.py` | ~80 | Middleware that injects persona context into system prompt |
| `agent/rules_engine.py` | ~60 | Rules evaluation engine |
| `agent/knowledge_tools.py` | ~60 | Knowledge base search tool |

---

## Frontend TypeScript/React Files

| File | Lines | What it shows |
|------|-------|--------------|
| `src/bootstrap/init.ts` | ~50 | **ManifestInstance + bootstrap** — sync and async manifest loading |
| `src/contexts/manifest-context.tsx` | ~30 | **ManifestProvider** — React context wrapping the app |
| `src/contexts/persona-context.tsx` | ~100 | **PersonaProvider** — persona switching, allowed tools/panels/skills |
| `src/contexts/tenant-context.tsx` | ~80 | **TenantProvider** — multi-tenancy context |
| `src/app/launchpad-client.tsx` | ~600 | **Main client component** — wraps everything with providers, configures CopilotKit |
| `src/app/launchpad-client.tsx:517-531` | | CopilotKitProvider + CopilotChatConfigurationProvider setup |
| `src/app/copilot-actions/use-hitl-actions.tsx` | 246 | **HITL hook registration** — buildHITLZodSchema + useHumanInTheLoop for each HITL tool |
| `src/app/copilot-actions/use-hitl-actions.tsx:15-33` | | Zod schema builder from manifest HITL parameters |
| `src/app/copilot-actions/use-hitl-actions.tsx:87-125` | | useHumanInTheLoop with manifest metadata + ActionCard |
| `src/components/action-card.tsx` | ~100 | **ActionCard component** — HITL approval UI with isLive guard |
| `src/app/api/copilotkit/[[...slug]]/route.ts` | ~210 | **CopilotKit runtime endpoint** — reads agents from manifest, creates skill adapter |
| `src/lib/session-artifacts.ts` | 87 | **Artifact persistence** — MCP JSON-RPC calls for read/write/update |
| `src/app/hooks/use-journey.ts` | 69 | **Client-side state** — localStorage with userId scoping |

---

## Manifest Files

| File | What it shows |
|------|--------------|
| `.aap/aap-launchpad/manifest.yaml` | **Complete manifest** — agents, artifacts, personas, skills, hitl, i18n, theme, connections, guardrails, telemetry, governance, recognition |
| `.aap/aap-launchpad/manifest.yaml:15-41` | Two agents (launchpad-agent + standard-agent) |
| `.aap/aap-launchpad/manifest.yaml:43-120` | Artifacts (config, state, content categories) |
| `.aap/aap-launchpad/manifest.yaml:122-180` | Personas (developer, product-owner, manager) |
| `.aap/aap-launchpad/manifest.yaml:182-250` | Skills with autoInvoke triggers and ghostTriggers |
| `.aap/aap-launchpad/manifest.yaml:357-439` | **HITL tools** (save_profile, propose_module, invite_github, show_feynman_card) |
| `.aap/aap-launchpad/manifest.yaml:441-480` | i18n (en + pt-BR) with welcome and prompt-pills |
| `.aap/aap-launchpad/manifest.yaml:482-520` | Theme presets (dark, light, gold) |
| `.aap/aap-launchpad/agents/launchpad-guide/instruction.md` | Full agent system prompt |
| `.aap/aap-launchpad/i18n/en.json` | English translations |
| `.aap/aap-launchpad/i18n/pt-BR.json` | Portuguese translations |

---

## MCP Server Files

| File | What it shows |
|------|--------------|
| `mcp-server/server.ts` | MCP server initialization from manifest |
| `mcp-server/tools/*.ts` | Tool implementations as default export handler functions |
| `.aap/launchpad-mcp/manifest.yaml` | MCP server manifest (tools, resources, prompts) |

---

## Key Import Patterns to Replicate

### Python
```python
# Core
from cockpit_aap import ManifestInstance
from cockpit_aap import create_guardrail_middleware
from cockpit_aap.runtime import GuardrailMiddleware
from cockpit_aap.conversation import create_conversation_store

# Helpers
from cockpit_aap.manifest.helpers import get_manifest_agent_instruction
from cockpit_aap.manifest.helpers import get_manifest_persona

# CopilotKit patch
from patched_copilotkit import StatefulCopilotKitMiddleware
```

### TypeScript
```typescript
// Bootstrap
import { ManifestInstance, bootstrapManifest } from "@ruinosus/aap-bootstrap";
import { getManifestAgentInstruction } from "@ruinosus/aap-bootstrap";
import { getManifestArtifactJSON } from "@ruinosus/aap-bootstrap";
import { getManifestSkills, createManifestSkillAdapter } from "@ruinosus/aap-bootstrap";
import { createAgentsFromManifest } from "@ruinosus/aap-bootstrap";

// React
import { ManifestProvider, useManifest } from "@/contexts/manifest-context";
import { PersonaProvider, usePersona } from "@/contexts/persona-context";

// CopilotKit
import { useHumanInTheLoop } from "@copilotkit/react-core/v2";
import { CopilotKit } from "@copilotkit/react-core";
```

---

## How to Use This Document

When implementing Layer 6 migration in a new session:

1. Read `2026-03-24-layer6-code-integration-design.md` for the 6 patterns
2. Use THIS document to find exact implementations in the Launchpad
3. Open the Launchpad files side-by-side as reference
4. Apply patterns one at a time, committing after each
5. Test after each pattern to catch breakage early
