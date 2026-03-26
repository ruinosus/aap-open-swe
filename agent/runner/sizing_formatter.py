import json


def format_sizing_markdown(agent_response: str) -> str:
    """Format sizing JSON output as rich markdown for GitHub issue comments."""
    data = None
    try:
        parsed = json.loads(agent_response)
        if isinstance(parsed, list):
            for block in parsed:
                if isinstance(block, dict) and block.get("text"):
                    try:
                        data = json.loads(block["text"])
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue
        elif isinstance(parsed, dict) and parsed.get("skill_output_type"):
            data = parsed
    except (json.JSONDecodeError, TypeError):
        pass

    if not data or data.get("skill_output_type") != "sizing":
        return agent_response

    layer_emoji = {
        1: "\U0001f9f1",
        2: "\U0001f527",
        3: "\U0001f3a8",
        4: "\U0001f6e1\ufe0f",
        5: "\u2728",
        6: "\U0001f4bb",
    }
    impact_emoji = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}

    # Try template rendering first
    from agent.config.templates import render_template

    repo_type = data.get("repo_type", "unknown")
    type_label = (
        "\U0001f500 External (fork required)" if repo_type == "external" else "\U0001f3e0 Internal"
    )

    layers = data.get("layers", [])
    template_layers = []
    for la in layers:
        num = la.get("layer", 0)
        template_layers.append(
            {
                "icon": layer_emoji.get(num, "\U0001f4e6"),
                "layer": num,
                "name": la.get("name", ""),
                "count": la.get("count", la.get("findings_count", 0)),
                "breaking_label": "\u26a0\ufe0f Yes" if la.get("is_breaking") else "\u2705 No",
            }
        )

    findings = data.get("findings", [])
    template_findings = []
    for i, f in enumerate(findings):
        imp = f.get("impact", "low")
        fp = f.get("file_path", f.get("file", "")).replace("/tmp/aap-sizing-target/", "")
        desc = (f.get("title", "") or f.get("rationale", "") or f.get("description", ""))[:80]
        template_findings.append(
            {
                "index": i + 1,
                "layer": f.get("layer", "?"),
                "impact_icon": impact_emoji.get(imp, "\u26aa"),
                "impact": imp,
                "file": fp,
                "description": desc,
            }
        )

    proposed = data.get("proposed_structure", [])

    next_steps = [
        "@aap-open-swe migrate --layer=core        # \U0001f9f1 Safe, non-breaking",
        "@aap-open-swe migrate --layer=tools       # \U0001f527 Safe, non-breaking",
        "@aap-open-swe migrate --layer=frontend    # \U0001f3a8 \u26a0\ufe0f BREAKING",
        "@aap-open-swe migrate --layer=governance  # \U0001f6e1\ufe0f Safe, non-breaking",
        "@aap-open-swe migrate --layer=polish      # \u2728 Safe, non-breaking",
        "@aap-open-swe migrate --layer=code        # \U0001f4bb \u26a0\ufe0f BREAKING (refactors source)",
    ]

    template_data = {
        "layer_icon_1": layer_emoji.get(1, "\U0001f4e6"),
        "repo_url": data.get("repo_url", "N/A"),
        "repo_type_label": type_label,
        "languages": ", ".join(data.get("languages", [])),
        "total_findings": data.get("total_findings", 0),
        "layers": template_layers,
        "findings": template_findings,
        "findings_icon": "\U0001f4cb",
        "findings_count": len(findings),
        "proposed_structure": proposed,
        "folder_icon": "\U0001f4c1",
        "structure_count": len(proposed),
        "next_steps": next_steps,
    }

    rendered = render_template("sizingReport", template_data)
    if rendered:
        return rendered

    # Fallback to Python formatting
    lines = []

    lines.append("## \U0001f4ca AAP SDK Migration \u2014 Sizing Report")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Repository** | {data.get('repo_url', 'N/A')} |")
    lines.append(f"| **Type** | {type_label} |")
    lines.append(f"| **Languages** | {', '.join(data.get('languages', []))} |")
    lines.append(f"| **Total Findings** | **{data.get('total_findings', 0)}** |")
    lines.append("")

    if layers:
        lines.append("### Layers")
        lines.append("")
        lines.append("| Layer | Name | Findings | Breaking? |")
        lines.append("|-------|------|----------|-----------|")
        for la in layers:
            num = la.get("layer", 0)
            emoji = layer_emoji.get(num, "\U0001f4e6")
            name = la.get("name", "")
            count = la.get("count", la.get("findings_count", 0))
            breaking = "\u26a0\ufe0f Yes" if la.get("is_breaking") else "\u2705 No"
            lines.append(f"| {emoji} {num} | **{name}** | {count} | {breaking} |")
        lines.append("")

    if findings:
        lines.append("<details>")
        lines.append(f"<summary>\U0001f4cb Detailed Findings ({len(findings)})</summary>")
        lines.append("")
        lines.append("| # | Layer | Impact | File | Description |")
        lines.append("|---|-------|--------|------|-------------|")
        for i, f in enumerate(findings):
            imp = f.get("impact", "low")
            ie = impact_emoji.get(imp, "\u26aa")
            fp = f.get("file_path", f.get("file", "")).replace("/tmp/aap-sizing-target/", "")
            desc = (f.get("title", "") or f.get("rationale", "") or f.get("description", ""))[:80]
            lines.append(f"| {i + 1} | L{f.get('layer', '?')} | {ie} {imp} | `{fp}` | {desc} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if proposed:
        lines.append("<details>")
        lines.append(
            f"<summary>\U0001f4c1 Proposed .aap/ Structure ({len(proposed)} files)</summary>"
        )
        lines.append("")
        lines.append("```")
        for p in proposed:
            lines.append(p)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("### Next Steps")
    lines.append("")
    lines.append("```")
    for step in next_steps:
        lines.append(step)
    lines.append("```")

    return "\n".join(lines)
