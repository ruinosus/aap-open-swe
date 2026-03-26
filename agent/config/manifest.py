"""Manifest-driven configuration.

Uses AAP SDK ManifestInstance with a compatibility shim for artifact_value
env_fallback/default (available in SDK v0.9.0+, shimmed for v0.6.0).
"""

import os

from cockpit_aap import ManifestInstance

_instance: ManifestInstance | None = None


def _mi() -> ManifestInstance:
    global _instance
    if _instance is None:
        _instance = ManifestInstance("open-swe")
    return _instance


def _artifact(key: str, env_fallback: str = "", default: str = "") -> str:
    """Read artifact with env fallback + default. Compat shim for SDK <0.9.0."""
    mi = _mi()
    # SDK v0.9.0+ has env_fallback/default params
    try:
        val = mi.artifact_value(key, env_fallback=env_fallback, default=default)
        if val:
            return str(val)
    except TypeError:
        # SDK <0.9.0: artifact_value(key) only
        val = mi.artifact_value(key)
        if val:
            return str(val)
    # Env fallback
    if env_fallback:
        env_val = os.getenv(env_fallback, "")
        if env_val:
            return env_val
    return default


def _artifact_json(key: str, env_fallback: str = "") -> dict:
    """Read JSON artifact with env fallback. Compat shim for SDK <0.9.0."""
    import json as _json

    mi = _mi()
    try:
        val = mi.artifact_json(key, env_fallback=env_fallback)
        if val and isinstance(val, dict):
            return val
    except TypeError:
        val = mi.artifact_json(key)
        if val and isinstance(val, dict):
            return val
    if env_fallback:
        raw = os.getenv(env_fallback, "")
        if raw:
            try:
                return _json.loads(raw)
            except (_json.JSONDecodeError, TypeError):
                pass
    return {}


# ── Manifest ─────────────────────────────────
def get_manifest():
    return _mi().manifest


# ── Model ────────────────────────────────────
def get_model_id() -> str:
    return _artifact("open-swe.config.model", "OPEN_SWE_MODEL", "openai:gpt-4o")


def get_model_temperature() -> float:
    return float(_artifact("open-swe.config.model_temperature", "OPEN_SWE_MODEL_TEMPERATURE", "0"))


def get_model_max_tokens() -> int:
    return int(_artifact("open-swe.config.model_max_tokens", "OPEN_SWE_MODEL_MAX_TOKENS", "20000"))


# ── Agent ────────────────────────────────────
def get_agent_instruction(agent_id: str = "swe-coder") -> str | None:
    return _mi().agent_instruction(agent_id)


# ── Skills ───────────────────────────────────
def get_skills():
    return _mi().skills()


def get_skill(skill_id: str):
    return _mi().skill(skill_id)


def get_skill_instruction(skill_id: str) -> str | None:
    mi = _mi()
    if hasattr(mi, "skill_instruction"):
        return mi.skill_instruction(skill_id)
    skill = mi.skill(skill_id)
    return skill.instruction if skill else None


# ── Skill routing (from manifest artifacts) ──
# SDK v0.6.0 ManifestSkill doesn't expose custom fields (category, outputFormat,
# branchPattern). We store these as artifacts until SDK supports them natively.
# See: docs/superpowers/specs/2026-03-26-aap-sdk-skill-extensions.md


def _skill_meta(skill_id: str, field: str, default: str = "") -> str:
    """Read skill metadata from artifacts: open-swe.skills.{skill_id}.{field}."""
    return _artifact(f"open-swe.skills.{skill_id}.{field}", default=default)


def get_skills_by_category(category: str) -> list:
    """Get all skills with the given category (review, pr, analysis, migration, utility)."""
    return [s for s in _mi().skills() if _skill_meta(s.id, "category") == category]


def get_skill_category(skill_id: str) -> str:
    """Get the category of a skill."""
    return _skill_meta(skill_id, "category")


def get_skill_branch(skill_id: str) -> str:
    """Get the branch pattern for a skill (empty string if no branch needed)."""
    return _skill_meta(skill_id, "branchPattern")


def is_structured_output_skill(skill_id: str) -> bool:
    """Check if a skill uses structured output (response_format)."""
    return _skill_meta(skill_id, "outputFormat") == "structured"


def uses_default_tools(skill_id: str) -> bool:
    """Check if a skill needs default tools (freeform output skills do)."""
    fmt = _skill_meta(skill_id, "outputFormat", "freeform")
    return fmt == "freeform"


# ── Git identity ─────────────────────────────
def get_git_identity() -> tuple[str, str]:
    """Returns (author_name, author_email) from spec.git."""
    spec = _mi().manifest
    git = {}
    if hasattr(spec, "spec"):
        git = getattr(spec.spec, "git", None) or {}
        if not isinstance(git, dict):
            git = {
                "authorName": getattr(git, "authorName", ""),
                "authorEmail": getattr(git, "authorEmail", ""),
            }
    return (
        git.get("authorName", "open-swe[bot]"),
        git.get("authorEmail", "open-swe@users.noreply.github.com"),
    )


def get_default_branch_pattern() -> str:
    """Get default branch pattern from spec.git."""
    spec = _mi().manifest
    git = {}
    if hasattr(spec, "spec"):
        git = getattr(spec.spec, "git", None) or {}
        if not isinstance(git, dict):
            git = {"defaultBranchPattern": getattr(git, "defaultBranchPattern", "")}
    return git.get("defaultBranchPattern", "aap-open-swe/issue-{issue_number}")


# ── Formatting constants ─────────────────────
def get_formatting() -> dict:
    """Get formatting constants (status icons, severity icons, layer icons)."""
    spec = _mi().manifest
    if hasattr(spec, "spec"):
        fmt = getattr(spec.spec, "formatting", None)
        if fmt:
            return (
                fmt
                if isinstance(fmt, dict)
                else {
                    "statusIcons": getattr(fmt, "statusIcons", {}),
                    "severityIcons": getattr(fmt, "severityIcons", {}),
                    "layerIcons": getattr(fmt, "layerIcons", {}),
                }
            )
    return {}


# ── Rules ────────────────────────────────────
def get_rules():
    return _mi().rules()


# ── Guardrails ───────────────────────────────
def get_guardrails(phase: str | None = None):
    mi = _mi()
    if hasattr(mi, "guardrails"):
        return mi.guardrails(phase=phase)
    raw = getattr(getattr(mi.manifest, "spec", None), "guardrails", []) or []
    if phase:
        return [g for g in raw if getattr(g, "phase", None) == phase]
    return list(raw)


# ── Config values ────────────────────────────
def get_recursion_limit() -> int:
    return int(_artifact("open-swe.config.recursion_limit", "OPEN_SWE_RECURSION_LIMIT", "1000"))


def get_allowed_github_orgs() -> frozenset[str]:
    raw = _artifact("open-swe.config.allowed_github_orgs", "ALLOWED_GITHUB_ORGS", "")
    return frozenset(o.strip().lower() for o in raw.split(",") if o.strip())


def get_sandbox_type() -> str:
    return _artifact("open-swe.config.sandbox_type", "SANDBOX_TYPE", "langsmith")


def get_langgraph_url() -> str:
    return _artifact("open-swe.config.langgraph_url", "LANGGRAPH_URL", "http://localhost:2024")


# ── Mappings ─────────────────────────────────
def get_linear_team_to_repo() -> dict:
    return _artifact_json("open-swe.mappings.linear_team_to_repo", "LINEAR_TEAM_TO_REPO_JSON")


def get_github_user_email_map() -> dict:
    return _artifact_json("open-swe.mappings.github_user_email", "GITHUB_USER_EMAIL_MAP_JSON")


# ── Telemetry ────────────────────────────────
def is_telemetry_enabled() -> bool:
    mi = _mi()
    if hasattr(mi, "is_telemetry_enabled"):
        return mi.is_telemetry_enabled()
    spec = mi.manifest
    return bool(getattr(getattr(spec, "spec", None), "telemetry", {}).get("enabled", False))


def get_telemetry_service_name() -> str:
    mi = _mi()
    if hasattr(mi, "telemetry_service_name"):
        return mi.telemetry_service_name(default="open-swe")
    spec = mi.manifest
    return getattr(getattr(spec, "spec", None), "telemetry", {}).get("service_name", "open-swe")


# ── i18n ─────────────────────────────────────
def get_i18n_message(key: str, locale: str = "en", **kwargs) -> str:
    return _mi().localized_content("i18n", key, locale) or key


# ── Connections ──────────────────────────────
def get_connection_endpoint(connection_id: str) -> str | None:
    conn = _mi().connection(connection_id)
    return conn.endpoint if conn else None


# ── Repo config (used by webapp) ─────────────
def get_default_repo_owner() -> str:
    return _artifact("open-swe.config.default_repo_owner", "DEFAULT_REPO_OWNER", "")


def get_default_repo_name() -> str:
    return _artifact("open-swe.config.default_repo_name", "DEFAULT_REPO_NAME", "")


def get_slack_bot_user_id() -> str:
    return _artifact("open-swe.config.slack_bot_user_id", "SLACK_BOT_USER_ID", "")


def get_slack_bot_username() -> str:
    return _artifact("open-swe.config.slack_bot_username", "SLACK_BOT_USERNAME", "")


def get_slack_repo_owner() -> str:
    return (
        _artifact("open-swe.config.slack_repo_owner", "SLACK_REPO_OWNER", "")
        or get_default_repo_owner()
    )


def get_slack_repo_name() -> str:
    return (
        _artifact("open-swe.config.slack_repo_name", "SLACK_REPO_NAME", "")
        or get_default_repo_name()
    )
