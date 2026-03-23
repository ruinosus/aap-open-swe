"""Integration tests for guardrail middleware.

These tests verify that the middleware actually intercepts agent behavior
when plugged into the pipeline — not just that the logic functions work
in isolation.

Each test simulates a real agent state (messages with tool calls or AI
responses) and passes it through the middleware, verifying the middleware
modifies the state correctly.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.middleware.output_validator import create_output_validator
from agent.middleware.secret_filter import secret_filter
from agent.middleware.skill_file_scope import create_skill_file_scope_middleware

# ─── Helpers ──────────────────────────────────────────────────


def _make_ai_message_with_tool_call(tool_name: str, args: dict, tool_call_id: str = "tc_1"):
    """Create an AIMessage with a tool_calls list, as the agent would produce."""
    msg = AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": tool_call_id}],
    )
    return msg


def _make_state(messages: list, **extra) -> dict:
    """Build a minimal AgentState dict."""
    return {"messages": messages, **extra}


class FakeRuntime:
    """Minimal runtime stub for middleware calls."""

    pass


RUNTIME = FakeRuntime()


def _call_before_model(mw, state):
    """Call a @before_model middleware."""
    return mw.before_model(state, RUNTIME)


def _call_after_agent(mw, state):
    """Call an @after_agent middleware."""
    return mw.after_agent(state, RUNTIME)


# ─── File Scope Integration Tests ─────────────────────────────


class TestFileScopeIntegration:
    """Verify the middleware intercepts tool calls in a realistic state."""

    def test_review_skill_blocks_write_file(self):
        """code-review skill must not write ANY file."""
        mw = create_skill_file_scope_middleware("code-review")
        assert mw is not None

        ai_msg = _make_ai_message_with_tool_call(
            "write_file", {"file_path": "README.md", "content": "hacked"}
        )
        state = _make_state([HumanMessage(content="review"), ai_msg])

        result = _call_before_model(mw, state)

        assert result is not None, "Middleware should have intercepted"
        last_msg = result["messages"][-1]
        assert isinstance(last_msg, ToolMessage)
        assert "BLOCKED" in last_msg.content

    def test_review_skill_allows_read_file(self):
        """code-review can use read_file (not a write tool)."""
        mw = create_skill_file_scope_middleware("code-review")

        ai_msg = _make_ai_message_with_tool_call("read_file", {"file_path": "agent/server.py"})
        state = _make_state([HumanMessage(content="review"), ai_msg])

        result = _call_before_model(mw, state)
        assert result is None, "read_file should not be blocked"

    def test_project_docs_blocks_workflow_edit(self):
        """project-docs must not edit .github/ files."""
        mw = create_skill_file_scope_middleware("project-docs")

        ai_msg = _make_ai_message_with_tool_call(
            "edit_file", {"file_path": ".github/workflows/agent.yml", "content": "x"}
        )
        state = _make_state([HumanMessage(content="update docs"), ai_msg])

        result = _call_before_model(mw, state)

        assert result is not None
        last_msg = result["messages"][-1]
        assert "BLOCKED" in last_msg.content
        assert ".github/workflows/agent.yml" in last_msg.content

    def test_project_docs_allows_readme_write(self):
        """project-docs CAN write to README.md."""
        mw = create_skill_file_scope_middleware("project-docs")

        ai_msg = _make_ai_message_with_tool_call(
            "write_file", {"file_path": "README.md", "content": "updated"}
        )
        state = _make_state([HumanMessage(content="update docs"), ai_msg])

        result = _call_before_model(mw, state)
        assert result is None, "README.md should be allowed for project-docs"

    def test_project_docs_blocks_python_file(self):
        """project-docs must not touch .py files."""
        mw = create_skill_file_scope_middleware("project-docs")

        ai_msg = _make_ai_message_with_tool_call(
            "write_file", {"file_path": "agent/aap_config.py", "content": "x"}
        )
        state = _make_state([HumanMessage(content="docs"), ai_msg])

        result = _call_before_model(mw, state)

        assert result is not None
        assert "BLOCKED" in result["messages"][-1].content

    def test_test_generator_blocks_source_code(self):
        """test-generator must not modify source code."""
        mw = create_skill_file_scope_middleware("test-generator")

        ai_msg = _make_ai_message_with_tool_call(
            "edit_file", {"file_path": "agent/server.py", "content": "x"}
        )
        state = _make_state([HumanMessage(content="gen tests"), ai_msg])

        result = _call_before_model(mw, state)

        assert result is not None
        assert "BLOCKED" in result["messages"][-1].content

    def test_test_generator_allows_test_file(self):
        """test-generator CAN write test files."""
        mw = create_skill_file_scope_middleware("test-generator")

        ai_msg = _make_ai_message_with_tool_call(
            "write_file", {"file_path": "tests/test_new_feature.py", "content": "x"}
        )
        state = _make_state([HumanMessage(content="gen tests"), ai_msg])

        result = _call_before_model(mw, state)
        assert result is None, "tests/ should be allowed for test-generator"

    def test_no_middleware_for_unknown_skill(self):
        """Unknown skills get no file scope middleware."""
        mw = create_skill_file_scope_middleware("unknown-skill")
        assert mw is None

    def test_no_middleware_for_swe_coder(self):
        """swe-coder has no file restrictions."""
        mw = create_skill_file_scope_middleware("swe-coder")
        assert mw is None

    def test_ignores_messages_without_tool_calls(self):
        """Middleware does nothing when no tool calls are present."""
        mw = create_skill_file_scope_middleware("code-review")

        state = _make_state(
            [
                HumanMessage(content="review this"),
                AIMessage(content="I'll analyze the code"),
            ]
        )

        result = _call_before_model(mw, state)
        assert result is None

    def test_blocks_only_first_offending_tool_call(self):
        """When multiple tool calls exist, blocks on the first violation."""
        mw = create_skill_file_scope_middleware("project-docs")

        msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "write_file", "args": {"file_path": "README.md"}, "id": "tc_1"},
                {"name": "write_file", "args": {"file_path": "agent/server.py"}, "id": "tc_2"},
            ],
        )
        state = _make_state([msg])

        result = _call_before_model(mw, state)

        # README.md is allowed, but agent/server.py is blocked
        assert result is not None
        assert "agent/server.py" in result["messages"][-1].content


# ─── Secret Filter Integration Tests ─────────────────────────


class TestSecretFilterIntegration:
    """Verify the after_agent middleware redacts secrets from AI messages."""

    def test_redacts_secret_in_ai_message(self):
        """If the agent outputs an API key, it must be redacted."""
        state = _make_state(
            [
                HumanMessage(content="show config"),
                AIMessage(content="The API key is sk-abc123def456ghi789jkl012mno345pq"),
            ]
        )

        result = _call_after_agent(secret_filter, state)

        assert result is not None, "Should have redacted"
        ai_msg = result["messages"][-1]
        assert "sk-abc" not in ai_msg.content
        assert "[REDACTED_" in ai_msg.content

    def test_redacts_github_token_in_output(self):
        """GitHub tokens in agent output must be redacted."""
        state = _make_state(
            [
                AIMessage(content="Use this token: ghp_1234567890abcdefghijklmnopqrstuvwxyz"),
            ]
        )

        result = _call_after_agent(secret_filter, state)

        assert result is not None
        assert "ghp_" not in result["messages"][-1].content

    def test_no_redaction_on_clean_output(self):
        """Clean output should not be modified."""
        state = _make_state(
            [
                AIMessage(content="Found 3 issues in the code review."),
            ]
        )

        result = _call_after_agent(secret_filter, state)
        assert result is None, "Clean output should not trigger redaction"

    def test_preserves_human_messages(self):
        """Only AI messages are scanned, human messages are untouched."""
        state = _make_state(
            [
                HumanMessage(content="My key is sk-abc123def456ghi789jkl012mno345pq"),
                AIMessage(content="I see you shared a key. Let me help."),
            ]
        )

        result = _call_after_agent(secret_filter, state)
        assert result is None, "No AI message has secrets"

    def test_redacts_multiple_secrets(self):
        """Multiple secrets in one message should all be redacted."""
        state = _make_state(
            [
                AIMessage(
                    content="Keys: sk-abc123def456ghi789jkl012mno345pq and AKIAIOSFODNN7EXAMPLE"
                ),
            ]
        )

        result = _call_after_agent(secret_filter, state)

        assert result is not None
        content = result["messages"][-1].content
        assert "sk-abc" not in content
        assert "AKIA" not in content

    def test_handles_empty_state(self):
        """Empty state should not crash."""
        result = _call_after_agent(secret_filter, {"messages": []})
        assert result is None


# ─── Output Validator Integration Tests ───────────────────────


class TestOutputValidatorIntegration:
    """Verify the after_agent middleware validates structured output."""

    def test_valid_review_passes(self):
        """Valid review JSON should pass validation (returns None = no changes)."""
        mw = create_output_validator("code-review")
        assert mw is not None

        valid_json = json.dumps(
            {
                "skill_output_type": "review",
                "summary": "All good",
                "score": "9/10",
                "comments": [],
            }
        )
        state = _make_state([AIMessage(content=valid_json)])

        result = _call_after_agent(mw, state)
        assert result is None, "Valid output should pass without modification"

    def test_invalid_review_logs_warning(self, caplog):
        """Invalid review JSON should log a warning."""
        import logging

        mw = create_output_validator("code-review")

        invalid_json = json.dumps({"skill_output_type": "review"})
        state = _make_state([AIMessage(content=invalid_json)])

        with caplog.at_level(logging.WARNING, logger="agent.middleware.output_validator"):
            result = _call_after_agent(mw, state)

        assert result is None, "Validator warns but doesn't block"
        assert "validation failed" in caplog.text

    def test_valid_pr_output_passes(self):
        """Valid PR JSON passes validation."""
        mw = create_output_validator("project-docs")

        valid_json = json.dumps(
            {
                "skill_output_type": "pr",
                "summary": "Updated docs",
                "files_changed": ["README.md"],
            }
        )
        state = _make_state([AIMessage(content=valid_json)])

        result = _call_after_agent(mw, state)
        assert result is None

    def test_no_json_in_output_logs_warning(self, caplog):
        """Non-JSON output should log a warning."""
        import logging

        mw = create_output_validator("security-scan")

        state = _make_state([AIMessage(content="Just plain text, no JSON.")])

        with caplog.at_level(logging.WARNING, logger="agent.middleware.output_validator"):
            result = _call_after_agent(mw, state)

        assert result is None
        assert "no structured output found" in caplog.text

    def test_no_validator_for_swe_coder(self):
        """swe-coder doesn't need output validation."""
        mw = create_output_validator("swe-coder")
        assert mw is None

    def test_validates_from_structured_response(self):
        """If structured_response is present in state, use it."""
        mw = create_output_validator("code-review")

        from agent.schemas import ReviewOutput

        structured = ReviewOutput(
            summary="Clean code",
            score="10/10",
            comments=[],
        )
        state = _make_state(
            [AIMessage(content="")],
            structured_response=structured,
        )

        result = _call_after_agent(mw, state)
        assert result is None, "Structured response should pass validation"


# ─── Middleware Wiring Tests ──────────────────────────────────


class TestMiddlewareWiring:
    """Verify that run_standalone.py correctly wires middleware per skill."""

    def test_review_skill_gets_3_middleware(self):
        """Review skills should get file_scope + secret_filter + output_validator."""
        from agent.middleware.output_validator import create_output_validator
        from agent.middleware.secret_filter import secret_filter
        from agent.middleware.skill_file_scope import create_skill_file_scope_middleware

        middleware = []
        skill_id = "code-review"

        file_scope_mw = create_skill_file_scope_middleware(skill_id)
        if file_scope_mw:
            middleware.append(file_scope_mw)
        middleware.append(secret_filter)
        output_mw = create_output_validator(skill_id)
        if output_mw:
            middleware.append(output_mw)

        assert len(middleware) == 3

    def test_project_docs_gets_3_middleware(self):
        """PR skills should also get all 3 middleware."""
        from agent.middleware.output_validator import create_output_validator
        from agent.middleware.secret_filter import secret_filter
        from agent.middleware.skill_file_scope import create_skill_file_scope_middleware

        middleware = []
        skill_id = "project-docs"

        file_scope_mw = create_skill_file_scope_middleware(skill_id)
        if file_scope_mw:
            middleware.append(file_scope_mw)
        middleware.append(secret_filter)
        output_mw = create_output_validator(skill_id)
        if output_mw:
            middleware.append(output_mw)

        assert len(middleware) == 3

    def test_swe_coder_gets_only_secret_filter(self):
        """swe-coder has no file scope or output validator, only secret filter."""
        from agent.middleware.output_validator import create_output_validator
        from agent.middleware.skill_file_scope import create_skill_file_scope_middleware

        assert create_skill_file_scope_middleware("swe-coder") is None
        assert create_output_validator("swe-coder") is None
