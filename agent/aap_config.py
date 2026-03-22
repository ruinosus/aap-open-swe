"""AAP SDK manifest-driven configuration layer for Open SWE.

Loads configuration from .aap/open-swe/manifest.yaml using ManifestInstance.
Falls back to environment variables when manifest values are empty.
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)

try:
    from cockpit_aap import ManifestInstance

    _HAS_AAP_SDK = True
except ImportError:
    _HAS_AAP_SDK = False
    logger.info("cockpit-aap-sdk not installed, falling back to env vars only")


@lru_cache(maxsize=1)
def _load_manifest() -> "ManifestInstance | None":
    if not _HAS_AAP_SDK:
        return None
    try:
        instance = ManifestInstance("open-swe", cwd=_ROOT_DIR)
        logger.info("Loaded AAP manifest from %s", instance.path)
        return instance
    except Exception:
        logger.warning("Failed to load AAP manifest, falling back to env vars", exc_info=True)
        return None


def get_manifest() -> "ManifestInstance | None":
    return _load_manifest()


def _artifact(key: str, env_var: str = "", default: str = "") -> str:
    """Get config value: manifest artifact first, then env var, then default."""
    mi = get_manifest()
    if mi is not None:
        val = mi.artifact_value(key)
        if val and val.strip():
            return val
    if env_var:
        val = os.environ.get(env_var, "")
        if val:
            return val
    return default


def _artifact_json(key: str, env_var: str = "", default: dict | list | None = None):
    """Get JSON config value from manifest artifact or env var."""
    raw = _artifact(key, env_var, "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid JSON in %s, using default", key)
    return default if default is not None else {}


def _artifact_int(key: str, env_var: str = "", default: int = 0) -> int:
    raw = _artifact(key, env_var, "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


# ─── Model Configuration ────────────────────────────────────

def get_model_id() -> str:
    return _artifact("open-swe.config.model", "OPEN_SWE_MODEL", "anthropic:claude-opus-4-6")


def get_model_temperature() -> float:
    raw = _artifact("open-swe.config.model_temperature", "OPEN_SWE_MODEL_TEMPERATURE", "0")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def get_model_max_tokens() -> int:
    return _artifact_int("open-swe.config.model_max_tokens", "OPEN_SWE_MODEL_MAX_TOKENS", 20000)


# ─── Repository Configuration ───────────────────────────────

def get_default_repo_owner() -> str:
    return _artifact("open-swe.config.default_repo_owner", "DEFAULT_REPO_OWNER", "")


def get_default_repo_name() -> str:
    return _artifact("open-swe.config.default_repo_name", "DEFAULT_REPO_NAME", "")


def get_slack_repo_owner() -> str:
    return _artifact("open-swe.config.slack_repo_owner", "SLACK_REPO_OWNER", "") or get_default_repo_owner()


def get_slack_repo_name() -> str:
    return _artifact("open-swe.config.slack_repo_name", "SLACK_REPO_NAME", "") or get_default_repo_name()


# ─── Slack Configuration ────────────────────────────────────

def get_slack_bot_user_id() -> str:
    return _artifact("open-swe.config.slack_bot_user_id", "SLACK_BOT_USER_ID", "")


def get_slack_bot_username() -> str:
    return _artifact("open-swe.config.slack_bot_username", "SLACK_BOT_USERNAME", "")


# ─── GitHub Configuration ───────────────────────────────────

def get_allowed_github_orgs() -> frozenset[str]:
    raw = _artifact("open-swe.config.allowed_github_orgs", "ALLOWED_GITHUB_ORGS", "")
    if not raw:
        return frozenset()
    return frozenset(org.strip().lower() for org in raw.split(",") if org.strip())


# ─── Sandbox Configuration ──────────────────────────────────

def get_sandbox_type() -> str:
    return _artifact("open-swe.config.sandbox_type", "SANDBOX_TYPE", "langsmith")


# ─── LangGraph Configuration ────────────────────────────────

def get_langgraph_url() -> str:
    return _artifact(
        "open-swe.config.langgraph_url",
        "LANGGRAPH_URL",
        os.environ.get("LANGGRAPH_URL_PROD", "http://localhost:2024"),
    )


def get_recursion_limit() -> int:
    return _artifact_int("open-swe.config.recursion_limit", "OPEN_SWE_RECURSION_LIMIT", 1000)


# ─── Mapping Configuration ──────────────────────────────────

def get_linear_team_to_repo() -> dict:
    return _artifact_json("open-swe.mappings.linear_team_to_repo", "LINEAR_TEAM_TO_REPO_JSON", {})


def get_github_user_email_map() -> dict:
    return _artifact_json("open-swe.mappings.github_user_email", "GITHUB_USER_EMAIL_MAP_JSON", {})


# ─── Agent Instruction ──────────────────────────────────────

def get_agent_instruction() -> str:
    mi = get_manifest()
    if mi is not None:
        try:
            return mi.agent_instruction("swe-coder")
        except Exception:
            logger.warning("Failed to get agent instruction from manifest", exc_info=True)
    return ""


# ─── i18n ────────────────────────────────────────────────────

def get_i18n_message(key: str, locale: str = "", **kwargs) -> str:
    mi = get_manifest()
    if mi is None:
        return key

    effective_locale = locale or "en"
    try:
        content = mi.localized_content("resources", key, locale=effective_locale)
        if content and isinstance(content, str):
            return content.format(**kwargs) if kwargs else content
    except Exception:
        pass
    return key


# ─── Connections ─────────────────────────────────────────────

def get_connection_endpoint(connection_id: str) -> str:
    mi = get_manifest()
    if mi is not None:
        try:
            conn = mi.connection(connection_id)
            if conn and hasattr(conn, "endpoint"):
                return conn.endpoint
        except Exception:
            pass
    return ""


# ─── Telemetry ───────────────────────────────────────────────

def is_telemetry_enabled() -> bool:
    mi = get_manifest()
    if mi is not None:
        try:
            t = mi.manifest.spec.telemetry
            if t is not None:
                return bool(t.enabled)
        except Exception:
            pass
    return False


def get_telemetry_service_name() -> str:
    mi = get_manifest()
    if mi is not None:
        try:
            t = mi.manifest.spec.telemetry
            if t is not None and t.service_name:
                return t.service_name
        except Exception:
            pass
    return "open-swe"


# ─── Rules ───────────────────────────────────────────────────

def get_rules() -> list:
    mi = get_manifest()
    if mi is not None:
        try:
            return mi.manifest.spec.rules or []
        except Exception:
            pass
    return []


def get_rules_for_agent(agent_id: str = "swe-coder") -> list:
    return [
        r for r in get_rules()
        if not r.applies_to or agent_id in (r.applies_to or [])
    ]


# ─── Guardrails ─────────────────────────────────────────────

def get_guardrails() -> dict:
    mi = get_manifest()
    if mi is not None:
        try:
            g = mi.manifest.spec.guardrails
            if g and isinstance(g, dict):
                return g
        except Exception:
            pass
    return {"input": [], "output": []}


def get_input_guardrails() -> list:
    return get_guardrails().get("input", [])


def get_output_guardrails() -> list:
    return get_guardrails().get("output", [])
