"""End-to-end tests for guardrail middleware with REAL LLM calls.

These tests create actual Deep Agents, send real prompts to an LLM,
and verify that the SDK GuardrailMiddleware works in production conditions.

Run with:
    source .env && pytest tests/test_guardrails_e2e.py -m e2e -v

Requires:
    OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable set.

WARNING: These tests cost money (API calls). They are excluded from
normal test runs and must be invoked explicitly with -m e2e.
"""

import json
import os

import pytest

_has_openai = bool(os.environ.get("OPENAI_API_KEY"))
_has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _has_openai and not _has_anthropic,
        reason="No LLM API key available (set OPENAI_API_KEY or ANTHROPIC_API_KEY)",
    ),
]


def _get_model_id() -> str:
    if _has_anthropic:
        return "anthropic:claude-sonnet-4-6"
    return "openai:gpt-4o"


@pytest.mark.e2e
async def test_review_skill_with_sdk_guardrails():
    """Full pipeline: agent + SDK GuardrailMiddleware → valid review JSON.

    Creates a real agent with SDK guardrail middleware (auto-resolved from
    .aap/ manifests), sends code with SQL injection, verifies valid JSON output.
    """
    from cockpit_aap import create_guardrail_middleware
    from deepagents import create_deep_agent
    from deepagents.backends import LocalShellBackend
    from langchain.agents.structured_output import ProviderStrategy

    from agent.config import get_manifest, make_model
    from agent.middleware.output_validator import create_output_validator
    from agent.skills.review.poster import parse_review_output
    from agent.skills.schemas import ReviewOutput

    model_id = _get_model_id()
    model = make_model(model_id, temperature=0, max_tokens=4000)

    # SDK guardrail middleware (replaces 3 custom middleware)
    mi = get_manifest()
    guardrail_mw = create_guardrail_middleware(mi, include_builtin_pii=True)

    middleware = [guardrail_mw]
    output_mw = create_output_validator("code-review")
    if output_mw:
        middleware.append(output_mw)

    # Structured output for review
    response_format = None
    if _has_openai:
        response_format = ProviderStrategy(schema=ReviewOutput, strict=True)

    sandbox = LocalShellBackend(root_dir=".", virtual_mode=True)

    agent = create_deep_agent(
        model=model,
        system_prompt=(
            "You are a code review agent. Return ONLY a JSON object with: "
            "skill_output_type, summary, score (N/10), comments [{file, line, message, severity}]"
        ),
        tools=[],
        backend=sandbox,
        response_format=response_format,
        middleware=middleware,
    )

    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": """Review this code:
```python
# file: example.py
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id  # line 3
    return query
```""",
                }
            ]
        },
    )

    # Extract response
    structured = result.get("structured_response")
    if structured and hasattr(structured, "model_dump"):
        data = structured.model_dump()
    else:
        messages = result.get("messages", [])
        data = None
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content.strip():
                try:
                    data = json.loads(msg.content)
                    break
                except (json.JSONDecodeError, TypeError):
                    pass
                data = parse_review_output(msg.content)
                if data:
                    break

    assert data is not None, "Agent should have returned structured output"
    assert "summary" in data
    assert "score" in data
    assert "comments" in data
    assert len(data["comments"]) >= 1, "Should find SQL injection"


@pytest.mark.e2e
async def test_secret_filter_with_sdk_guardrails():
    """Agent output with secrets → SDK guardrail should redact them."""
    from cockpit_aap import ManifestInstance, create_guardrail_middleware

    mi = ManifestInstance("open-swe")
    mw = create_guardrail_middleware(mi)

    # Simulate what would happen if the agent output a secret
    result = await mw.check_output(
        "The config uses api_key = 'sk-proj-abc123def456ghi789jkl012mno345pq' for auth"
    )

    # SDK should redact
    assert result.rewritten is not None
    assert "sk-proj" not in result.rewritten


@pytest.mark.e2e
async def test_input_guardrail_blocks_destructive_command():
    """SDK guardrail blocks destructive commands before they reach the LLM."""
    from cockpit_aap import ManifestInstance, create_guardrail_middleware

    mi = ManifestInstance("open-swe")
    mw = create_guardrail_middleware(mi)

    result = await mw.check_input("Please execute: rm -rf / --no-preserve-root")
    assert not result.allowed
    assert result.action == "block"
    assert any(v.category == "safety" for v in result.violations)
