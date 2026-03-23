"""Tests for skill guardrail middleware."""

from agent.middleware.output_validator import validate_pr_output, validate_review_output
from agent.middleware.secret_filter import redact_secrets
from agent.middleware.skill_file_scope import SKILL_SCOPE, _is_path_allowed

# ─── File Scope Tests ──────────────────────────────────────────


class TestFileScope:
    def test_review_skills_block_all_writes(self):
        scope = SKILL_SCOPE["code-review"]
        assert not scope["allow_writes"]
        assert not _is_path_allowed("anything.py", scope)

    def test_security_scan_blocks_all_writes(self):
        scope = SKILL_SCOPE["security-scan"]
        assert not _is_path_allowed("src/main.py", scope)

    def test_project_docs_allows_readme(self):
        scope = SKILL_SCOPE["project-docs"]
        assert _is_path_allowed("README.md", scope)

    def test_project_docs_allows_docs_dir(self):
        scope = SKILL_SCOPE["project-docs"]
        assert _is_path_allowed("docs/ARCHITECTURE.md", scope)

    def test_project_docs_allows_root_md(self):
        scope = SKILL_SCOPE["project-docs"]
        assert _is_path_allowed("CUSTOMIZATION.md", scope)

    def test_project_docs_blocks_github(self):
        scope = SKILL_SCOPE["project-docs"]
        assert not _is_path_allowed(".github/workflows/agent.yml", scope)

    def test_project_docs_blocks_aap(self):
        scope = SKILL_SCOPE["project-docs"]
        assert not _is_path_allowed(".aap/open-swe/manifest.yaml", scope)

    def test_project_docs_blocks_python(self):
        scope = SKILL_SCOPE["project-docs"]
        assert not _is_path_allowed("agent/server.py", scope)

    def test_project_docs_blocks_yaml(self):
        scope = SKILL_SCOPE["project-docs"]
        assert not _is_path_allowed("config.yaml", scope)

    def test_test_generator_allows_tests(self):
        scope = SKILL_SCOPE["test-generator"]
        assert _is_path_allowed("tests/test_new.py", scope)

    def test_test_generator_blocks_agent_code(self):
        scope = SKILL_SCOPE["test-generator"]
        assert not _is_path_allowed("agent/server.py", scope)

    def test_doc_generator_allows_python(self):
        scope = SKILL_SCOPE["doc-generator"]
        assert _is_path_allowed("agent/utils/model.py", scope)

    def test_doc_generator_blocks_tests(self):
        scope = SKILL_SCOPE["doc-generator"]
        assert not _is_path_allowed("tests/test_skills.py", scope)

    def test_normalizes_leading_dot_slash(self):
        scope = SKILL_SCOPE["project-docs"]
        assert _is_path_allowed("./README.md", scope)

    def test_normalizes_leading_slash(self):
        scope = SKILL_SCOPE["project-docs"]
        assert _is_path_allowed("/README.md", scope)


# ─── Secret Filter Tests ──────────────────────────────────────


class TestSecretFilter:
    def test_redacts_openai_key(self):
        text = "My key is sk-abc123def456ghi789jkl012mno345pq"
        result, count = redact_secrets(text)
        assert "sk-abc" not in result
        assert "[REDACTED_" in result
        assert count >= 1

    def test_redacts_github_token(self):
        text = "Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result, count = redact_secrets(text)
        assert "ghp_" not in result
        assert count >= 1

    def test_redacts_aws_key(self):
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result, count = redact_secrets(text)
        assert "AKIA" not in result
        assert count >= 1

    def test_redacts_generic_api_key(self):
        text = "api_key = 'super_secret_value_here_long'"
        result, count = redact_secrets(text)
        assert "super_secret" not in result
        assert count >= 1

    def test_no_redaction_on_clean_text(self):
        text = "This is a clean review with no secrets."
        result, count = redact_secrets(text)
        assert result == text
        assert count == 0

    def test_redacts_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
        result, count = redact_secrets(text)
        assert "eyJhbG" not in result
        assert count >= 1

    def test_redacts_connection_string(self):
        text = "DB: postgres://user:pass@host:5432/db"
        result, count = redact_secrets(text)
        assert "postgres://" not in result
        assert count >= 1


# ─── Output Validator Tests ──────────────────────────────────


class TestOutputValidator:
    def test_valid_review_output(self):
        data = {
            "skill_output_type": "review",
            "summary": "Found 2 issues",
            "score": "7/10",
            "comments": [
                {"file": "a.py", "line": 1, "message": "Bug", "severity": "high"},
            ],
        }
        errors = validate_review_output(data)
        assert errors == []

    def test_review_missing_summary(self):
        data = {"score": "7/10", "comments": []}
        errors = validate_review_output(data)
        assert any("summary" in e for e in errors)

    def test_review_missing_score(self):
        data = {"summary": "ok", "comments": []}
        errors = validate_review_output(data)
        assert any("score" in e for e in errors)

    def test_review_invalid_score_range(self):
        data = {"summary": "ok", "score": "15/10", "comments": []}
        errors = validate_review_output(data)
        assert any("out of range" in e for e in errors)

    def test_review_comment_missing_fields(self):
        data = {
            "summary": "ok",
            "score": "5/10",
            "comments": [{"file": "a.py"}],  # missing line, message, severity
        }
        errors = validate_review_output(data)
        assert len(errors) == 3  # line, message, severity

    def test_valid_pr_output(self):
        data = {"skill_output_type": "pr", "summary": "Updated docs"}
        errors = validate_pr_output(data)
        assert errors == []

    def test_pr_missing_summary(self):
        data = {"skill_output_type": "pr"}
        errors = validate_pr_output(data)
        assert any("summary" in e for e in errors)
