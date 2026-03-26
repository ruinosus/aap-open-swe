"""Build structured execution reports for agent runs."""

import json
import re
import time

from agent.config import (
    get_default_agent_id,
    get_formatting,
    get_output_truncation_limit,
    get_skill,
)
from agent.config.templates import render_template


def _redact_secrets(text: str) -> str:
    """Redact potential secrets from text before embedding in public comments."""
    # Patterns from the secret-redaction guardrail manifest
    patterns = [
        (r"(sk-[a-zA-Z0-9\-]{20,})", "[REDACTED_KEY]"),
        (r"(ghp_[a-zA-Z0-9]{36})", "[REDACTED_TOKEN]"),
        (r"(ghs_[a-zA-Z0-9]{36})", "[REDACTED_TOKEN]"),
        (r"(AKIA[0-9A-Z]{16})", "[REDACTED_AWS]"),
        (r"(Bearer\s+[a-zA-Z0-9\-._~+/]+=*)", "[REDACTED_BEARER]"),
        (
            r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
            r"\1=[REDACTED]",
        ),
    ]
    for pattern, replacement in patterns:
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
    """Build a markdown execution report."""
    elapsed = int(time.time() - start_time)
    mins, secs = divmod(elapsed, 60)
    duration = f"{mins}m{secs:02d}s"
    total_tokens = input_tokens + output_tokens
    cost_str = f"${estimated_cost:.4f}" if estimated_cost is not None else "N/A"

    # Icons from manifest
    fmt = get_formatting()
    status_icons = fmt.get("statusIcons", {}) if isinstance(fmt, dict) else {}

    if success:
        status = "Success" if has_changes else "Success (no changes)"
        status_icon = status_icons.get("success", "")
    else:
        status = "Failed"
        status_icon = status_icons.get("failure", "")

    # Objective from manifest skill description
    objective = _extract_objective(task, skill_id, repo_owner, repo_name)

    # Summary from agent response
    summary = _extract_summary(agent_response, skill_id, has_changes, branch_name, pr_url)

    # Guardrail suggestions from parsed response
    guardrail_suggestions = []
    try:
        parsed = json.loads(agent_response) if agent_response else None
        if parsed and isinstance(parsed, dict):
            guardrail_suggestions = parsed.get("suggested_guardrails", [])
    except (json.JSONDecodeError, TypeError):
        pass

    # Render template
    template_data = {
        "status_icon": status_icon,
        "status": status,
        "duration": duration,
        "cost": cost_str,
        "objective": objective,
        "summary": summary,
        "skill_id": skill_id or get_default_agent_id(),
        "model_id": model_id,
        "llm_calls": llm_calls,
        "input_tokens": f"{input_tokens:,}" if input_tokens else "",
        "output_tokens": f"{output_tokens:,}" if output_tokens else "",
        "total_tokens": f"{total_tokens:,}" if total_tokens else "",
        "tool_calls": tool_calls,
        "estimated_cost": cost_str if estimated_cost is not None else "",
        "raw_output": _redact_secrets(agent_response[: get_output_truncation_limit()])
        if agent_response
        else "",
        "guardrail_suggestions": guardrail_suggestions,
        "guardrail_count": len(guardrail_suggestions),
    }

    return render_template("executionReport", template_data) or ""


def _extract_objective(task: str, skill_id: str, repo_owner: str, repo_name: str) -> str:
    """Extract objective from manifest skill description."""
    skill = get_skill(skill_id)
    if skill and getattr(skill, "description", ""):
        return f"{skill.description} on `{repo_owner}/{repo_name}`"

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
    """Extract summary from agent response."""
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
            summary_text = data.get("summary", "")
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
                f"- {summary_text}" if summary_text else "",
            ]
            if guardrails:
                lines.append("")
                lines.append(f"**Suggested guardrails** ({len(guardrails)}):")
                for g in guardrails:
                    lines.append(
                        f"- `{g.get('name', '?')}` — {g.get('description', '')} ({g.get('phase', 'input')}/{g.get('action', 'block')})"
                    )
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
            summary_text = data.get("summary", "")
            files_created = data.get("files_created", [])
            files_modified = data.get("files_modified", [])
            lines = [
                f"- Completed **Layer {layer}** migration",
                f"- {summary_text}" if summary_text else "",
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
            summary_text = data.get("summary", "")
            files = data.get("files_changed", [])
            lines = [
                f"- {summary_text}" if summary_text else "- Generated changes",
                f"- Changed {len(files)} files" if files else "",
            ]
            if branch_name:
                lines.append(f"- Branch: `{branch_name}`")
            if pr_url:
                lines.append(f"- PR: {pr_url}")
            return "\n".join(line for line in lines if line)

    if has_changes:
        lines = ["- Agent made changes and pushed to branch"]
        if branch_name:
            lines.append(f"- Branch: `{branch_name}`")
        if pr_url:
            lines.append(f"- PR: {pr_url}")
        return "\n".join(lines)

    preview = agent_response[:200].replace("\n", " ").strip()
    return f"- {preview}" if preview else "- Agent completed without making changes"
