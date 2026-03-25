"""Agent observability package.

Provides three composable layers for monitoring agent execution in GitHub Actions:

- **Layer A** (``gh_actions``): Structured log groups, annotations, and step summaries
  using GitHub Actions workflow commands (``::group::``, ``::notice::``, etc.).
- **Layer B** (``progress_reporter``): Live issue comment updates via the GitHub REST
  API — creates a comment on first call, then edits it as phases complete.
- **Layer C** (``streaming_callback``): LangChain ``BaseCallbackHandler`` that wraps
  every tool call and LLM invocation in a log group and feeds metrics to Layer B.

Typical usage::

    from agent.observability import AgentStreamingCallback, ProgressReporter, gh_group

    progress = ProgressReporter(github_token=token, repo_owner=owner,
                                repo_name=repo, issue_number=issue_num)
    callback = AgentStreamingCallback(progress_reporter=progress)

    progress.start_phase("Agent")
    result = await agent.ainvoke(input, config={"callbacks": [callback]})
    progress.finalize(success=True)
"""

from .gh_actions import gh_error, gh_group, gh_notice, gh_warning, write_step_summary
from .progress_reporter import ProgressReporter
from .streaming_callback import AgentStreamingCallback

__all__ = [
    "AgentStreamingCallback",
    "ProgressReporter",
    "gh_error",
    "gh_group",
    "gh_notice",
    "gh_warning",
    "write_step_summary",
]
