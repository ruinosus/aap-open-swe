"""Pydantic schemas for structured agent output.

Used with deepagents' response_format parameter to guarantee
valid JSON output from any LLM that supports structured outputs
(OpenAI GPT-4o, Claude, etc.).
"""

from pydantic import BaseModel, ConfigDict, Field


class _StrictSchema(BaseModel):
    """Base class that sets additionalProperties=false for OpenAI compatibility.

    OpenAI's structured outputs API requires all object schemas to have
    additionalProperties set to false. Pydantic v2 ConfigDict handles this.
    """

    model_config = ConfigDict(
        json_schema_extra={"additionalProperties": False},
    )


class ReviewComment(_StrictSchema):
    """A single review finding on a specific file and line."""

    file: str = Field(description="File path relative to repository root")
    line: int = Field(description="Line number in the new version of the file")
    message: str = Field(description="Clear description of the issue and why it matters")
    severity: str = Field(description="One of: critical, high, medium, low")


class GuardrailSuggestion(_StrictSchema):
    """A suggested AAP SDK guardrail manifest for a security finding."""

    name: str = Field(description="Guardrail name in kebab-case (e.g., 'sql-injection-block')")
    description: str = Field(description="What this guardrail prevents")
    phase: str = Field(description="'input' or 'output'")
    pattern: str = Field(description="Regex pattern to detect the vulnerability")
    action: str = Field(description="'block' or 'rewrite'")
    finding_ids: list[int] = Field(
        default_factory=list,
        description="Indices of comments[] this guardrail would prevent (0-based)",
    )


class ReviewOutput(_StrictSchema):
    """Structured output for code-review and security-scan skills."""

    skill_output_type: str = Field(
        default="review",
        description="Always 'review' for code-review and security-scan skills",
    )
    summary: str = Field(description="One or two sentence overview of the review findings")
    score: str = Field(description="Score from 1 to 10 as 'N/10'")
    comments: list[ReviewComment] = Field(
        default_factory=list,
        description="List of findings with file, line, message, and severity",
    )
    suggested_guardrails: list[GuardrailSuggestion] = Field(
        default_factory=list,
        description="Suggested AAP SDK guardrail manifests for critical/high findings (security-scan only)",
    )


class PROutput(_StrictSchema):
    """Structured output for doc-generator and test-generator skills."""

    skill_output_type: str = Field(
        default="pr",
        description="Always 'pr' for doc-generator and test-generator skills",
    )
    summary: str = Field(description="Description of changes made")
    files_changed: list[str] = Field(
        default_factory=list,
        description="List of file paths that were created or modified",
    )
    branch: str = Field(
        default="",
        description="Branch name where changes were pushed",
    )


class SizingFinding(_StrictSchema):
    """A single finding from repository analysis."""

    layer: int = Field(description="Migration layer (1-6)")
    category: str = Field(
        description="Finding category: prompt, model_config, tool, hitl, i18n, theme, connection, guardrail, form, persona"
    )
    file: str = Field(description="Relative file path")
    line: int = Field(description="Line number")
    description: str = Field(description="Human-readable finding description")
    impact: str = Field(description="One of: high, medium, low")
    code_snippet: str = Field(description="First 200 chars of matched code")
    language: str = Field(description="Source language: python or typescript")


class SizingLayerSummary(_StrictSchema):
    """Summary for one migration layer."""

    layer: int = Field(description="Layer number (1-6)")
    name: str = Field(description="Layer name: core, tools, frontend, governance, polish, code")
    findings_count: int = Field(description="Number of findings in this layer")
    estimated_effort: str = Field(description="Estimated effort (e.g., '2-3h')")
    is_breaking: bool = Field(description="Whether this layer modifies functional code")
    applicable: bool = Field(description="False if no findings for this layer")


class SizingOutput(_StrictSchema):
    """Structured output for the aap-sizing skill."""

    skill_output_type: str = Field(default="sizing", description="Always 'sizing'")
    repo_url: str = Field(description="Repository URL analyzed")
    repo_type: str = Field(description="'internal' or 'external'")
    languages: list[str] = Field(default_factory=list, description="Languages detected")
    total_findings: int = Field(description="Total number of findings")
    findings: list[SizingFinding] = Field(default_factory=list, description="All findings")
    layers: list[SizingLayerSummary] = Field(
        default_factory=list, description="Per-layer summaries"
    )
    proposed_structure: list[str] = Field(
        default_factory=list, description="Proposed .aap/ file paths"
    )


class MigrationOutput(_StrictSchema):
    """Structured output for the migrate-to-aap skill."""

    skill_output_type: str = Field(default="migration", description="Always 'migration'")
    layer: int = Field(description="Layer number executed (1-6)")
    layer_name: str = Field(description="Layer name")
    summary: str = Field(description="Summary of changes made")
    files_created: list[str] = Field(default_factory=list, description="New files created")
    files_modified: list[str] = Field(default_factory=list, description="Existing files modified")
    branch: str = Field(default="", description="Branch name")
    is_breaking: bool = Field(default=False, description="Whether changes are breaking")


# Map skill IDs to their expected output schema
SKILL_SCHEMAS: dict[str, type[BaseModel]] = {
    "code-review": ReviewOutput,
    "security-scan": ReviewOutput,
    "doc-generator": PROutput,
    "test-generator": PROutput,
    "project-docs": PROutput,
    "aap-sizing": SizingOutput,
    "migrate-to-aap": MigrationOutput,
}
