# Plano de Migracao: Guardrails para AAP SDK v0.6.0

> **Pre-requisito:** cockpit-aap-sdk >= 0.6.0 publicado no PyPI.
> **Ref:** Resposta da equipe SDK em `aap-sdk/docs/responses/2026-03-24-guardrails-proposal-response.md`

**Goal:** Substituir os 4 middleware customizados de guardrails por manifests YAML + `create_guardrail_middleware()` do SDK v0.6.0, eliminando ~400 linhas de codigo Python.

---

## File Structure

```
Modified:
  pyproject.toml                           — bump cockpit-aap-sdk>=0.6.0
  agent/run_standalone.py                  — substituir middleware stack por create_guardrail_middleware()
  agent/middleware/__init__.py             — remover exports dos middleware substituidos
  tests/test_guardrails.py                — adaptar para usar assert_manifest_guardrail_*
  tests/test_guardrails_integration.py    — adaptar para novo middleware
  tests/test_guardrails_e2e.py            — adaptar para novo middleware

Created:
  .aap/secret-redaction/manifest.yaml     — kind: Guardrail (output: redact secrets)
  .aap/destructive-block/manifest.yaml    — kind: Guardrail (input: block rm -rf, DROP TABLE)
  .aap/unsafe-exec-block/manifest.yaml    — kind: Guardrail (input: block curl|sh, eval)
  .aap/skill-read-only/manifest.yaml      — kind: Guardrail (skill scope: code-review, security-scan)
  .aap/skill-docs-scope/manifest.yaml     — kind: Guardrail (skill scope: project-docs, doc-generator)
  .aap/skill-tests-scope/manifest.yaml    — kind: Guardrail (skill scope: test-generator)

Removed:
  agent/middleware/manifest_guardrails.py  — substituido por create_guardrail_middleware()
  agent/middleware/secret_filter.py        — substituido por kind: Guardrail com onFail: rewrite
  agent/middleware/skill_file_scope.py     — substituido por kind: Guardrail com scope/appliesTo
  agent/middleware/output_validator.py     — MANTER (validacao de JSON nao tem equivalente no SDK)
```

---

## Chunk 1: Guardrail Manifests

### Task 1: Criar manifests de guardrail em .aap/

- [ ] **Step 1: Criar `.aap/secret-redaction/manifest.yaml`**

```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: secret-redaction
  description: Redact API keys, tokens, and credentials from agent output
spec:
  appliesTo:
    kind: Module
  phase: output
  rules:
    - id: aws-key
      pattern: '(AKIA[0-9A-Z]{16})'
      onFail: rewrite
      replacement: '[REDACTED_AWS_KEY]'
      message: 'AWS access key redacted'
      category: secrets

    - id: openai-key
      pattern: '(sk-[a-zA-Z0-9\-]{20,})'
      onFail: rewrite
      replacement: '[REDACTED_OPENAI_KEY]'
      message: 'OpenAI API key redacted'
      category: secrets

    - id: github-token
      pattern: '(ghp_[a-zA-Z0-9]{36})'
      onFail: rewrite
      replacement: '[REDACTED_GITHUB_TOKEN]'
      message: 'GitHub token redacted'
      category: secrets

    - id: github-app-token
      pattern: '(ghs_[a-zA-Z0-9]{36})'
      onFail: rewrite
      replacement: '[REDACTED_GITHUB_APP_TOKEN]'
      message: 'GitHub App token redacted'
      category: secrets

    - id: anthropic-key
      pattern: '(sk-ant-[a-zA-Z0-9\-]{32,})'
      onFail: rewrite
      replacement: '[REDACTED_ANTHROPIC_KEY]'
      message: 'Anthropic key redacted'
      category: secrets

    - id: bearer-token
      pattern: '(Bearer\s+[a-zA-Z0-9\-._~+/]+=*)'
      onFail: rewrite
      replacement: '[REDACTED_BEARER]'
      message: 'Bearer token redacted'
      category: secrets

    - id: connection-string
      pattern: '((?:mongodb|postgres|mysql|redis)://[^\s]+)'
      onFail: rewrite
      replacement: '[REDACTED_CONNECTION_STRING]'
      message: 'Connection string redacted'
      category: secrets

    - id: generic-api-key
      pattern: '(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[''"][^''"]{8,}[''"]'
      onFail: rewrite
      replacement: '[REDACTED_CREDENTIAL]'
      message: 'Generic credential redacted'
      category: secrets
```

- [ ] **Step 2: Criar `.aap/destructive-block/manifest.yaml`**

```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: destructive-block
  description: Block destructive commands in agent input
spec:
  appliesTo:
    kind: Module
  phase: input
  rules:
    - id: destructive-commands
      pattern: '(rm\s+-rf\s+/|DROP\s+TABLE|DELETE\s+FROM\s+\w+\s*;|truncate\s+table)'
      onFail: block
      message: 'Destructive command detected and blocked'
      category: safety
```

- [ ] **Step 3: Criar `.aap/unsafe-exec-block/manifest.yaml`**

```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: unsafe-exec-block
  description: Block unsafe command execution patterns
spec:
  appliesTo:
    kind: Module
  phase: input
  rules:
    - id: pipe-to-shell
      pattern: '(curl\s+.*\|\s*sh|wget\s+.*\|\s*bash|eval\s*\()'
      onFail: block
      message: 'Unsafe command execution pattern detected'
      category: safety
```

- [ ] **Step 4: Criar `.aap/skill-read-only/manifest.yaml`**

```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: skill-read-only
  description: Enforce read-only mode for review skills
spec:
  appliesTo:
    kind: Skill
    when: "id in ('code-review', 'security-scan')"
  phase: input
  rules:
    - id: read-only
      category: scope
      onFail: block
      message: 'Review skills are read-only and cannot modify files'
  scope:
    allow_writes: false
```

- [ ] **Step 5: Criar `.aap/skill-docs-scope/manifest.yaml`**

```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: skill-docs-scope
  description: Restrict doc skills to .md files only
spec:
  appliesTo:
    kind: Skill
    when: "id in ('project-docs', 'doc-generator')"
  phase: input
  rules:
    - id: docs-scope
      category: scope
      onFail: block
      message: 'Doc skills can only modify documentation files'
  scope:
    allow_writes: true
    allowed_patterns:
      - '*.md'
      - 'docs/*.md'
      - 'docs/**/*.md'
    blocked_patterns:
      - '.github/*'
      - '.aap/*'
      - '*.py'
      - '*.yaml'
      - '*.yml'
```

- [ ] **Step 6: Criar `.aap/skill-tests-scope/manifest.yaml`**

```yaml
apiVersion: governance.cockpit.io/v1
kind: Guardrail
metadata:
  name: skill-tests-scope
  description: Restrict test-generator to test files only
spec:
  appliesTo:
    kind: Skill
    when: "id == 'test-generator'"
  phase: input
  rules:
    - id: tests-scope
      category: scope
      onFail: block
      message: 'Test generator can only create/modify test files'
  scope:
    allow_writes: true
    allowed_patterns:
      - 'tests/*.py'
      - 'test_*.py'
    blocked_patterns:
      - '.github/*'
      - '.aap/*'
      - 'agent/*'
```

- [ ] **Step 7: Verificar que os manifests carregam**

```bash
source .venv/bin/activate && python3 -c "
from cockpit_aap import ManifestInstance, resolve_guardrails
mi = ManifestInstance('open-swe')
guardrails = resolve_guardrails(mi)
for g in guardrails:
    print(f'  {g.metadata.name}: {len(g.spec.rules)} rules, phase={g.spec.phase}')
"
```

- [ ] **Step 8: Commit**

```bash
git add .aap/secret-redaction/ .aap/destructive-block/ .aap/unsafe-exec-block/ \
       .aap/skill-read-only/ .aap/skill-docs-scope/ .aap/skill-tests-scope/
git commit -m "feat: add 6 Guardrail manifests for SDK v0.6.0 migration"
```

---

## Chunk 2: Simplificar run_standalone.py

### Task 2: Substituir middleware stack por create_guardrail_middleware()

- [ ] **Step 1: Bump SDK version**

Em `pyproject.toml`, alterar:
```
"cockpit-aap-sdk>=0.6.0"
```

- [ ] **Step 2: Substituir bloco de middleware em run_standalone.py**

Substituir as ~50 linhas de montagem de middleware por:

```python
# Build guardrail middleware from manifest + SDK
from cockpit_aap import create_guardrail_middleware

mi = get_manifest()
guardrail_mw = create_guardrail_middleware(
    mi,
    agent_id=skill_id or "swe-coder",
    include_builtin_pii=True,
)
middleware = [guardrail_mw]

# Output validator (JSON structure) — keep as custom middleware
if skill_id and skill_id not in ("swe-coder", ""):
    from agent.middleware.output_validator import create_output_validator
    output_mw = create_output_validator(skill_id)
    if output_mw:
        middleware.append(output_mw)

# File scope — read from guardrail middleware scope metadata
if guardrail_mw and not guardrail_mw.allow_writes:
    logger.info("Skill %s is read-only (enforced by guardrail manifest)", skill_id)
```

- [ ] **Step 3: Verificar que run_standalone.py funciona**

```bash
source .venv/bin/activate && PYTHONPATH=. python -c "
import asyncio
from agent.run_standalone import run_agent
# Dry run check — just verify imports work
print('Imports OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml agent/run_standalone.py
git commit -m "feat: replace custom guardrail middleware with SDK create_guardrail_middleware"
```

---

## Chunk 3: Remover middleware substituidos

### Task 3: Limpar codigo customizado

- [ ] **Step 1: Remover arquivos substituidos**

```bash
git rm agent/middleware/manifest_guardrails.py
git rm agent/middleware/secret_filter.py
git rm agent/middleware/skill_file_scope.py
```

**MANTER:** `agent/middleware/output_validator.py` (validacao de JSON nao tem equivalente no SDK).

- [ ] **Step 2: Atualizar __init__.py**

Remover imports dos 3 arquivos deletados. Manter `output_validator`.

- [ ] **Step 3: Remover guardrails section do manifest.yaml**

Os patterns que estavam em `spec.guardrails` agora vivem nos manifests `kind: Guardrail`.
Remover a secao inteira de `guardrails:` do `.aap/open-swe/manifest.yaml`.

- [ ] **Step 4: Commit**

```bash
git add agent/middleware/ .aap/open-swe/manifest.yaml
git commit -m "refactor: remove custom guardrail middleware replaced by SDK v0.6.0"
```

---

## Chunk 4: Atualizar testes

### Task 4: Migrar testes para SDK

- [ ] **Step 1: Atualizar test_guardrails.py**

Substituir testes unitarios de `_is_path_allowed` e `redact_secrets` por
testes usando `assert_manifest_guardrail_blocks/passes`:

```python
from cockpit_aap import assert_manifest_guardrail_blocks, assert_manifest_guardrail_passes

async def test_destructive_command_blocked():
    await assert_manifest_guardrail_blocks(
        {"kind": "Module", "metadata": {"name": "open-swe"}, "spec": {}},
        input="rm -rf /",
        expected_category="safety",
    )

async def test_clean_input_passes():
    await assert_manifest_guardrail_passes(
        {"kind": "Module", "metadata": {"name": "open-swe"}, "spec": {}},
        input="git status",
    )

async def test_secret_redacted_in_output():
    await assert_manifest_guardrail_blocks(
        {"kind": "Module", "metadata": {"name": "open-swe"}, "spec": {}},
        output="Key: AKIAIOSFODNN7EXAMPLE",
        expected_category="secrets",
    )
```

- [ ] **Step 2: Atualizar test_guardrails_integration.py**

Substituir testes que usavam `create_skill_file_scope_middleware` e `secret_filter`
por testes usando `create_guardrail_middleware()` com os novos manifests.

- [ ] **Step 3: Atualizar test_guardrails_e2e.py**

Substituir montagem manual de middleware por `create_guardrail_middleware(mi)`.

- [ ] **Step 4: Rodar suite completa**

```bash
source .venv/bin/activate && python -m pytest tests/ -q
```

Expected: Todos os testes passam.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: migrate guardrail tests to SDK v0.6.0 assert helpers"
```

---

## Chunk 5: Atualizar documentacao

### Task 5: Atualizar docs

- [ ] **Step 1: Atualizar GUARDRAILS.md**

Simplificar de 3 camadas para 1:
- Remover secoes sobre manifest_guardrails.py, secret_filter.py, skill_file_scope.py
- Documentar a nova abordagem com `kind: Guardrail` manifests
- Manter secao "Como Criar um Novo Guardrail" — agora eh criar um YAML

- [ ] **Step 2: Atualizar ARCHITECTURE.md**

Atualizar secao de guardrails para refletir a nova arquitetura.

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: update guardrails documentation for SDK v0.6.0"
```

---

## Chunk 6: Validacao final

### Task 6: E2E + push

- [ ] **Step 1: Rodar suite completa**

```bash
source .venv/bin/activate && python -m pytest tests/ -q
source .env && python -m pytest tests/test_guardrails_e2e.py -m e2e -v
```

- [ ] **Step 2: Lint**

```bash
uv run ruff check . && uv run ruff format --check .
```

- [ ] **Step 3: Push**

```bash
git push
```

- [ ] **Step 4: Testar E2E no GitHub Actions**

Criar PR de teste e verificar que `run-review` funciona com o novo middleware.

---

## Resumo de Impacto

| Metrica | Antes | Depois |
|---------|-------|--------|
| Linhas de middleware Python | ~400 | ~20 |
| Arquivos de middleware | 4 | 1 (`output_validator.py`) |
| Guardrail manifests YAML | 0 | 6 |
| Dependencia SDK | v0.5.0 | v0.6.0 |
| Patterns configuraveis sem codigo | 4 (no manifest.yaml) | ~20 (em 6 manifests YAML) |
| PII detection | Manual (regex) | Built-in SDK |
| Telemetria | Nenhuma | OTEL spans automaticos |
