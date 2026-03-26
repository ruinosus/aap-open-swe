"""Template rendering engine — loads .hbs files from manifest and renders with chevron."""

import logging
from pathlib import Path

import chevron

from .manifest import _mi

logger = logging.getLogger("templates")

# Cache loaded template strings
_template_cache: dict[str, str] = {}

# Known template name → filename mapping (convention-based fallback)
_TEMPLATE_FILES = {
    "executionReport": "execution-report.hbs",
    "sizingReport": "sizing-report.hbs",
    "reviewSummary": "review-summary.hbs",
    "progressComment": "progress-comment.hbs",
    "prDescription": "pr-description.hbs",
}


def _find_template_file(name: str) -> Path | None:
    """Find a template file by name, checking manifest config then convention."""
    # Try manifest spec.templates first
    try:
        mi = _mi()
        spec = mi.manifest
        templates = getattr(getattr(spec, "spec", None), "templates", None)
        if templates:
            path_str = (
                templates.get(name)
                if isinstance(templates, dict)
                else getattr(templates, name, None)
            )
            if path_str:
                manifest_dir = Path(mi.path) if mi.path else Path(".aap/open-swe")
                template_path = manifest_dir / path_str
                if template_path.exists():
                    return template_path
    except Exception:
        pass

    # Convention-based fallback: look in .aap/open-swe/templates/
    filename = _TEMPLATE_FILES.get(name)
    if filename:
        for base in [Path(".aap/open-swe/templates"), Path("../../.aap/open-swe/templates")]:
            path = base / filename
            if path.exists():
                return path

    return None


def get_template(name: str) -> str | None:
    """Load a template by name.

    Args:
        name: Template name (e.g., "executionReport", "sizingReport")

    Returns:
        Template string or None if not found.
    """
    if name in _template_cache:
        return _template_cache[name]

    path = _find_template_file(name)
    if not path:
        return None

    content = path.read_text()
    _template_cache[name] = content
    return content


def render_template(name: str, data: dict) -> str | None:
    """Load a template by name and render it with the given data.

    Returns rendered string, or None if template not found.
    """
    template = get_template(name)
    if template is None:
        return None
    return chevron.render(template, data)


def render_string(template: str, data: dict) -> str:
    """Render a template string directly."""
    return chevron.render(template, data)
