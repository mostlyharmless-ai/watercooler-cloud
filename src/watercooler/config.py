from __future__ import annotations

import os
from pathlib import Path


def resolve_threads_dir(cli_value: str | None = None) -> Path:
    """Resolve threads directory using precedence: CLI > env > default.

    Env var: WATERCOOLER_DIR
    Default: ./watercooler
    """
    if cli_value:
        return Path(cli_value)
    env = os.getenv("WATERCOOLER_DIR")
    if env:
        return Path(env)
    return Path("watercooler")


def resolve_templates_dir(cli_value: str | None = None) -> Path:
    """Resolve templates directory using precedence: CLI > env > project-local > package default.

    Precedence:
    1. CLI argument (--templates-dir)
    2. Environment variable (WATERCOOLER_TEMPLATES)
    3. Project-local templates (./watercooler/ if exists)
    4. Package bundled templates (always available as fallback)

    Returns Path to directory containing _TEMPLATE_*.md files.
    """
    if cli_value:
        return Path(cli_value)
    env = os.getenv("WATERCOOLER_TEMPLATES")
    if env:
        return Path(env)
    # Check for project-local templates
    project_local = Path("watercooler")
    if project_local.exists() and project_local.is_dir():
        return project_local
    # Fallback to package bundled templates
    # This returns src/watercooler/templates/ in development
    # or site-packages/watercooler/templates/ when installed
    return Path(__file__).parent / "templates"


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

