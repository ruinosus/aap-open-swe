"""Manifest-driven configuration using AAP SDK v0.9.0.

All configuration reads go through ManifestInstance — the single source of truth.
"""

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
def get_model_id() -> str:
    return _mi().model_config(default_model="openai:gpt-4o")["model_id"]


def get_model_temperature() -> float:
    return _mi().model_config()["temperature"]


def get_model_max_tokens() -> int:
    return _mi().model_config()["max_tokens"]


# ── Agent ────────────────────────────────────
def get_default_agent_id() -> str:
    return _mi().artifact_value("open-swe.config.default_agent_id", default="swe-coder")


def get_agent_instruction(agent_id: str = "") -> str | None:
    return _mi().agent_instruction(agent_id or get_default_agent_id())


# ── Skills ───────────────────────────────────
def get_skills():
    return _mi().skills()


def get_skill(skill_id: str):
    return _mi().skill(skill_id)


def get_skill_instruction(skill_id: str) -> str | None:
    return _mi().skill_instruction(skill_id)


# ── Skill routing (via artifacts until SDK adds native fields) ──
def _skill_meta(skill_id: str, field: str, default: str = "") -> str:
    return _mi().artifact_value(f"open-swe.skills.{skill_id}.{field}", default=default)


def get_skills_by_category(category: str) -> list:
    return [s for s in _mi().skills() if _skill_meta(s.id, "category") == category]


def get_skill_category(skill_id: str) -> str:
    return _skill_meta(skill_id, "category")


def get_skill_branch(skill_id: str) -> str:
    return _skill_meta(skill_id, "branchPattern")


def is_structured_output_skill(skill_id: str) -> bool:
    return _skill_meta(skill_id, "outputFormat") == "structured"


def uses_default_tools(skill_id: str) -> bool:
    return _skill_meta(skill_id, "outputFormat", "freeform") == "freeform"


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
        "open-swe.config.allowed_github_orgs", env_fallback="ALLOWED_GITHUB_ORGS", default=""
    )
    return frozenset(o.strip().lower() for o in raw.split(",") if o.strip())


def get_sandbox_type() -> str:
    return _mi().artifact_value(
        "open-swe.config.sandbox_type", env_fallback="SANDBOX_TYPE", default="langsmith"
    )


def get_langgraph_url() -> str:
    return _mi().artifact_value(
        "open-swe.config.langgraph_url",
        env_fallback="LANGGRAPH_URL",
        default="http://localhost:2024",
    )


def get_output_truncation_limit() -> int:
    return int(_mi().artifact_value("open-swe.config.output_truncation_limit", default="60000"))


def get_tool_output_truncation() -> int:
    return int(_mi().artifact_value("open-swe.config.tool_output_truncation", default="500"))


def get_http_timeout() -> int:
    return int(_mi().artifact_value("open-swe.config.http_timeout", default="10"))


def get_pagination_limit() -> int:
    return int(_mi().artifact_value("open-swe.config.pagination_limit", default="100"))


def get_tool_call_log_frequency() -> int:
    return int(_mi().artifact_value("open-swe.config.tool_call_log_frequency", default="5"))


def get_pricing_api_url() -> str:
    return _mi().artifact_value(
        "open-swe.config.pricing_api_url", default="https://models.dev/api.json"
    )


def get_temp_path_prefix() -> str:
    return _mi().artifact_value(
        "open-swe.config.temp_path_prefix", default="/tmp/aap-sizing-target/"
    )


def get_default_bot_login() -> str:
    return _mi().artifact_value("open-swe.config.default_bot_login", default="github-actions")


def get_commit_message_template() -> str:
    return _mi().artifact_value(
        "open-swe.config.commit_message_template", default="fix: address issue #{issue_number}"
    )


# ── Prompt templates ──────────────────────────
def get_prompt_template(key: str) -> str:
    return _mi().artifact_value(f"open-swe.prompts.{key}", default="")


# ── Reply messages ───────────────────────────
def get_message(key: str, default: str = "") -> str:
    return _mi().artifact_value(f"open-swe.messages.{key}", default=default)


# ── Module identity ──────────────────────────
def get_module_name() -> str:
    m = _mi().manifest
    return getattr(getattr(m, "metadata", None), "name", "open-swe")


def get_module_display_name() -> str:
    m = _mi().manifest
    meta = getattr(m, "metadata", None)
    return (
        getattr(meta, "displayName", None) or getattr(meta, "display_name", None) or "AAP Open SWE"
    )


# ── Git identity ─────────────────────────────
def get_git_identity() -> tuple[str, str]:
    spec = _mi().manifest
    git = getattr(getattr(spec, "spec", None), "git", None) or {}
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
    spec = _mi().manifest
    git = getattr(getattr(spec, "spec", None), "git", None) or {}
    if not isinstance(git, dict):
        git = {"defaultBranchPattern": getattr(git, "defaultBranchPattern", "")}
    return git.get("defaultBranchPattern", "aap-open-swe/issue-{issue_number}")


# ── Formatting constants ─────────────────────
def get_formatting() -> dict:
    spec = _mi().manifest
    fmt = getattr(getattr(spec, "spec", None), "formatting", None)
    if fmt:
        return (
            fmt
            if isinstance(fmt, dict)
            else {
                "statusIcons": getattr(fmt, "statusIcons", {}),
                "severityIcons": getattr(fmt, "severityIcons", {}),
                "layerIcons": getattr(fmt, "layerIcons", {}),
                "miscIcons": getattr(fmt, "miscIcons", {}),
                "repoTypeLabels": getattr(fmt, "repoTypeLabels", {}),
            }
        )
    return {}


# ── Mappings ─────────────────────────────────
def get_linear_team_to_repo() -> dict:
    return _mi().artifact_json(
        "open-swe.mappings.linear_team_to_repo", env_fallback="LINEAR_TEAM_TO_REPO_JSON"
    )


def get_github_user_email_map() -> dict:
    return _mi().artifact_json(
        "open-swe.mappings.github_user_email", env_fallback="GITHUB_USER_EMAIL_MAP_JSON"
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
        "open-swe.config.default_repo_owner", env_fallback="DEFAULT_REPO_OWNER", default=""
    )


def get_default_repo_name() -> str:
    return _mi().artifact_value(
        "open-swe.config.default_repo_name", env_fallback="DEFAULT_REPO_NAME", default=""
    )


def get_slack_bot_user_id() -> str:
    return _mi().artifact_value(
        "open-swe.config.slack_bot_user_id", env_fallback="SLACK_BOT_USER_ID", default=""
    )


def get_slack_bot_username() -> str:
    return _mi().artifact_value(
        "open-swe.config.slack_bot_username", env_fallback="SLACK_BOT_USERNAME", default=""
    )


def get_slack_repo_owner() -> str:
    return (
        _mi().artifact_value(
            "open-swe.config.slack_repo_owner", env_fallback="SLACK_REPO_OWNER", default=""
        )
        or get_default_repo_owner()
    )


def get_slack_repo_name() -> str:
    return (
        _mi().artifact_value(
            "open-swe.config.slack_repo_name", env_fallback="SLACK_REPO_NAME", default=""
        )
        or get_default_repo_name()
    )
