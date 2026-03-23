# AAP SDK — Proposta de Evolucao de Guardrails

**De:** Equipe AAP Open SWE
**Para:** Equipe Tecnica AAP SDK
**Data:** 2026-03-23

---

## Contexto

Durante a implementacao do sistema de guardrails no AAP Open SWE, identificamos gaps
entre o que o SDK oferece hoje e o que precisamos para garantir seguranca em agentes
autonomos rodando em producao (GitHub Actions, sem supervisao humana).

Hoje precisamos de **3 camadas separadas** para cobrir todos os cenarios. Idealmente,
o AAP SDK deveria unificar essas camadas em uma unica interface.

---

## O que o SDK ja oferece (v0.5.0)

| Feature | Status | Comentario |
|---------|--------|------------|
| `GuardrailMiddleware` | Funciona | Implementa `AgentMiddleware` do LangChain corretamente |
| `RegexGuardrailAdapter` | Funciona | PII detection built-in (email, CPF, phone, credit card, prompt injection) |
| `evaluate_input` / `evaluate_output` | Funciona | Interface async para checagem |
| `GuardrailDecision` | Funciona | Retorno estruturado com `allowed`, `action`, `violations` |
| `assert_guardrail_blocks` / `assert_guardrail_passes` | Funciona | Helpers de teste |
| Guardrails no `manifest.yaml` | **Declarados, mas nao integrados** | O manifest define patterns, mas o SDK nao os carrega automaticamente |

---

## O que precisamos e nao temos

### 1. Integracao automatica Manifest → GuardrailMiddleware

**Problema:** O manifest define guardrails com regex patterns, mas o `RegexGuardrailAdapter`
tem seus proprios patterns hardcoded e **nao le do manifest**. Tivemos que criar
`manifest_guardrails.py` manualmente para compilar os patterns do YAML.

**Proposta:**
```python
# O que queremos poder fazer:
from cockpit_aap import ManifestInstance, create_guardrail_middleware

mi = ManifestInstance("open-swe")
mw = create_guardrail_middleware(mi)  # Le input + output guardrails do manifest

# Ou diretamente:
mw = create_guardrail_middleware("open-swe")
```

**Implementacao sugerida:**
```python
def create_guardrail_middleware(manifest_or_id):
    """Factory que cria GuardrailMiddleware a partir do manifest."""
    if isinstance(manifest_or_id, str):
        mi = ManifestInstance(manifest_or_id)
    else:
        mi = manifest_or_id

    guardrails = mi.manifest.spec.guardrails

    # Combina patterns do manifest com os built-in do RegexGuardrailAdapter
    adapter = ManifestGuardrailAdapter(
        input_patterns=guardrails.get("input", []),
        output_patterns=guardrails.get("output", []),
        include_builtin_pii=True,  # Inclui email, CPF, etc.
    )

    return GuardrailMiddleware(
        guardrail=adapter,
        module_id=mi.manifest.metadata.name,
    )
```

### 2. `ManifestGuardrailAdapter` — Adapter que combina manifest + built-in

**Problema:** O `RegexGuardrailAdapter` nao aceita argumentos. Nao ha como
passar os patterns do manifest para ele.

**Proposta:** Novo adapter que:
- Le patterns do manifest (input/output)
- Inclui os patterns built-in do `RegexGuardrailAdapter` (PII, prompt injection)
- Permite adicionar patterns customizados via API

```python
class ManifestGuardrailAdapter(GuardrailPort):
    def __init__(self, input_patterns, output_patterns, include_builtin_pii=True):
        self.input_patterns = compile_patterns(input_patterns)
        self.output_patterns = compile_patterns(output_patterns)
        if include_builtin_pii:
            self.input_patterns += RegexGuardrailAdapter.DEFAULT_PATTERNS

    async def evaluate_input(self, text: str) -> GuardrailDecision: ...
    async def evaluate_output(self, text: str) -> GuardrailDecision: ...
```

### 3. Per-Skill Guardrails no Manifest

**Problema:** O manifest define guardrails globais, mas nao tem como definir
guardrails por skill. Tivemos que hardcodar `SKILL_SCOPE` em Python.

**Proposta:** Adicionar `guardrails` por skill no manifest:

```yaml
skills:
  - id: code-review
    instruction: skills/code-review.md
    guardrails:
      allow_writes: false  # Read-only skill

  - id: project-docs
    instruction: skills/project-docs.md
    guardrails:
      allow_writes: true
      allowed_patterns: ["*.md", "docs/*.md"]
      blocked_patterns: [".github/*", ".aap/*", "*.py"]

  - id: test-generator
    instruction: skills/test-generator.md
    guardrails:
      allow_writes: true
      allowed_patterns: ["tests/*.py"]
      blocked_patterns: ["agent/*", ".github/*"]
```

E o SDK criaria o middleware automaticamente:

```python
mi = ManifestInstance("open-swe")
skill = mi.skill("project-docs")
mw = skill.create_guardrail_middleware()  # Le guardrails da skill
```

### 4. Output Redaction (nao apenas Block)

**Problema:** O `GuardrailDecision` retorna `allowed=False` e `action="block"`,
mas nao tem mecanismo de **redacao** (substituir o secret por `[REDACTED]`).
No nosso caso, queremos que o output chegue ao GitHub mas com secrets removidos,
nao que o output inteiro seja bloqueado.

**Proposta:** Adicionar `action: "redact"` e campo `rewritten` no `GuardrailDecision`:

```yaml
# manifest.yaml
guardrails:
  output:
    - type: regex
      pattern: '(AKIA[0-9A-Z]{16})'
      action: redact          # Novo! Redacta em vez de bloquear
      replacement: '[REDACTED_AWS_KEY]'
      message: 'AWS key redacted from output'
```

```python
decision = await mw.check_output("Key: AKIAIOSFODNN7EXAMPLE")
# decision.action == "redact"
# decision.rewritten == "Key: [REDACTED_AWS_KEY]"
```

### 5. Guardrail Telemetria Integrada

**Problema:** O `RegexGuardrailAdapter` ja emite logs JSON estruturados quando
detecta violacoes, mas nao ha integracao com o sistema de telemetria do manifest
(`spec.telemetry`). Os eventos de guardrail deveriam ser spans OTEL automaticamente.

**Proposta:**
```python
# O GuardrailMiddleware deveria emitir spans quando:
# 1. Uma violacao e detectada
# 2. Uma redacao e feita
# 3. Um input e bloqueado

# Formato do span:
{
    "name": "guardrail.check",
    "attributes": {
        "guardrail.rule_id": "pii-email",
        "guardrail.action": "block",
        "guardrail.category": "pii",
        "guardrail.module_id": "open-swe",
        "guardrail.agent_id": "code-review",
    }
}
```

### 6. `assert_guardrail_*` com Manifest

**Problema:** Os helpers de teste `assert_guardrail_blocks` e `assert_guardrail_passes`
existem mas nao ha uma forma facil de testar guardrails do manifest.

**Proposta:**
```python
from cockpit_aap import ManifestInstance, assert_manifest_guardrail_blocks

mi = ManifestInstance("open-swe")

# Testa que os guardrails do manifest bloqueiam como esperado
assert_manifest_guardrail_blocks(mi, input="rm -rf /", expected_message="Destructive command")
assert_manifest_guardrail_blocks(mi, output="api_key='secret123'", expected_message="secret")
```

---

## Prioridades Sugeridas

| # | Feature | Impacto | Esforco | Prioridade |
|---|---------|---------|---------|------------|
| 1 | `create_guardrail_middleware(mi)` factory | Alto — elimina codigo customizado | Baixo | **P0** |
| 2 | `ManifestGuardrailAdapter` | Alto — unifica manifest + built-in | Medio | **P0** |
| 3 | Per-skill guardrails no manifest | Alto — elimina SKILL_SCOPE hardcoded | Medio | **P1** |
| 4 | Action `redact` + `rewritten` | Medio — necessario para output safety | Baixo | **P1** |
| 5 | Telemetria OTEL integrada | Medio — observabilidade | Medio | **P2** |
| 6 | `assert_manifest_guardrail_*` helpers | Baixo — DX improvement | Baixo | **P2** |

---

## O que construimos como workaround (removivel quando o SDK evoluir)

| Arquivo | O que faz | Substituido por |
|---------|-----------|-----------------|
| `agent/middleware/manifest_guardrails.py` | Compila patterns do manifest em middleware | `create_guardrail_middleware(mi)` (#1 + #2) |
| `agent/middleware/skill_file_scope.py` (SKILL_SCOPE dict) | Hardcoda regras de escopo por skill | Per-skill guardrails no manifest (#3) |
| `agent/middleware/secret_filter.py` | Redacao de secrets com patterns hardcoded | Action `redact` no manifest (#4) |
| `agent/middleware/output_validator.py` | Valida JSON estruturado | Pode virar regra no manifest ou manter como middleware |

Quando os itens P0 e P1 forem implementados no SDK, podemos remover ~400 linhas de
codigo customizado e substituir por ~10 linhas usando o SDK.

---

## Exemplo do Fluxo Ideal (pos-SDK)

```python
# run_standalone.py — fluxo ideal com SDK evoluido
from cockpit_aap import ManifestInstance, create_guardrail_middleware

mi = ManifestInstance("open-swe")

# Uma linha cria todos os guardrails (manifest + PII + per-skill)
guardrail_mw = create_guardrail_middleware(mi, skill_id=skill_id)

agent = create_deep_agent(
    model=model,
    system_prompt=system_prompt,
    middleware=[guardrail_mw],
    backend=sandbox,
)
```

Hoje precisamos de ~50 linhas para montar o mesmo middleware stack.
