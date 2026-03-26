"""Manifest-driven configuration using AAP SDK v0.9.0."""

from cockpit_aap import ManifestInstance

_instance: ManifestInstance | None = None


def _mi() -> ManifestInstance:
    global _instance
    if _instance is None:
        _instance = ManifestInstance("open-swe")
    return _instance


# ── Manifest ─────────────────────────────────
def get_manifest():
    return _mi().manifest


# ── Model ────────────────────────────────────
def get_model_config() -> dict:
    """Returns {model_id, temperature, max_tokens} from manifest + env."""
    return _mi().model_config(default_model="openai:gpt-4o")


def get_model_id() -> str:
    return get_model_config()["model_id"]


def get_model_temperature() -> float:
    return get_model_config()["temperature"]


def get_model_max_tokens() -> int:
    return get_model_config()["max_tokens"]


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
    # Fallback: derive instruction from the skill object directly
    skill = mi.skill(skill_id)
    if skill is None:
        return None
    instr = getattr(skill, "instruction", None)
    if isinstance(instr, str):
        return instr
    return None


# ── Rules ────────────────────────────────────
def get_rules():
    return _mi().rules()


# ── Guardrails ───────────────────────────────
def get_guardrails(phase: str | None = None):
    return _mi().guardrails(phase=phase)


# ── Config values ────────────────────────────
def get_recursion_limit() -> int:
    return int(
        _mi().artifact_value(
            "open-swe.config.recursion_limit",
            env_fallback="OPEN_SWE_RECURSION_LIMIT",
            default="1000",
        )
    )


def get_allowed_github_orgs() -> frozenset[str]:
    raw = _mi().artifact_value(
        "open-swe.config.allowed_github_orgs",
        env_fallback="ALLOWED_GITHUB_ORGS",
        default="",
    )
    return frozenset(o.strip().lower() for o in raw.split(",") if o.strip())


def get_sandbox_type() -> str:
    return _mi().artifact_value(
        "open-swe.config.sandbox_type",
        env_fallback="SANDBOX_TYPE",
        default="langsmith",
    )


def get_langgraph_url() -> str:
    return _mi().artifact_value(
        "open-swe.config.langgraph_url",
        env_fallback="LANGGRAPH_URL",
        default="http://localhost:2024",
    )


# ── Mappings ─────────────────────────────────
def get_linear_team_to_repo() -> dict:
    return _mi().artifact_json(
        "open-swe.mappings.linear_team_to_repo",
        env_fallback="LINEAR_TEAM_TO_REPO_JSON",
    )


def get_github_user_email_map() -> dict:
    return _mi().artifact_json(
        "open-swe.mappings.github_user_email",
        env_fallback="GITHUB_USER_EMAIL_MAP_JSON",
    )


# ── Telemetry ────────────────────────────────
def is_telemetry_enabled() -> bool:
    return _mi().is_telemetry_enabled()


def get_telemetry_service_name() -> str:
    return _mi().telemetry_service_name(default="open-swe")


# ── i18n ─────────────────────────────────────
def get_i18n_message(key: str, locale: str = "en", **kwargs) -> str:
    return _mi().localized_content("i18n", key, locale) or key


# ── Connections ──────────────────────────────
def get_connection_endpoint(connection_id: str) -> str | None:
    conn = _mi().connection(connection_id)
    return conn.endpoint if conn else None


# ── Repo config (used by webapp) ─────────────
def get_default_repo_owner() -> str:
    return _mi().artifact_value(
        "open-swe.config.default_repo_owner",
        env_fallback="DEFAULT_REPO_OWNER",
        default="",
    )


def get_default_repo_name() -> str:
    return _mi().artifact_value(
        "open-swe.config.default_repo_name",
        env_fallback="DEFAULT_REPO_NAME",
        default="",
    )


def get_slack_bot_user_id() -> str:
    return _mi().artifact_value(
        "open-swe.config.slack_bot_user_id",
        env_fallback="SLACK_BOT_USER_ID",
        default="",
    )


def get_slack_bot_username() -> str:
    return _mi().artifact_value(
        "open-swe.config.slack_bot_username",
        env_fallback="SLACK_BOT_USERNAME",
        default="",
    )
