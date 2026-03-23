"""Tests for skill adapter integration."""


def test_get_skills_returns_list():
    from agent.aap_config import get_skills

    skills = get_skills()
    assert isinstance(skills, list)


def test_get_skills_loads_4_skills():
    from agent.aap_config import _load_manifest, get_skills

    _load_manifest.cache_clear()
    skills = get_skills()
    assert len(skills) == 5
    ids = [s.id for s in skills]
    assert "code-review" in ids
    assert "security-scan" in ids
    assert "doc-generator" in ids
    assert "test-generator" in ids
    assert "project-docs" in ids


def test_get_skill_by_id():
    from agent.aap_config import _load_manifest, get_skill

    _load_manifest.cache_clear()
    skill = get_skill("code-review")
    assert skill is not None
    assert skill.id == "code-review"
    assert skill.name == "Code Review"


def test_get_skill_unknown_returns_none():
    from agent.aap_config import get_skill

    assert get_skill("nonexistent-skill") is None


def test_get_skill_adapter_builds():
    from agent.aap_config import _load_manifest, get_skill_adapter

    _load_manifest.cache_clear()
    adapter = get_skill_adapter()
    assert adapter is not None
    assert hasattr(adapter, "detect_triggers")
    assert hasattr(adapter, "build_skill_system_prompt")


def test_skill_adapter_detects_review_trigger():
    from agent.aap_config import _load_manifest, get_skill_adapter

    _load_manifest.cache_clear()
    adapter = get_skill_adapter()
    activated = adapter.detect_triggers("please review this PR")
    ids = [s.id for s in activated]
    assert "code-review" in ids


def test_skill_adapter_detects_security_trigger():
    from agent.aap_config import _load_manifest, get_skill_adapter

    _load_manifest.cache_clear()
    adapter = get_skill_adapter()
    activated = adapter.detect_triggers("check for security vulnerabilities")
    ids = [s.id for s in activated]
    assert "security-scan" in ids


def test_get_skill_instruction_returns_content():
    from agent.aap_config import _load_manifest, get_skill_instruction

    _load_manifest.cache_clear()
    instruction = get_skill_instruction("code-review")
    assert instruction
    assert len(instruction) > 100  # non-trivial content
    assert "review" in instruction.lower()
