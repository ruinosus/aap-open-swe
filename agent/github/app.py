"""GitHub App installation token generation and GitHub token lookup utilities."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
import jwt
from langgraph.config import get_config
from langgraph_sdk import get_client
from langgraph_sdk.errors import NotFoundError

from ..server.encryption import decrypt_token

logger = logging.getLogger(__name__)

GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
GITHUB_APP_INSTALLATION_ID = os.environ.get("GITHUB_APP_INSTALLATION_ID", "")


def _generate_app_jwt() -> str:
    """Generate a short-lived JWT signed with the GitHub App private key."""
    now = int(time.time())
    payload = {
        "iat": now - 60,  # issued 60s ago to account for clock skew
        "exp": now + 540,  # expires in 9 minutes (max is 10)
        "iss": GITHUB_APP_ID,
    }
    private_key = GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_github_app_installation_token() -> str | None:
    """Exchange the GitHub App JWT for an installation access token.

    Returns:
        Installation access token string, or None if unavailable.
    """
    if not GITHUB_APP_ID or not GITHUB_APP_PRIVATE_KEY or not GITHUB_APP_INSTALLATION_ID:
        logger.debug("GitHub App env vars not fully configured, skipping app token")
        return None

    try:
        app_jwt = _generate_app_jwt()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{GITHUB_APP_INSTALLATION_ID}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json().get("token")
    except Exception:
        logger.exception("Failed to get GitHub App installation token")
        return None


_GITHUB_TOKEN_METADATA_KEY = "github_token_encrypted"

client = get_client()


def _read_encrypted_github_token(metadata: dict[str, Any]) -> str | None:
    encrypted_token = metadata.get(_GITHUB_TOKEN_METADATA_KEY)
    return encrypted_token if isinstance(encrypted_token, str) and encrypted_token else None


def _decrypt_github_token(encrypted_token: str | None) -> str | None:
    if not encrypted_token:
        return None

    return decrypt_token(encrypted_token)


def get_github_token() -> str | None:
    """Resolve a GitHub token from run metadata."""
    config = get_config()
    return _decrypt_github_token(_read_encrypted_github_token(config.get("metadata", {})))


async def get_github_token_from_thread(thread_id: str) -> tuple[str | None, str | None]:
    """Resolve a GitHub token from LangGraph thread metadata.

    Returns:
        A `(token, encrypted_token)` tuple. Either value may be `None`.
    """
    try:
        thread = await client.threads.get(thread_id)
    except NotFoundError:
        logger.debug("Thread %s not found while looking up GitHub token", thread_id)
        return None, None
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch thread metadata for %s", thread_id)
        return None, None

    encrypted_token = _read_encrypted_github_token((thread or {}).get("metadata", {}))
    token = _decrypt_github_token(encrypted_token)
    if token:
        logger.info("Found GitHub token in thread metadata for thread %s", thread_id)
    return token, encrypted_token
