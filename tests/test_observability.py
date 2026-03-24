import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

from agent.observability.gh_actions import (
    gh_error,
    gh_group,
    gh_notice,
    gh_warning,
    write_step_summary,
)
from agent.observability.progress_reporter import ProgressReporter
from agent.observability.streaming_callback import AgentStreamingCallback


class TestGhGroup:
    def test_group_prints_markers(self, capsys):
        with gh_group("Layer 1 — Core"):
            print("doing work")
        out = capsys.readouterr().out
        assert "::group::Layer 1 — Core" in out
        assert "doing work" in out
        assert "::endgroup::" in out

    def test_nested_groups(self, capsys):
        with gh_group("Outer"):
            with gh_group("Inner"):
                print("nested")
        out = capsys.readouterr().out
        assert out.count("::group::") == 2
        assert out.count("::endgroup::") == 2


class TestAnnotations:
    def test_notice(self, capsys):
        gh_notice("All tests passed")
        assert "::notice::All tests passed" in capsys.readouterr().out

    def test_warning(self, capsys):
        gh_warning("No HITL tools found")
        assert "::warning::No HITL tools found" in capsys.readouterr().out

    def test_error(self, capsys):
        gh_error("Push failed")
        assert "::error::Push failed" in capsys.readouterr().out


class TestStepSummary:
    def test_writes_to_github_step_summary(self, tmp_path):
        summary_file = tmp_path / "summary.md"
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
            write_step_summary("## Results\n\nAll good.")
        assert "## Results" in summary_file.read_text()

    def test_noop_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            write_step_summary("content")

    def test_appends_to_existing(self, tmp_path):
        summary_file = tmp_path / "summary.md"
        summary_file.write_text("# Existing\n")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
            write_step_summary("## New section")
        content = summary_file.read_text()
        assert "# Existing" in content
        assert "## New section" in content


class TestProgressReporter:
    def test_init_with_all_params(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="ruinosus",
            repo_name="aap-open-swe",
            issue_number=15,
            comment_id=123,
        )
        assert pr.repo_owner == "ruinosus"
        assert pr.comment_id == 123

    def test_init_disabled_without_token(self):
        pr = ProgressReporter(
            github_token="",
            repo_owner="ruinosus",
            repo_name="aap-open-swe",
            issue_number=15,
        )
        assert pr.enabled is False

    def test_format_progress_bar(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._phases = [
            {"name": "Setup", "status": "done"},
            {"name": "Layer 1", "status": "running"},
            {"name": "Layer 2", "status": "pending"},
        ]
        bar = pr._format_progress()
        assert "Setup" in bar
        assert "Layer 1" in bar
        assert "Layer 2" in bar

    def test_start_phase_updates_state(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._post = MagicMock()
        pr.start_phase("Layer 1 — Core")
        assert any(p["name"] == "Layer 1 — Core" for p in pr._phases)

    def test_complete_phase_updates_state(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._post = MagicMock()
        pr.start_phase("Layer 1")
        pr.complete_phase("Layer 1")
        phase = next(p for p in pr._phases if p["name"] == "Layer 1")
        assert phase["status"] == "done"

    def test_tool_call_logged(self):
        pr = ProgressReporter(
            github_token="tok",
            repo_owner="o",
            repo_name="r",
            issue_number=1,
        )
        pr._post = MagicMock()
        pr.log_tool_call("execute", "git commit -m 'test'")
        assert pr._tool_calls == 1


class TestAgentStreamingCallback:
    def test_on_tool_start_logs_group(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_tool_start(
            serialized={"name": "execute"},
            input_str="git status",
            run_id=uuid4(),
        )
        out = capsys.readouterr().out
        assert "::group::" in out
        assert "execute" in out

    def test_on_tool_end_closes_group(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_tool_end(output="done", run_id=uuid4())
        out = capsys.readouterr().out
        assert "::endgroup::" in out

    def test_on_tool_start_calls_progress_reporter(self):
        reporter = MagicMock()
        cb = AgentStreamingCallback(progress_reporter=reporter)
        cb.on_tool_start(
            serialized={"name": "execute"},
            input_str="git commit",
            run_id=uuid4(),
        )
        reporter.log_tool_call.assert_called_once()

    def test_on_tool_error_emits_gh_error(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_tool_error(error=Exception("fail"), run_id=uuid4())
        out = capsys.readouterr().out
        assert "::error::" in out

    def test_on_chat_model_start_logs(self, capsys):
        cb = AgentStreamingCallback()
        cb.on_chat_model_start(
            serialized={"id": ["langchain", "chat_models", "ChatOpenAI"]},
            messages=[[]],
            run_id=uuid4(),
        )
        out = capsys.readouterr().out
        assert "::group::" in out
        assert "LLM" in out

    def test_tool_call_counter(self):
        cb = AgentStreamingCallback()
        cb.on_tool_start(serialized={"name": "a"}, input_str="", run_id=uuid4())
        cb.on_tool_end(output="", run_id=uuid4())
        cb.on_tool_start(serialized={"name": "b"}, input_str="", run_id=uuid4())
        cb.on_tool_end(output="", run_id=uuid4())
        assert cb.tool_call_count == 2
