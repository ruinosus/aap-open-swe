"""GitHub Actions log formatting — groups, annotations, step summary."""

import os
from contextlib import contextmanager


@contextmanager
def gh_group(title: str):
    """Emit collapsible log group in GitHub Actions."""
    print(f"::group::{title}", flush=True)
    try:
        yield
    finally:
        print("::endgroup::", flush=True)


def gh_notice(msg: str) -> None:
    """Emit a notice annotation."""
    print(f"::notice::{msg}", flush=True)


def gh_warning(msg: str) -> None:
    """Emit a warning annotation."""
    print(f"::warning::{msg}", flush=True)


def gh_error(msg: str) -> None:
    """Emit an error annotation."""
    print(f"::error::{msg}", flush=True)


def write_step_summary(content: str) -> None:
    """Append markdown to the GitHub Actions step summary."""
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not path:
        return
    with open(path, "a") as f:
        f.write(content)
        f.write("\n")
