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
    lines = []

    lines.append("## \U0001f4ca AAP SDK Migration \u2014 Sizing Report")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Repository** | {data.get('repo_url', 'N/A')} |")
    repo_type = data.get("repo_type", "unknown")
    type_label = (
        "\U0001f500 External (fork required)" if repo_type == "external" else "\U0001f3e0 Internal"
    )
    lines.append(f"| **Type** | {type_label} |")
    lines.append(f"| **Languages** | {', '.join(data.get('languages', []))} |")
    lines.append(f"| **Total Findings** | **{data.get('total_findings', 0)}** |")
    lines.append("")

    layers = data.get("layers", [])
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

    findings = data.get("findings", [])
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

    proposed = data.get("proposed_structure", [])
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
    lines.append("@aap-open-swe migrate --layer=core        # \U0001f9f1 Safe, non-breaking")
    lines.append("@aap-open-swe migrate --layer=tools       # \U0001f527 Safe, non-breaking")
    lines.append("@aap-open-swe migrate --layer=frontend    # \U0001f3a8 \u26a0\ufe0f BREAKING")
    lines.append("@aap-open-swe migrate --layer=governance  # \U0001f6e1\ufe0f Safe, non-breaking")
    lines.append("@aap-open-swe migrate --layer=polish      # \u2728 Safe, non-breaking")
    lines.append(
        "@aap-open-swe migrate --layer=code        # \U0001f4bb \u26a0\ufe0f BREAKING (refactors source)"
    )
    lines.append("```")

    return "\n".join(lines)
