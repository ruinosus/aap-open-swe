"""Integration tests for guardrail middleware in the agent pipeline.

Tests verify that the SDK GuardrailMiddleware intercepts agent behavior
correctly when plugged into the pipeline with realistic LangChain state.
"""

import asyncio
import json

from langchain_core.messages import AIMessage

from agent.middleware.output_validator import create_output_validator


def _run(coro):
    return asyncio.run(coro)


class FakeRuntime:
    pass


RUNTIME = FakeRuntime()


# ─── SDK Middleware in Pipeline Tests ─────────────────────────


class TestSDKMiddlewareInPipeline:
    """Verify GuardrailMiddleware works with LangChain agent state."""

    def test_middleware_blocks_destructive_input(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi)

        result = _run(mw.check_input("Please run: rm -rf / --force"))
        assert not result.allowed
        assert result.action == "block"
        assert len(result.violations) >= 1

    def test_middleware_redacts_secret_in_output(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi)

        result = _run(mw.check_output("Config: AKIAIOSFODNN7EXAMPLE"))
        assert result.rewritten is not None
        assert "AKIA" not in result.rewritten
        assert "REDACTED" in result.rewritten

    def test_middleware_passes_clean_content(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi)

        result_in = _run(mw.check_input("Review this PR please"))
        assert result_in.allowed

        result_out = _run(mw.check_output("Found 2 issues. Score: 7/10."))
        assert result_out.allowed
        assert result_out.rewritten is None

    def test_middleware_detects_multiple_secrets(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi)

        text = "Keys: AKIAIOSFODNN7EXAMPLE and ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = _run(mw.check_output(text))
        assert result.rewritten is not None
        assert "AKIA" not in result.rewritten
        assert "ghp_" not in result.rewritten

    def test_pii_detection_blocks_email(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi, include_builtin_pii=True)

        result = _run(mw.check_input("Contact john.doe@example.com for details"))
        assert not result.allowed

    def test_violations_have_rule_id(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi)

        result = _run(mw.check_input("DROP TABLE users;"))
        assert not result.allowed
        assert len(result.violations) >= 1
        assert result.violations[0].rule_id == "destructive-commands"


# ─── Output Validator Integration Tests ───────────────────────


class TestOutputValidatorIntegration:
    """Verify output_validator middleware with realistic state."""

    def test_valid_review_passes(self):
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
        state = {"messages": [AIMessage(content=valid_json)]}
        result = mw.after_agent(state, RUNTIME)
        assert result is None

    def test_invalid_review_logs_warning(self, caplog):
        import logging

        mw = create_output_validator("code-review")

        invalid_json = json.dumps({"skill_output_type": "review"})
        state = {"messages": [AIMessage(content=invalid_json)]}

        with caplog.at_level(logging.WARNING, logger="agent.middleware.output_validator"):
            result = mw.after_agent(state, RUNTIME)

        assert result is None
        assert "validation failed" in caplog.text

    def test_no_validator_for_swe_coder(self):
        mw = create_output_validator("swe-coder")
        assert mw is None


# ─── Middleware Wiring Tests ──────────────────────────────────


class TestMiddlewareWiring:
    """Verify that run_standalone.py correctly wires middleware."""

    def test_sdk_middleware_creates_for_module(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi)
        assert mw is not None

    def test_sdk_middleware_with_builtin_pii(self):
        from cockpit_aap import ManifestInstance, create_guardrail_middleware

        mi = ManifestInstance("open-swe")
        mw = create_guardrail_middleware(mi, include_builtin_pii=True)
        assert mw is not None

    def test_output_validator_created_for_review_skill(self):
        mw = create_output_validator("code-review")
        assert mw is not None

    def test_output_validator_created_for_pr_skill(self):
        mw = create_output_validator("project-docs")
        assert mw is not None

    def test_no_output_validator_for_swe_coder(self):
        assert create_output_validator("swe-coder") is None
