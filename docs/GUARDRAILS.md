# Guardrails — Guia de Seguranca do Agente

Este documento explica como os guardrails protegem o agente durante a execucao de skills,
como testamos essa protecao, e como voce pode criar novos guardrails.

## Indice

1. [Visao Geral](#visao-geral)
2. [As 3 Camadas de Guardrails](#as-3-camadas-de-guardrails)
3. [Guardrails por Skill (Middleware)](#guardrails-por-skill-middleware)
4. [Como Funcionam no Pipeline](#como-funcionam-no-pipeline)
5. [Testes — 3 Camadas de Garantia](#testes--3-camadas-de-garantia)
6. [Como Criar um Novo Guardrail](#como-criar-um-novo-guardrail)
7. [Referencia de Arquivos](#referencia-de-arquivos)

---

## Visao Geral

O sistema de guardrails tem **3 camadas** que se complementam:

| Camada | Fonte | O que faz | Onde |
|--------|-------|-----------|------|
| **AAP SDK** | `cockpit-aap-sdk` | Detecta PII (email, CPF, telefone, cartao de credito) e prompt injection | `GuardrailMiddleware` + `RegexGuardrailAdapter` |
| **Manifest** | `manifest.yaml` | Regex patterns configuraveis (destructive commands, secrets, cloud keys) | `manifest_guardrails.py` |
| **Skill** | `agent/middleware/` | File scope, secret filter, output validator — por skill | Middleware customizados |

Todas as camadas sao **codigo deterministico** — nao dependem do LLM.

```
User Task
    |
    v
[wrap_model_call] AAP SDK GuardrailMiddleware  <-- PII detection (email, CPF, etc.)
    |
    v
[before_model] manifest_input_guardrail        <-- Blocks: rm -rf, DROP TABLE, curl|sh
    |
    v
[before_model] skill_file_scope                <-- Blocks writes fora do escopo da skill
    |
    v
LLM decide acao + chama tools
    |
    v
[after_agent] manifest_output_guardrail        <-- Redacta: api_key=, AKIA*, sk-*, ghp_*
    |
    v
[after_agent] secret_filter                    <-- Redacta patterns extras (Bearer, connection strings)
    |
    v
[after_agent] output_validator                 <-- Valida JSON antes de postar
    |
    v
Output (GitHub Reviews API / PR)
```

---

## As 3 Camadas de Guardrails

### Camada 1: AAP SDK (`GuardrailMiddleware`)

O [cockpit-aap-sdk](https://github.com/ruinosus/aap-sdk) fornece `GuardrailMiddleware`
que implementa a interface `AgentMiddleware` do LangChain nativamente. Ele usa o
`RegexGuardrailAdapter` que detecta PII automaticamente:

- Email addresses
- CPF numbers
- Phone numbers
- Credit card numbers
- Prompt injection patterns

```python
from cockpit_aap import GuardrailMiddleware, RegexGuardrailAdapter

adapter = RegexGuardrailAdapter()
mw = GuardrailMiddleware(guardrail=adapter, module_id="open-swe", agent_id="swe-coder")

# Passa direto para create_deep_agent(middleware=[mw, ...])
```

**Importante:** Este middleware roda para TODOS os agentes (swe-coder + skills).

### Camada 2: Manifest (`manifest.yaml`)

Os guardrails do manifest sao regex patterns declarativos:

```yaml
# .aap/open-swe/manifest.yaml
guardrails:
  input:
    - type: regex
      pattern: '(rm\s+-rf\s+/|DROP\s+TABLE|DELETE\s+FROM)'
      action: block
      message: 'Destructive command detected and blocked'

    - type: regex
      pattern: '(curl\s+.*\|\s*sh|wget\s+.*\|\s*bash|eval\s*\()'
      action: block
      message: 'Unsafe command execution pattern detected'

  output:
    - type: regex
      pattern: '(password|secret|api[_-]?key|token)\s*[:=]\s*[''"][^''"]{8,}'
      action: block
      message: 'Potential secret in output detected'

    - type: regex
      pattern: '(AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{32,}|ghp_[a-zA-Z0-9]{36})'
      action: block
      message: 'Cloud provider credential detected in output'
```

Esses patterns sao lidos por `agent/middleware/manifest_guardrails.py` e compilados
em middleware automaticamente. **Para adicionar um novo guardrail, basta editar o YAML.**

### Camada 3: Skill Middleware (customizados)

Middleware Python que aplicam logica mais complexa que regex:

---

## Os 3 Guardrails

### 1. File Scope (`skill_file_scope.py`)

**Tipo:** `@before_model` — executa antes de cada chamada ao LLM.

**O que faz:** Intercepta tool calls de `write_file` e `edit_file`. Se o
path do arquivo esta fora do escopo permitido para a skill, bloqueia a
operacao e retorna uma mensagem de erro para o agente.

**Regras por skill:**

| Skill | Pode escrever? | Permitido | Bloqueado |
|-------|---------------|-----------|-----------|
| `code-review` | Nao | — | Tudo (read-only) |
| `security-scan` | Nao | — | Tudo (read-only) |
| `project-docs` | Sim | `*.md`, `docs/*.md` | `.github/`, `.aap/`, `*.py`, `*.yaml` |
| `doc-generator` | Sim | `*.py`, `docs/*.md`, `README.md` | `.github/`, `.aap/`, `tests/` |
| `test-generator` | Sim | `tests/*.py`, `test_*.py` | `.github/`, `.aap/`, `agent/` |

**Exemplo de bloqueio nos logs:**
```
WARNING skill_file_scope: Skill project-docs blocked from writing to .github/workflows/agent.yml (outside scope)
```

**Configuracao:** As regras ficam no dict `SKILL_SCOPE` em `agent/middleware/skill_file_scope.py`.

---

### 2. Secret Filter (`secret_filter.py`)

**Tipo:** `@after_agent` — executa uma vez apos o agente terminar.

**O que faz:** Escaneia todas as `AIMessage` do output procurando patterns
de secrets. Substitui por `[REDACTED_*]` antes do output chegar ao GitHub.

**Patterns detectados:**

| Pattern | Exemplo | Regex |
|---------|---------|-------|
| AWS Access Key | `AKIAIOSFODNN7EXAMPLE` | `AKIA[0-9A-Z]{16}` |
| OpenAI API Key | `sk-proj-abc123...` | `sk-[a-zA-Z0-9\-]{20,}` |
| GitHub Token | `ghp_1234...` | `ghp_[a-zA-Z0-9]{36}` |
| GitHub App Token | `ghs_1234...` | `ghs_[a-zA-Z0-9]{36}` |
| Anthropic Key | `sk-ant-api03-...` | `sk-ant-[a-zA-Z0-9\-]{32,}` |
| Generic API Key | `api_key = 'value'` | `(api_key\|secret\|token\|password)\s*[:=]\s*['"][^'"]{8,}` |
| Bearer Token | `Bearer eyJhbG...` | `Bearer\s+[a-zA-Z0-9\-._~+/]+=*` |
| Connection String | `postgres://user:pass@host` | `(mongodb\|postgres\|mysql\|redis)://` |
| Private Key | `-----BEGIN PRIVATE KEY-----` | `-----BEGIN.*PRIVATE KEY-----` |

**Exemplo de redacao nos logs:**
```
WARNING secret_filter: Redacted 1 instance(s) of OpenAI API Key from agent output
```

---

### 3. Output Validator (`output_validator.py`)

**Tipo:** `@after_agent` — executa uma vez apos o agente terminar.

**O que faz:** Valida que o JSON de resposta do agente tem os campos
obrigatorios antes de ser postado no GitHub. Loga warnings se a validacao
falhar, mas **nao bloqueia** (para nao perder o output parcial).

**Campos obrigatorios por tipo:**

| Tipo | Campos | Validacao extra |
|------|--------|-----------------|
| `review` | `summary`, `score`, `comments` | Score deve ser `N/10` (1-10). Comments devem ter `file`, `line`, `message`, `severity`. |
| `pr` | `summary` | — |

**Exemplo nos logs:**
```
INFO output_validator: Skill code-review output validation passed (type=review)
WARNING output_validator: Skill code-review output validation failed (2 errors): Missing 'score'; Comment [0] missing 'severity'
```

---

## Como Funcionam no Pipeline

Os guardrails sao montados em `agent/run_standalone.py`:

```python
# run_standalone.py (simplificado)
middleware = []

# Camada 1: AAP SDK — sempre ativo (PII detection)
from cockpit_aap import GuardrailMiddleware, RegexGuardrailAdapter
sdk_guardrail = GuardrailMiddleware(guardrail=RegexGuardrailAdapter(), module_id="open-swe")
middleware.append(sdk_guardrail)

# Camada 2: Manifest — sempre ativo (regex patterns do YAML)
from agent.middleware.manifest_guardrails import create_manifest_input_guardrail, create_manifest_output_guardrail
manifest_input = create_manifest_input_guardrail()   # rm -rf, DROP TABLE, etc.
manifest_output = create_manifest_output_guardrail()  # api_key=, AKIA*, sk-*, ghp_*
if manifest_input:
    middleware.append(manifest_input)
if manifest_output:
    middleware.append(manifest_output)

# Camada 3: Skill middleware — apenas quando SKILL_ID esta definido
if skill_id:
    file_scope_mw = create_skill_file_scope_middleware(skill_id)
    if file_scope_mw:
        middleware.append(file_scope_mw)
    middleware.append(secret_filter)
    output_mw = create_output_validator(skill_id)
    if output_mw:
        middleware.append(output_mw)

agent = create_deep_agent(model=model, middleware=middleware, ...)
```

**Para o `swe-coder`:** As camadas 1 e 2 rodam (PII + manifest). A camada 3 (skill) nao.
**Para skills:** Todas as 3 camadas rodam.
**Para o modo LangGraph (`server.py`):** Usa os 4 middleware originais do Open SWE.

---

## Testes — 3 Camadas de Garantia

### Camada 1: Testes Unitarios (29 testes)

Testam a logica pura dos guardrails sem nenhuma dependencia externa.

```bash
pytest tests/test_guardrails.py -v
```

**O que testam:**
- `_is_path_allowed()` retorna True/False corretamente para cada skill
- `redact_secrets()` encontra e redacta cada pattern
- `validate_review_output()` detecta campos faltantes

**Exemplo:**
```python
def test_project_docs_blocks_github(self):
    scope = SKILL_SCOPE["project-docs"]
    assert not _is_path_allowed(".github/workflows/agent.yml", scope)
```

### Camada 2: Testes de Integracao (26 testes)

Simulam o pipeline real do LangChain — criam `AIMessage` com `tool_calls`,
passam pelo middleware, e verificam que a interceptacao acontece.

```bash
pytest tests/test_guardrails_integration.py -v
```

**O que testam:**
- Middleware recebe `AgentState` real com `AIMessage` e `tool_calls`
- `skill_file_scope.before_model()` retorna `ToolMessage` com "BLOCKED"
- `secret_filter.after_agent()` modifica `AIMessage` com conteudo redactado
- `output_validator.after_agent()` loga warnings para JSON invalido

**Exemplo:**
```python
def test_review_skill_blocks_write_file(self):
    """code-review skill must not write ANY file."""
    mw = create_skill_file_scope_middleware("code-review")

    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "write_file", "args": {"file_path": "README.md"}, "id": "tc_1"}],
    )
    state = {"messages": [HumanMessage(content="review"), ai_msg]}

    result = mw.before_model(state, runtime)

    assert result is not None
    assert "BLOCKED" in result["messages"][-1].content
```

### Camada 3: Testes E2E com LLM Real (3 testes)

Criam um agente real com model + middleware, enviam prompts, e verificam
que os guardrails funcionam em producao.

```bash
# Requer API key
source .env
pytest tests/test_guardrails_e2e.py -m e2e -v
```

**O que testam:**
1. **Review + JSON**: Agent com 3 middleware analisa codigo com SQL injection
   → retorna JSON valido com `summary`, `score`, `comments`
2. **Secret Filter**: Agent analisa codigo com API key → output nao contem a key
3. **File Scope**: Agent com code-review (read-only) recebe task → nao escreve arquivos

**Custo:** ~$0.03-0.05 por execucao (Claude Sonnet). Rodam em ~30 segundos.

### Resumo

| Camada | Testes | LLM? | Tempo | Custo | Comando |
|--------|--------|------|-------|-------|---------|
| Unitario | 29 | Nao | <1s | $0 | `pytest tests/test_guardrails.py` |
| Integracao | 26 | Nao | <1s | $0 | `pytest tests/test_guardrails_integration.py` |
| E2E | 3 | Sim | ~30s | ~$0.05 | `pytest -m e2e` |

---

## Como Criar um Novo Guardrail

### Passo 1: Escolha o tipo

| Tipo | Decorator | Quando executa | Use para |
|------|-----------|----------------|----------|
| `@before_model` | Antes de cada chamada ao LLM | Interceptar tool calls, validar input |
| `@after_agent` | Uma vez apos o agente terminar | Validar output, redactar dados, logging |
| `@before_agent` | Uma vez antes do agente iniciar | Validar input, rate limiting |

### Passo 2: Crie o arquivo

Crie `agent/middleware/meu_guardrail.py`:

```python
"""Descricao do que o guardrail faz."""

from typing import Any
from langchain.agents.middleware import AgentState, before_model  # ou after_agent
from langgraph.runtime import Runtime


@before_model
def meu_guardrail(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Implementacao do guardrail.

    Args:
        state: Estado atual do agente (messages, tool_calls, etc.)
        runtime: Runtime do LangGraph (acesso a store, config)

    Returns:
        None = nao modificar nada (prosseguir normalmente)
        dict = modificar o state (ex: injetar mensagem de erro)
    """
    messages = state.get("messages", [])
    if not messages:
        return None

    # Sua logica aqui...
    # Retorne None para permitir, ou dict para interceptar

    return None
```

**Para guardrails que dependem do skill_id**, use uma factory:

```python
def create_meu_guardrail(skill_id: str):
    """Cria guardrail configurado para uma skill especifica."""
    if skill_id not in ("skill-a", "skill-b"):
        return None  # Nao aplicavel para esta skill

    @before_model
    def meu_guardrail(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        # Use skill_id aqui via closure
        ...
        return None

    return meu_guardrail
```

### Passo 3: Registre no `__init__.py`

Edite `agent/middleware/__init__.py`:

```python
from .meu_guardrail import meu_guardrail  # ou create_meu_guardrail

__all__ = [
    ...,
    "meu_guardrail",
]
```

### Passo 4: Plugue no `run_standalone.py`

Edite `agent/run_standalone.py`, na secao de middleware:

```python
from agent.middleware.meu_guardrail import meu_guardrail  # ou create_meu_guardrail

# Na construcao do middleware stack:
middleware.append(meu_guardrail)

# Ou para factory:
meu_mw = create_meu_guardrail(skill_id)
if meu_mw:
    middleware.append(meu_mw)
```

### Passo 5: Escreva testes

**Teste unitario** em `tests/test_guardrails.py`:
```python
def test_meu_guardrail_bloqueia_x():
    from agent.middleware.meu_guardrail import minha_funcao
    assert minha_funcao("input_invalido") == False
```

**Teste de integracao** em `tests/test_guardrails_integration.py`:
```python
def test_meu_guardrail_intercepta_no_pipeline():
    from agent.middleware.meu_guardrail import meu_guardrail

    state = {"messages": [AIMessage(content="conteudo problematico")]}
    result = meu_guardrail.after_agent(state, FakeRuntime())

    assert result is not None  # Interceptou
```

**Teste E2E** em `tests/test_guardrails_e2e.py`:
```python
@pytest.mark.e2e
async def test_meu_guardrail_com_llm_real():
    agent = create_deep_agent(
        model=model,
        middleware=[meu_guardrail],
        ...
    )
    result = await agent.ainvoke({"messages": [...]})
    # Verificar que o guardrail agiu
```

### Passo 6: Rode os testes

```bash
# Unitarios + integracao (rapido, sem custo)
pytest tests/test_guardrails.py tests/test_guardrails_integration.py -v

# E2E com LLM real (requer .env com API key)
source .env && pytest -m e2e -v
```

---

## Referencia de Arquivos

| Arquivo | Tipo | Descricao |
|---------|------|-----------|
| `.aap/open-swe/manifest.yaml` | Config | Regex patterns declarativos (input + output guardrails) |
| `agent/aap_config.py` | Accessors | `get_input_guardrails()`, `get_output_guardrails()` — le do manifest |
| `agent/middleware/manifest_guardrails.py` | Camada 2 | Compila patterns do manifest em middleware LangChain |
| `agent/middleware/skill_file_scope.py` | Camada 3 | Controle de escopo de arquivos por skill |
| `agent/middleware/secret_filter.py` | Camada 3 | Redacao de secrets extras no output (Bearer, connection strings) |
| `agent/middleware/output_validator.py` | Camada 3 | Validacao de JSON estruturado |
| `agent/middleware/__init__.py` | Registry | Exporta todos os middleware |
| `agent/run_standalone.py` | Pipeline | Monta as 3 camadas de guardrails |
| `tests/test_guardrails.py` | Teste | 29 testes unitarios |
| `tests/test_guardrails_integration.py` | Teste | 26 testes de integracao |
| `tests/test_guardrails_e2e.py` | Teste | 3 testes E2E com LLM real |
