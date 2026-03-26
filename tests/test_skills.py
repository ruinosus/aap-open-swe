"""Tests for skill adapter integration."""


def _reset():
    """Reset the ManifestInstance singleton for clean tests."""
    global _instance
    import agent.config.manifest

    agent.config.manifest._instance = None


def test_get_skills_returns_list():
    from agent.config import get_skills

    skills = get_skills()
    assert isinstance(skills, list)


def test_get_skills_loads_7_skills():
    from agent.config import get_skills

    _reset()
    skills = get_skills()
    assert len(skills) == 8
    ids = [s.id for s in skills]
    assert "code-review" in ids
    assert "security-scan" in ids
    assert "doc-generator" in ids
    assert "test-generator" in ids
    assert "project-docs" in ids
    assert "aap-sizing" in ids
    assert "migrate-to-aap" in ids


def test_get_skill_by_id():
    from agent.config import get_skill

    _reset()
    skill = get_skill("code-review")
    assert skill is not None
    assert skill.id == "code-review"
    assert skill.name == "Code Review"


def test_get_skill_unknown_returns_none():
    from agent.config import get_skill

    assert get_skill("nonexistent-skill") is None


def test_get_skill_adapter_builds():
    from cockpit_aap import create_manifest_skill_adapter

    from agent.config import get_skills

    _reset()
    adapter = create_manifest_skill_adapter(get_skills())
    assert adapter is not None
    assert hasattr(adapter, "detect_triggers")
    assert hasattr(adapter, "build_skill_system_prompt")


def test_skill_adapter_detects_review_trigger():
    from cockpit_aap import create_manifest_skill_adapter

    from agent.config import get_skills

    _reset()
    adapter = create_manifest_skill_adapter(get_skills())
    activated = adapter.detect_triggers("please review this PR")
    ids = [s.id for s in activated]
    assert "code-review" in ids


def test_skill_adapter_detects_security_trigger():
    from cockpit_aap import create_manifest_skill_adapter

    from agent.config import get_skills

    _reset()
    adapter = create_manifest_skill_adapter(get_skills())
    activated = adapter.detect_triggers("check for security vulnerabilities")
    ids = [s.id for s in activated]
    assert "security-scan" in ids


def test_get_skill_instruction_returns_content():
    from agent.config import get_skill_instruction

    _reset()
    instruction = get_skill_instruction("code-review")
    assert instruction is not None
    assert "security" in instruction.lower() or "review" in instruction.lower()
