# AAP SDK — Suggestions & Missing Features

**From:** aap-open-swe team
**SDK Version:** v0.8.0 (Python)
**Date:** 2026-03-25

These are features we need in the SDK that are currently implemented as custom
code in aap-open-swe. Adding them to the SDK would eliminate boilerplate across
all SDK consumers.

---

## 1. `artifact_value()` with env var fallback and default

**Priority:** High
**Impact:** Eliminates 22 repetitive accessor functions

**Current (our code):**
```python
def get_model_id():
    val = mi.artifact_value("open-swe.config.model")
    if val:
        return val
    return os.getenv("OPEN_SWE_MODEL", "anthropic:claude-opus-4-6")
```

**Suggested SDK API:**
```python
val = mi.artifact_value(
    "open-swe.config.model",
    env_fallback="OPEN_SWE_MODEL",
    default="anthropic:claude-opus-4-6",
)
```

Every consumer of ManifestInstance needs this 3-tier fallback pattern
(manifest → env var → hardcoded default). It's the most common pattern
in any app that uses the SDK.

---

## 2. Model config helpers

**Priority:** High
**Impact:** Every app needs these

Every app that uses the SDK needs model ID, temperature, and max_tokens.
These are currently read via `artifact_value()` with manual type conversion.

**Suggested SDK API:**
```python
mi.model_id(default="openai:gpt-4o")         # str
mi.model_temperature(default=0.0)             # float
mi.model_max_tokens(default=20000)            # int
```

Or a single method:
```python
config = mi.model_config()
# config.model_id, config.temperature, config.max_tokens
```

---

## 3. `skill_instruction(skill_id)` method

**Priority:** Medium
**Impact:** Common pattern, currently requires two calls

**Current:**
```python
skill = mi.skill(skill_id)
instruction = skill.instruction if skill else None
```

**Suggested SDK API:**
```python
instruction = mi.skill_instruction(skill_id)  # Returns str | None
```

This is analogous to `mi.agent_instruction(agent_id)` which already exists.

---

## 4. Guardrails getter

**Priority:** Medium
**Impact:** Direct spec access feels wrong

**Current:**
```python
guardrails = mi.manifest.spec.guardrails  # Direct spec access
input_guardrails = [g for g in guardrails if g.phase == "input"]
```

**Suggested SDK API:**
```python
all_guardrails = mi.guardrails()
input_guardrails = mi.guardrails(phase="input")
output_guardrails = mi.guardrails(phase="output")
```

The SDK has `create_guardrail_middleware()` which is great for runtime,
but sometimes you need to inspect guardrails without creating middleware
(e.g., for documentation, reporting, or UI display).

---

## 5. Telemetry getters

**Priority:** Low
**Impact:** Minor convenience

**Current:**
```python
enabled = mi.manifest.spec.telemetry.get("enabled", False)
service_name = mi.manifest.spec.telemetry.get("service_name", "default")
```

**Suggested SDK API:**
```python
mi.is_telemetry_enabled()       # bool
mi.telemetry_service_name()     # str
mi.telemetry_config()           # dict with all telemetry settings
```

---

## 6. `artifact_json()` with env var fallback

**Priority:** Medium
**Impact:** Needed for mapping/config artifacts stored as JSON

**Current:**
```python
def _artifact_json(key, env_var):
    val = mi.artifact_json(key)
    if val:
        return val
    raw = os.getenv(env_var, "")
    if raw:
        return json.loads(raw)
    return {}
```

**Suggested SDK API:**
```python
val = mi.artifact_json("open-swe.mappings.linear_team_to_repo", env_fallback="LINEAR_TEAM_TO_REPO_JSON")
```

Same principle as suggestion #1 but for JSON artifacts.

---

## Summary

| # | Feature | Priority | Lines saved |
|---|---------|----------|-------------|
| 1 | `artifact_value()` with env fallback + default | High | ~150 |
| 2 | Model config helpers | High | ~30 |
| 3 | `skill_instruction(skill_id)` | Medium | ~10 |
| 4 | `guardrails()` getter | Medium | ~15 |
| 5 | Telemetry getters | Low | ~10 |
| 6 | `artifact_json()` with env fallback | Medium | ~20 |

Total: ~235 lines of boilerplate eliminated if all 6 are implemented.
