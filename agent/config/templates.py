"""Template rendering engine — loads .hbs files from manifest and renders with chevron."""

import logging
from pathlib import Path

import chevron

from .manifest import _mi

logger = logging.getLogger("templates")

# Cache loaded template strings
_template_cache: dict[str, str] = {}


def _manifest_dir() -> Path:
    """Get the .aap/open-swe/ directory path."""
    mi = _mi()
    return Path(mi.path) if mi.path else Path(".aap/open-swe")


def get_template(name: str) -> str | None:
    """Load a template by name from spec.templates.

    Args:
        name: Template name (e.g., "executionReport", "sizingReport")

    Returns:
        Template string or None if not found.
    """
    if name in _template_cache:
        return _template_cache[name]

    mi = _mi()
    spec = mi.manifest
    templates = getattr(getattr(spec, "spec", None), "templates", None)
    if not templates:
        return None

    # templates is a dict or object with template names as keys
    path_str = (
        templates.get(name) if isinstance(templates, dict) else getattr(templates, name, None)
    )
    if not path_str:
        return None

    # Resolve relative to manifest directory
    template_path = _manifest_dir() / path_str
    if not template_path.exists():
        logger.warning("Template file not found: %s", template_path)
        return None

    content = template_path.read_text()
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
