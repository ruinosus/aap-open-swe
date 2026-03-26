"""Sandbox creation, path resolution, and shared state."""

from __future__ import annotations

import asyncio
import logging
import os
import posixpath
import shlex
from collections.abc import Iterable
from typing import Any

from deepagents.backends.protocol import SandboxBackendProtocol
from langgraph.config import get_config

from agent.sandbox.providers.daytona import create_daytona_sandbox
from agent.sandbox.providers.langsmith import create_langsmith_sandbox
from agent.sandbox.providers.local import create_local_sandbox
from agent.sandbox.providers.modal import create_modal_sandbox
from agent.sandbox.providers.runloop import create_runloop_sandbox

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sandbox factory / creation (from agent.utils.sandbox)
# ---------------------------------------------------------------------------

SANDBOX_FACTORIES = {
    "langsmith": create_langsmith_sandbox,
    "daytona": create_daytona_sandbox,
    "modal": create_modal_sandbox,
    "runloop": create_runloop_sandbox,
    "local": create_local_sandbox,
}


def create_sandbox(sandbox_id: str | None = None):
    """Create or reconnect to a sandbox using the configured provider.

    The provider is selected via the SANDBOX_TYPE environment variable.
    Supported values: langsmith (default), daytona, modal, runloop, local.

    Args:
        sandbox_id: Optional existing sandbox ID to reconnect to.

    Returns:
        A sandbox backend implementing SandboxBackendProtocol.
    """
    sandbox_type = os.getenv("SANDBOX_TYPE", "langsmith")
    factory = SANDBOX_FACTORIES.get(sandbox_type)
    if not factory:
        supported = ", ".join(sorted(SANDBOX_FACTORIES))
        raise ValueError(f"Invalid sandbox type: {sandbox_type}. Supported types: {supported}")
    return factory(sandbox_id)


# ---------------------------------------------------------------------------
# Path resolution helpers (from agent.utils.sandbox_paths)
# ---------------------------------------------------------------------------

_WORK_DIR_CACHE_ATTR = "_open_swe_resolved_work_dir"
_PROVIDER_ATTR_NAMES = ("sandbox", "_sandbox")


def resolve_repo_dir(sandbox_backend: SandboxBackendProtocol, repo_name: str) -> str:
    """Resolve the repository directory for a sandbox backend."""
    if not repo_name:
        raise ValueError("repo_name must be a non-empty string")

    work_dir = resolve_sandbox_work_dir(sandbox_backend)
    return posixpath.join(work_dir, repo_name)


async def aresolve_repo_dir(sandbox_backend: SandboxBackendProtocol, repo_name: str) -> str:
    """Async wrapper around resolve_repo_dir for use in event-loop code."""
    return await asyncio.to_thread(resolve_repo_dir, sandbox_backend, repo_name)


def resolve_sandbox_work_dir(sandbox_backend: SandboxBackendProtocol) -> str:
    """Resolve a writable base directory for repository operations."""
    cached_work_dir = getattr(sandbox_backend, _WORK_DIR_CACHE_ATTR, None)
    if isinstance(cached_work_dir, str) and cached_work_dir:
        return cached_work_dir

    checked_candidates: list[str] = []
    for candidate in _iter_work_dir_candidates(sandbox_backend):
        checked_candidates.append(candidate)
        if _is_writable_directory(sandbox_backend, candidate):
            _cache_work_dir(sandbox_backend, candidate)
            return candidate

    msg = "Failed to resolve a writable sandbox work directory"
    if checked_candidates:
        msg = f"{msg}. Candidates checked: {', '.join(checked_candidates)}"
    raise RuntimeError(msg)


async def aresolve_sandbox_work_dir(sandbox_backend: SandboxBackendProtocol) -> str:
    """Async wrapper around resolve_sandbox_work_dir for use in event-loop code."""
    return await asyncio.to_thread(resolve_sandbox_work_dir, sandbox_backend)


def _iter_work_dir_candidates(
    sandbox_backend: SandboxBackendProtocol,
) -> Iterable[str]:
    seen: set[str] = set()

    for candidate in _iter_provider_paths(sandbox_backend, "get_work_dir"):
        if candidate not in seen:
            seen.add(candidate)
            yield candidate

    shell_work_dir = _resolve_shell_path(sandbox_backend, "pwd")
    if shell_work_dir and shell_work_dir not in seen:
        seen.add(shell_work_dir)
        yield shell_work_dir

    for candidate in _iter_provider_paths(
        sandbox_backend,
        "get_user_home_dir",
        "get_user_root_dir",
    ):
        if candidate not in seen:
            seen.add(candidate)
            yield candidate

    shell_home_dir = _resolve_shell_path(sandbox_backend, "printf '%s' \"$HOME\"")
    if shell_home_dir and shell_home_dir not in seen:
        seen.add(shell_home_dir)
        yield shell_home_dir


def _iter_provider_paths(
    sandbox_backend: SandboxBackendProtocol,
    *method_names: str,
) -> Iterable[str]:
    for provider in _iter_path_providers(sandbox_backend):
        for method_name in method_names:
            path = _call_path_method(provider, method_name)
            if path:
                yield path


def _iter_path_providers(sandbox_backend: SandboxBackendProtocol) -> Iterable[Any]:
    yield sandbox_backend
    for attr_name in _PROVIDER_ATTR_NAMES:
        provider = getattr(sandbox_backend, attr_name, None)
        if provider is not None:
            yield provider


def _call_path_method(provider: Any, method_name: str) -> str | None:
    method = getattr(provider, method_name, None)
    if not callable(method):
        return None

    try:
        return _normalize_path(method())
    except Exception:
        logger.debug("Failed to call %s on %s", method_name, type(provider).__name__, exc_info=True)
        return None


def _resolve_shell_path(
    sandbox_backend: SandboxBackendProtocol,
    command: str,
) -> str | None:
    result = sandbox_backend.execute(command)
    if result.exit_code != 0:
        return None
    return _normalize_path(result.output)


def _normalize_path(raw_path: str | None) -> str | None:
    if raw_path is None:
        return None

    path = raw_path.strip()
    if not path or not path.startswith("/"):
        return None

    return posixpath.normpath(path)


def _is_writable_directory(
    sandbox_backend: SandboxBackendProtocol,
    directory: str,
) -> bool:
    safe_directory = shlex.quote(directory)
    result = sandbox_backend.execute(f"test -d {safe_directory} && test -w {safe_directory}")
    return result.exit_code == 0


def _cache_work_dir(sandbox_backend: SandboxBackendProtocol, work_dir: str) -> None:
    try:
        setattr(sandbox_backend, _WORK_DIR_CACHE_ATTR, work_dir)
    except Exception:
        logger.debug("Failed to cache sandbox work dir on %s", type(sandbox_backend).__name__)


# ---------------------------------------------------------------------------
# Shared sandbox state (from agent.utils.sandbox_state)
# ---------------------------------------------------------------------------

# Thread ID -> SandboxBackend mapping, shared between server.py and middleware
SANDBOX_BACKENDS: dict[str, Any] = {}


async def get_sandbox_id_from_metadata(thread_id: str) -> str | None:
    """Fetch sandbox_id from thread metadata."""
    try:
        config = get_config()
    except Exception:
        logger.exception("Failed to read thread metadata for sandbox")
        return None
    return config.get("metadata", {}).get("sandbox_id")


async def get_sandbox_backend(thread_id: str) -> Any | None:
    """Get sandbox backend from cache, or connect using thread metadata."""
    sandbox_backend = SANDBOX_BACKENDS.get(thread_id)
    if sandbox_backend:
        return sandbox_backend

    sandbox_id = await get_sandbox_id_from_metadata(thread_id)
    if not sandbox_id:
        raise ValueError(f"Missing sandbox_id in thread metadata for {thread_id}")

    sandbox_backend = await asyncio.to_thread(create_sandbox, sandbox_id)
    SANDBOX_BACKENDS[thread_id] = sandbox_backend
    return sandbox_backend


def get_sandbox_backend_sync(thread_id: str) -> Any | None:
    """Sync wrapper for get_sandbox_backend."""
    return asyncio.run(get_sandbox_backend(thread_id))
