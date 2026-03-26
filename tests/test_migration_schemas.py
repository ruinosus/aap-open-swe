"""Tests for migration skill schemas."""

from agent.skills.schemas import MigrationOutput, SizingFinding, SizingLayerSummary, SizingOutput


def test_sizing_finding_valid():
    f = SizingFinding(
        layer=1,
        category="prompt",
        file="apps/agent/src/agent.py",
        line=15,
        description="SYSTEM_PROMPT (2.3K chars)",
        impact="high",
        code_snippet='SYSTEM_PROMPT = """You are...',
        language="python",
    )
    assert f.layer == 1
    assert f.impact == "high"


def test_sizing_layer_summary():
    s = SizingLayerSummary(
        layer=1,
        name="core",
        findings_count=15,
        estimated_effort="2-3h",
        is_breaking=False,
        applicable=True,
    )
    assert s.name == "core"
    assert not s.is_breaking


def test_sizing_output_valid():
    o = SizingOutput(
        repo_url="https://github.com/CopilotKit/OpenGenerativeUI",
        repo_type="external",
        languages=["python", "typescript"],
        total_findings=47,
        findings=[],
        layers=[],
        proposed_structure=[".aap/open-generative-ui/manifest.yaml"],
    )
    assert o.skill_output_type == "sizing"
    assert o.repo_type == "external"


def test_migration_output_valid():
    o = MigrationOutput(
        layer=1,
        layer_name="core",
        summary="Created .aap/ structure with 12 prompts extracted",
        files_created=[".aap/open-generative-ui/manifest.yaml"],
        files_modified=["pyproject.toml"],
        branch="aap-migration/layer-1-core",
        is_breaking=False,
    )
    assert o.skill_output_type == "migration"
    assert not o.is_breaking


def test_sizing_output_schema_has_additional_properties_false():
    schema = SizingOutput.model_json_schema()
    assert schema.get("additionalProperties") is False


def test_migration_output_schema_has_additional_properties_false():
    schema = MigrationOutput.model_json_schema()
    assert schema.get("additionalProperties") is False
