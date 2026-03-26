"""Build structured execution reports for agent runs."""

import json
import re
import time

# Patterns to redact from public output
_SECRET_PATTERNS = [
    (r"(sk-[a-zA-Z0-9\-]{20,})", "[REDACTED_KEY]"),
    (r"(ghp_[a-zA-Z0-9]{36})", "[REDACTED_TOKEN]"),
    (r"(ghs_[a-zA-Z0-9]{36})", "[REDACTED_TOKEN]"),
    (r"(AKIA[0-9A-Z]{16})", "[REDACTED_AWS]"),
    (r"(Bearer\s+[a-zA-Z0-9\-._~+/]+=*)", "[REDACTED_BEARER]"),
    (r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]", r"\1=[REDACTED]"),
]


def _redact_secrets(text: str) -> str:
    """Redact potential secrets from text before embedding in public comments."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def build_execution_report(
    skill_id: str,
    model_id: str,
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    task: str,
    agent_response: str,
    has_changes: bool,
    branch_name: str,
    input_tokens: int,
    output_tokens: int,
    llm_calls: int,
    tool_calls: int,
    estimated_cost: float | None,
    start_time: float,
    pr_url: str = "",
    success: bool = True,
) -> str:
    """Build a markdown execution report for the GitHub issue comment.

    This replaces raw agent output with a structured report that answers:
    - What was the objective?
    - What did the agent do?
    - Was it successful?
    - How much did it cost?
    """
    elapsed = int(time.time() - start_time)
    mins, secs = divmod(elapsed, 60)
    duration = f"{mins}m{secs:02d}s"
    total_tokens = input_tokens + output_tokens
    cost_str = f"${estimated_cost:.4f}" if estimated_cost is not None else "N/A"

    # Status
    if success:
        status = "Success" if has_changes else "Success (no changes)"
        status_icon = "\u2705"
    else:
        status = "Failed"
        status_icon = "\u274c"

    # Objective section — show the original task
    task_preview = _extract_objective(task, skill_id, repo_owner, repo_name, issue_number)

    # What was done — extract from agent response
    summary = _extract_summary(agent_response, skill_id, has_changes, branch_name, pr_url)

    # Build guardrail suggestions from parsed agent response
    guardrail_suggestions = []
    try:
        parsed = json.loads(agent_response) if agent_response else None
        if parsed and isinstance(parsed, dict):
            guardrail_suggestions = parsed.get("suggested_guardrails", [])
    except (json.JSONDecodeError, TypeError):
        pass

    # Try template rendering first
    from agent.config.templates import render_template

    template_data = {
        "status_icon": status_icon,
        "status": status,
        "duration": duration,
        "cost": cost_str,
        "objective": task_preview,
        "summary": summary,
        "skill_id": skill_id or "swe-coder",
        "model_id": model_id,
        "llm_calls": llm_calls,
        "input_tokens": f"{input_tokens:,}" if input_tokens else "",
        "output_tokens": f"{output_tokens:,}" if output_tokens else "",
        "total_tokens": f"{total_tokens:,}" if total_tokens else "",
        "tool_calls": tool_calls,
        "estimated_cost": cost_str if estimated_cost is not None else "",
        "raw_output": _redact_secrets(agent_response[:5000]) if agent_response else "",
        "guardrail_suggestions": guardrail_suggestions,
        "guardrail_count": len(guardrail_suggestions),
    }

    rendered = render_template("executionReport", template_data)
    if rendered:
        return rendered

    # Fallback to Python formatting
    lines = [
        "## Agent Execution Report",
        "",
        f"**{status_icon} {status}** | **Duration:** {duration} | **Cost:** {cost_str}",
        "",
    ]

    lines.append("### Objective")
    lines.append(f"> {task_preview}")
    lines.append("")

    lines.append("### What was done")
    lines.append(summary)
    lines.append("")

    # Metrics table
    lines.append("### Metrics")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Skill** | `{skill_id or 'swe-coder'}` |")
    lines.append(f"| **Model** | `{model_id}` |")
    if llm_calls:
        lines.append(f"| LLM calls | {llm_calls} |")
    if total_tokens:
        lines.append(f"| Input tokens | {input_tokens:,} |")
        lines.append(f"| Output tokens | {output_tokens:,} |")
        lines.append(f"| Total tokens | {total_tokens:,} |")
    if tool_calls:
        lines.append(f"| Tool calls | {tool_calls} |")
    lines.append(f"| Duration | {duration} |")
    if estimated_cost is not None:
        lines.append(f"| **Estimated cost** | **{cost_str}** |")
    lines.append("")

    # Agent output in collapsible details (redact potential secrets)
    if agent_response:
        safe_output = _redact_secrets(agent_response[:5000])
        lines.append("<details>")
        lines.append("<summary>Raw agent output</summary>")
        lines.append("")
        lines.append(safe_output)
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def _extract_objective(
    task: str, skill_id: str, repo_owner: str, repo_name: str, issue_number: int
) -> str:
    """Extract a clean objective from the task string."""
    skill_descriptions = {
        "code-review": f"Review PR #{issue_number} on `{repo_owner}/{repo_name}` for code quality and correctness",
        "security-scan": f"Security scan PR #{issue_number} on `{repo_owner}/{repo_name}` for vulnerabilities",
        "aap-sizing": f"Analyze `{repo_owner}/{repo_name}` for AAP SDK migration sizing",
        "migrate-to-aap": f"Migrate `{repo_owner}/{repo_name}` to AAP SDK manifest architecture (Layers 1-6)",
        "doc-generator": f"Generate documentation for `{repo_owner}/{repo_name}`",
        "test-generator": f"Generate tests for `{repo_owner}/{repo_name}`",
        "project-docs": f"Generate project documentation for `{repo_owner}/{repo_name}`",
    }

    if skill_id in skill_descriptions:
        return skill_descriptions[skill_id]

    # Fallback: first line of task, cleaned up
    first_line = task.split("\n")[0][:200].strip()
    if first_line.startswith("Issue #"):
        return first_line
    return f"Execute task on `{repo_owner}/{repo_name}`: {first_line}"


def _extract_summary(
    agent_response: str,
    skill_id: str,
    has_changes: bool,
    branch_name: str,
    pr_url: str,
) -> str:
    """Extract a human-readable summary of what the agent did."""
    # Try to parse structured output
    data = None
    try:
        data = json.loads(agent_response)
    except (json.JSONDecodeError, TypeError):
        pass

    if data and isinstance(data, dict):
        output_type = data.get("skill_output_type", "")

        if output_type == "review":
            comments = data.get("comments", [])
            score = data.get("score", "N/A")
            summary = data.get("summary", "")
            guardrails = data.get("suggested_guardrails", [])
            severities = {}
            for c in comments:
                sev = c.get("severity", "info")
                severities[sev] = severities.get(sev, 0) + 1
            sev_str = ", ".join(f"{v} {k}" for k, v in sorted(severities.items()))
            lines = [
                f"- Reviewed PR and scored **{score}**",
                f"- Found **{len(comments)} findings** ({sev_str})"
                if comments
                else "- No findings",
                f"- {summary}" if summary else "",
            ]
            if guardrails:
                lines.append("")
                lines.append(f"**Suggested guardrails** ({len(guardrails)}):")
                for g in guardrails:
                    name = g.get("name", "unknown")
                    desc = g.get("description", "")
                    phase = g.get("phase", "input")
                    action = g.get("action", "block")
                    lines.append(f"- `{name}` — {desc} ({phase}/{action})")
            return "\n".join(line for line in lines if line)

        if output_type == "sizing":
            total = data.get("total_findings", 0)
            layers = data.get("layers", [])
            repo_url = data.get("repo_url", "")
            lines = [
                f"- Analyzed `{repo_url}`" if repo_url else "- Analyzed repository",
                f"- Found **{total} findings** across {len(layers)} layers",
            ]
            for la in layers:
                name = la.get("name", "")
                count = la.get("count", la.get("findings_count", 0))
                if count:
                    lines.append(f"  - Layer {la.get('layer', '?')} ({name}): {count} findings")
            return "\n".join(lines)

        if output_type == "migration":
            layer = data.get("layer", 0)
            summary = data.get("summary", "")
            files_created = data.get("files_created", [])
            files_modified = data.get("files_modified", [])
            lines = [
                f"- Completed **Layer {layer}** migration",
                f"- {summary}" if summary else "",
                f"- Created {len(files_created)} files, modified {len(files_modified)} files"
                if files_created or files_modified
                else "",
            ]
            if branch_name:
                lines.append(f"- Branch: `{branch_name}`")
            if pr_url:
                lines.append(f"- PR: {pr_url}")
            return "\n".join(line for line in lines if line)

        if output_type == "pr":
            summary = data.get("summary", "")
            files = data.get("files_changed", [])
            lines = [
                f"- {summary}" if summary else "- Generated changes",
                f"- Changed {len(files)} files" if files else "",
            ]
            if branch_name:
                lines.append(f"- Branch: `{branch_name}`")
            if pr_url:
                lines.append(f"- PR: {pr_url}")
            return "\n".join(line for line in lines if line)

    # Fallback for unstructured responses
    if has_changes:
        lines = ["- Agent made changes and pushed to branch"]
        if branch_name:
            lines.append(f"- Branch: `{branch_name}`")
        if pr_url:
            lines.append(f"- PR: {pr_url}")
        return "\n".join(lines)

    # Last resort: first 200 chars of response
    preview = agent_response[:200].replace("\n", " ").strip()
    return f"- {preview}" if preview else "- Agent completed without making changes"
