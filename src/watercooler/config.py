"""Legacy path resolution (backward compatibility).

DEPRECATED: Use config_facade instead.

This module is maintained for backward compatibility only.
New code should use:
    from watercooler.config_facade import config
    threads_dir = config.paths.threads_dir

The implementation now delegates to path_resolver.py to eliminate
duplication with watercooler_mcp/config.py.
"""

from __future__ import annotations

from pathlib import Path


def resolve_threads_dir(cli_value: str | None = None) -> Path:
    """Resolve threads directory using precedence: CLI > env > git-aware default.

    DEPRECATED: Use config.get_threads_dir() instead.

    This function is maintained for backward compatibility.
    It now delegates to path_resolver.py.
    """
    from .path_resolver import resolve_threads_dir as _resolve
    return _resolve(cli_value)


def resolve_templates_dir(cli_value: str | None = None) -> Path:
    """Resolve templates directory using precedence: CLI > env > project-local > package default.

    DEPRECATED: Use config.paths.templates_dir instead.

    This function is maintained for backward compatibility.
    It now delegates to path_resolver.py.

    Precedence:
    1. CLI argument (--templates-dir)
    2. Environment variable (WATERCOOLER_TEMPLATES)
    3. Project-local templates (./.watercooler/templates/ if exists)
    4. Package bundled templates (always available as fallback)

    Returns Path to directory containing _TEMPLATE_*.md files.
    """
    from .path_resolver import resolve_templates_dir as _resolve
    return _resolve(cli_value)


def load_template(template_name: str, templates_dir: Path | None = None) -> str:
    """Load a template file with fallback to package bundled templates.

    Args:
        template_name: Name of template file (e.g., "_TEMPLATE_entry_block.md")
        templates_dir: Optional templates directory (uses resolve_templates_dir if None)

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If template not found in any location
    """
    if templates_dir is None:
        templates_dir = resolve_templates_dir()

    template_path = templates_dir / template_name

    # Try requested location first
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")

    # Fallback to package bundled templates
    bundled_path = Path(__file__).parent / "templates" / template_name
    if bundled_path.exists():
        return bundled_path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Template '{template_name}' not found in {templates_dir} or bundled templates"
    )
