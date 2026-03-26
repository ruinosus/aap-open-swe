# AAP Open SWE

Fork customizado do [Open SWE](https://github.com/langchain-ai/open-swe) integrado com o **AAP SDK** (Avanade Agentic Platform).

Toda a configuracao do agente — model, system prompt, connections, rules, guardrails, telemetry e i18n — vive no manifest YAML (`.aap/open-swe/manifest.yaml`), nao no codigo Python.

## O que eh

Um **coding agent autonomo** que:
1. Recebe tarefas via **GitHub**, **Slack** ou **Linear** (webhooks)
2. Cria um **sandbox isolado** e clona o repositorio
3. Faz as mudancas de codigo necessarias
4. Roda linters e testes relacionados
5. Abre um **Pull Request** automaticamente
6. Comenta na issue/thread com o resumo

Alem disso, possui **5 skills dinamicas** que ativam automaticamente:
- **Code Review** — revisa PRs com inline comments automaticos
- **Security Scan** — detecta vulnerabilidades (OWASP Top 10, secrets, injection)
- **Doc Generator** — gera docstrings e documentacao de codigo
- **Test Generator** — gera testes unitarios para codigo sem cobertura
- **Project Docs** — atualiza os .md do projeto (README, ARCHITECTURE, etc.)

Built on [LangGraph](https://langchain-ai.github.io/langgraph/) + [Deep Agents](https://github.com/langchain-ai/deepagents).

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ruinosus/aap-open-swe.git
cd aap-open-swe

# 2. Install
uv venv && source .venv/bin/activate
uv sync --all-extras

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

# 4. Test
PYTHONPATH=. python test_mvp.py

# 5. Run
uv run langgraph dev --no-browser
```

## Configuration

All config lives in `.aap/open-swe/manifest.yaml`:

```yaml
apiVersion: cockpit.io/v1
kind: Module
metadata:
  name: open-swe
spec:
  agents:
    - id: swe-coder
      instruction: agents/swe-coder.md
  artifacts:
    - key: open-swe.config.model
      defaultValue: ''                    # Set via OPEN_SWE_MODEL env var
  connections: [...]                      # GitHub, Linear, Slack, LangSmith, LangGraph
  rules: [...]                            # 6 business rules
  guardrails: { input: [...], output: [...] }
  telemetry: { enabled: true, serviceName: open-swe }
  i18n: { defaultLocale: en, locales: { en, pt-BR } }
```

### Config Priority

1. **Manifest artifact** (if non-empty)
2. **Environment variable** (fallback)
3. **Hardcoded default** (last resort)

### Model Selection

```bash
# OpenAI
OPEN_SWE_MODEL=openai:gpt-4o
OPENAI_API_KEY=sk-...

# Anthropic
OPEN_SWE_MODEL=anthropic:claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...

# Google
OPEN_SWE_MODEL=google_genai:gemini-2.5-pro
GOOGLE_API_KEY=...
```

## AAP SDK Integration

The `agent/config/manifest.py` module provides typed accessor functions for manifest-driven configuration:

```python
from agent.aap_config import (
    get_model_id,           # "openai:gpt-4o"
    get_agent_instruction,  # 10K+ chars system prompt
    get_skills,             # [ManifestSkill(...), ...] — 5 skills
    get_rules,              # [ManifestRule(...), ...]
    get_guardrails,         # {"input": [...], "output": [...]}
    is_telemetry_enabled,   # True
)
```

If `cockpit-aap-sdk` is not installed, everything falls back to env vars seamlessly.

## Architecture

```
.aap/open-swe/manifest.yaml     <- Declarative config (agents, skills, rules, ...)
    |
agent/aap_config.py              <- Config layer (manifest -> env var -> default)
    |
    ├── agent/server.py          <- Deep Agent creation (LangGraph server mode)
    └── agent/run_standalone.py  <- Standalone runner (GitHub Actions mode)
            |
            ├── SKILL_ID env var -> skill instruction from manifest
            ├── Pydantic schemas -> ProviderStrategy (structured JSON output)
            └── review_poster.py -> GitHub Reviews API (inline PR comments)
    |
Sandbox (local/cloud)            <- Isolated code execution
```

## Skills

Skills sao declarativas — adicionar uma nova requer apenas um markdown + entrada no manifest. O runtime tambem diferencia skills por categoria e formato de saida para decidir entre ferramentas, output estruturado e publicacao em PR:

```
.aap/open-swe/skills/
  code-review.md       -> PR opened     -> inline comments
  security-scan.md     -> PR opened     -> inline comments
  doc-generator.md     -> PR merged     -> draft PR com docs
  test-generator.md    -> label added   -> draft PR com testes
  project-docs.md      -> PR merged     -> draft PR com .md updates
```

On-demand via comentario: `@aap-open-swe review`, `@aap-open-swe security`, `@aap-open-swe docs`, `@aap-open-swe tests`

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | Yes | LLM provider API key |
| `OPEN_SWE_MODEL` | No | Model ID (default: `anthropic:claude-opus-4-6`) |
| `SANDBOX_TYPE` | No | `langsmith`, `local`, `daytona`, `modal`, `runloop` |
| `GITHUB_APP_ID` | For GitHub trigger | GitHub App ID |
| `DEFAULT_REPO_OWNER` | No | Default GitHub org |

## Deployment

- **Local**: `uv run langgraph dev --no-browser` + ngrok
- **Docker**: `docker build -t aap-open-swe . && docker run --env-file .env -p 2024:2024 aap-open-swe`
- **LangGraph Cloud**: Push to GitHub, connect to LangGraph Cloud, set env vars

See [INSTALLATION.md](INSTALLATION.md) for the full setup guide.

## Credits

- [Open SWE](https://github.com/langchain-ai/open-swe) by LangChain (MIT License)
- [AAP SDK](https://github.com/ruinosus/aap-sdk) by Avanade


## Documentation

- `docs/superpowers/specs/2026-03-26-manifest-driven-runtime-design.md` descreve o runtime dirigido por manifest.
- `docs/superpowers/specs/2026-03-26-aap-sdk-skill-extensions.md` documenta os campos extras das skills usados pela compatibilidade atual.
