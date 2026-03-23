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


# Map skill IDs to their expected output schema
SKILL_SCHEMAS: dict[str, type[BaseModel]] = {
    "code-review": ReviewOutput,
    "security-scan": ReviewOutput,
    "doc-generator": PROutput,
    "test-generator": PROutput,
}
