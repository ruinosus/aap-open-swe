"""GitHub Actions log formatting — groups, annotations, step summary."""

import os
from contextlib import contextmanager


def _sanitize(text: str) -> str:
    """Strip newlines and escape :: sequences to prevent GH Actions log injection."""
    return text.replace("\n", " ").replace("\r", " ").replace("::", ":\u200b:")


@contextmanager
def gh_group(title: str):
    """Emit collapsible log group in GitHub Actions."""
    print(f"::group::{_sanitize(title)}", flush=True)
    try:
        yield
    finally:
        print("::endgroup::", flush=True)


def gh_notice(msg: str) -> None:
    """Emit a notice annotation."""
    print(f"::notice::{_sanitize(msg)}", flush=True)


def gh_warning(msg: str) -> None:
    """Emit a warning annotation."""
    print(f"::warning::{_sanitize(msg)}", flush=True)


def gh_error(msg: str) -> None:
    """Emit an error annotation."""
    print(f"::error::{_sanitize(msg)}", flush=True)


def write_step_summary(content: str) -> None:
    """Append markdown to the GitHub Actions step summary."""
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not path:
        return
    with open(path, "a") as f:
        f.write(content)
        f.write("\n")
