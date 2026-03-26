"""Format sizing JSON output using manifest templates."""

import json

from agent.config import get_formatting, get_manifest, get_module_name, get_temp_path_prefix
from agent.config.templates import render_template


def format_sizing_markdown(agent_response: str) -> str:
    """Format sizing JSON output as rich markdown for GitHub issue comments."""
    data = _parse_sizing_data(agent_response)
    if not data:
        return agent_response

    fmt = get_formatting()
    layer_icons = fmt.get("layerIcons", {}) if isinstance(fmt, dict) else {}
    severity_icons = fmt.get("severityIcons", {}) if isinstance(fmt, dict) else {}
    status_icons = fmt.get("statusIcons", {}) if isinstance(fmt, dict) else {}
    misc_icons = fmt.get("miscIcons", {}) if isinstance(fmt, dict) else {}
    repo_type_labels = fmt.get("repoTypeLabels", {}) if isinstance(fmt, dict) else {}

    manifest = get_manifest()
    module_name = get_module_name()
    if manifest and hasattr(manifest, "metadata"):
        module_name = getattr(manifest.metadata, "name", module_name)

    template_data = _build_template_data(
        data, layer_icons, severity_icons, status_icons, misc_icons, repo_type_labels, module_name
    )

    return render_template("sizingReport", template_data) or agent_response


def _parse_sizing_data(agent_response: str) -> dict | None:
    """Parse sizing JSON from agent response."""
    try:
        parsed = json.loads(agent_response)
        if isinstance(parsed, list):
            for block in parsed:
                if isinstance(block, dict) and block.get("text"):
                    try:
                        data = json.loads(block["text"])
                        if data.get("skill_output_type") == "sizing":
                            return data
                    except (json.JSONDecodeError, TypeError):
                        continue
        elif isinstance(parsed, dict) and parsed.get("skill_output_type") == "sizing":
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _build_template_data(
    data: dict,
    layer_icons: dict,
    severity_icons: dict,
    status_icons: dict,
    misc_icons: dict,
    repo_type_labels: dict,
    module_name: str,
) -> dict:
    """Build template context from sizing data + manifest formatting."""
    repo_type = data.get("repo_type", "unknown")

    layers = []
    for la in data.get("layers", []):
        num = la.get("layer", 0)
        icon = layer_icons.get(str(num), layer_icons.get(num, ""))
        is_breaking = la.get("is_breaking", False)
        layers.append(
            {
                "icon": icon,
                "layer": num,
                "name": la.get("name", ""),
                "count": la.get("count", la.get("findings_count", 0)),
                "breaking_label": (
                    f"{status_icons.get('failure', '')} Yes"
                    if is_breaking
                    else f"{status_icons.get('success', '')} No"
                ),
            }
        )

    findings = []
    for i, f in enumerate(data.get("findings", [])):
        imp = f.get("impact", "low")
        fp = f.get("file_path", f.get("file", "")).replace(get_temp_path_prefix(), "")
        desc = (f.get("title", "") or f.get("rationale", "") or f.get("description", ""))[:80]
        findings.append(
            {
                "index": i + 1,
                "layer": f.get("layer", "?"),
                "impact_icon": severity_icons.get(imp, ""),
                "impact": imp,
                "file": fp,
                "description": desc,
            }
        )

    next_steps = []
    for la in layers:
        icon = la["icon"]
        name = la["name"]
        breaking = "BREAKING" in la["breaking_label"]
        label = "BREAKING" if breaking else "Safe, non-breaking"
        next_steps.append(f"@{module_name} migrate --layer={name:<14s} # {icon} {label}")

    proposed = data.get("proposed_structure", [])

    return {
        "layer_icon_1": layer_icons.get("1", layer_icons.get(1, "")),
        "repo_url": data.get("repo_url", "N/A"),
        "repo_type_label": repo_type_labels.get(repo_type, ""),
        "languages": ", ".join(data.get("languages", [])),
        "total_findings": data.get("total_findings", 0),
        "layers": layers,
        "findings": findings,
        "findings_icon": misc_icons.get("clipboard", ""),
        "findings_count": len(findings),
        "proposed_structure": proposed,
        "folder_icon": misc_icons.get("folder", ""),
        "structure_count": len(proposed),
        "next_steps": next_steps,
    }
