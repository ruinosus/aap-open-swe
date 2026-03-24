"""Tests for repository protection middleware.

Verifies that pushes to repos outside ALLOWED_GITHUB_ORGS are blocked,
and that external repos require fork-first workflow.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.middleware.repo_protection import (
    _extract_push_target,
    create_repo_protection_middleware,
)


class FakeRuntime:
    pass


RUNTIME = FakeRuntime()


# ─── Push Target Extraction ──────────────────────────────────


class TestExtractPushTarget:
    def test_extracts_from_https_url(self):
        cmd = "git push https://github.com/CopilotKit/OpenGenerativeUI.git main"
        result = _extract_push_target(cmd)
        assert result == ("copilotkit", "opengenerativeui")

    def test_extracts_from_token_url(self):
        cmd = "git push https://x-access-token:TOKEN@github.com/ruinosus/aap-open-swe.git HEAD:refs/heads/branch"
        result = _extract_push_target(cmd)
        assert result == ("ruinosus", "aap-open-swe")

    def test_returns_none_for_origin(self):
        cmd = "git push origin main"
        result = _extract_push_target(cmd)
        assert result is None

    def test_returns_none_for_non_push(self):
        cmd = "git status"
        result = _extract_push_target(cmd)
        assert result is None

    def test_extracts_without_git_suffix(self):
        cmd = "git push https://github.com/myorg/myrepo main"
        result = _extract_push_target(cmd)
        assert result == ("myorg", "myrepo")


# ─── Middleware Creation ──────────────────────────────────────


class TestMiddlewareCreation:
    def test_returns_none_when_no_allowed_orgs(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset(),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        assert mw is None

    def test_returns_middleware_when_orgs_configured(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        assert mw is not None


# ─── Middleware Interception ──────────────────────────────────


class TestMiddlewareInterception:
    def _make_state(self, command: str):
        return {
            "messages": [
                HumanMessage(content="do something"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "execute", "args": {"command": command}, "id": "tc_1"}],
                ),
            ]
        }

    def test_blocks_push_to_unauthorized_org(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        state = self._make_state("git push https://github.com/CopilotKit/OpenGenerativeUI.git main")
        result = mw.before_model(state, RUNTIME)

        assert result is not None
        last_msg = result["messages"][-1]
        assert isinstance(last_msg, ToolMessage)
        assert "BLOCKED" in last_msg.content
        assert "CopilotKit" in last_msg.content.lower() or "copilotkit" in last_msg.content

    def test_allows_push_to_authorized_org(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        state = self._make_state(
            "git push https://github.com/ruinosus/aap-open-swe.git HEAD:refs/heads/feature"
        )
        result = mw.before_model(state, RUNTIME)
        assert result is None

    def test_blocks_push_with_token_url(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        state = self._make_state(
            "git push https://x-access-token:ghp_abc@github.com/external-org/their-repo.git main"
        )
        result = mw.before_model(state, RUNTIME)

        assert result is not None
        assert "BLOCKED" in result["messages"][-1].content

    def test_allows_non_push_commands(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        state = self._make_state("git clone https://github.com/CopilotKit/OpenGenerativeUI.git")
        result = mw.before_model(state, RUNTIME)
        assert result is None

    def test_allows_non_execute_tools(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "read_file", "args": {"file_path": "README.md"}, "id": "tc_1"}
                    ],
                ),
            ]
        }
        result = mw.before_model(state, RUNTIME)
        assert result is None

    def test_multiple_allowed_orgs(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus", "avanade", "myorg"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        # Allowed
        state1 = self._make_state("git push https://github.com/avanade/some-repo.git main")
        assert mw.before_model(state1, RUNTIME) is None

        # Blocked
        state2 = self._make_state("git push https://github.com/facebook/react.git main")
        result = mw.before_model(state2, RUNTIME)
        assert result is not None
        assert "BLOCKED" in result["messages"][-1].content

    def test_block_message_includes_allowed_orgs(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus", "avanade"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        state = self._make_state("git push https://github.com/evil-org/repo.git main")
        result = mw.before_model(state, RUNTIME)

        content = result["messages"][-1].content
        assert "ruinosus" in content
        assert "avanade" in content
        assert "fork" in content.lower()

    def test_ignores_messages_without_tool_calls(self):
        mw = create_repo_protection_middleware(
            allowed_orgs=frozenset({"ruinosus"}),
            current_repo_owner="ruinosus",
            current_repo_name="aap-open-swe",
        )
        state = {"messages": [AIMessage(content="I'll analyze the code")]}
        result = mw.before_model(state, RUNTIME)
        assert result is None
