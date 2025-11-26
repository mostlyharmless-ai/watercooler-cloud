"""Schema validation utilities for Watercooler data structures.

This module provides utilities for validating ThreadEntry and WatercoolerThread
objects against the canonical JSON schemas defined in schemas/.

Note: Requires jsonschema package (install with 'pip install jsonschema')
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from jsonschema import validate, ValidationError, SchemaError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception  # type: ignore
    SchemaError = Exception  # type: ignore


def _get_schema_path(schema_name: str) -> Path:
    """Get path to a schema file.

    Args:
        schema_name: Name of schema file (e.g., 'thread_entry.schema.json')

    Returns:
        Path to schema file
    """
    # schemas/ is at repo root, one level up from src/watercooler
    repo_root = Path(__file__).parent.parent.parent
    return repo_root / "schemas" / schema_name


def load_schema(schema_name: str) -> Dict[str, Any]:
    """Load a JSON schema from schemas/ directory.

    Args:
        schema_name: Name of schema file (e.g., 'thread_entry.schema.json')

    Returns:
        Parsed schema as dictionary

    Raises:
        FileNotFoundError: If schema file doesn't exist
        json.JSONDecodeError: If schema is invalid JSON
    """
    schema_path = _get_schema_path(schema_name)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    return json.loads(schema_path.read_text())


def validate_thread_entry(entry_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a thread entry dictionary against canonical schema.

    Args:
        entry_dict: Dictionary representation of ThreadEntry

    Returns:
        Tuple of (is_valid, errors) where errors is list of error messages

    Example:
        >>> entry = {
        ...     "index": 0,
        ...     "header": "Entry: Claude (user) 2025-01-26T12:00:00Z",
        ...     "body": "Entry content",
        ...     "agent": "Claude (user)",
        ...     "timestamp": "2025-01-26T12:00:00Z",
        ...     "start_line": 10,
        ...     "end_line": 20,
        ...     "start_offset": 100,
        ...     "end_offset": 200,
        ... }
        >>> is_valid, errors = validate_thread_entry(entry)
        >>> assert is_valid and not errors
    """
    if not JSONSCHEMA_AVAILABLE:
        return False, ["jsonschema package not installed. Install with: pip install jsonschema"]

    try:
        schema = load_schema("thread_entry.schema.json")
        validate(instance=entry_dict, schema=schema)
        return True, []
    except ValidationError as e:
        return False, [str(e.message)]
    except SchemaError as e:
        return False, [f"Schema error: {e.message}"]
    except FileNotFoundError as e:
        return False, [str(e)]
    except json.JSONDecodeError as e:
        return False, [f"Invalid schema JSON: {e}"]


def validate_watercooler_thread(thread_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a thread dictionary against canonical schema.

    Args:
        thread_dict: Dictionary representation of WatercoolerThread

    Returns:
        Tuple of (is_valid, errors) where errors is list of error messages

    Example:
        >>> thread = {
        ...     "id": "feature-auth",
        ...     "title": "Authentication Feature",
        ...     "status": "OPEN",
        ...     "ball": "Claude (user)",
        ...     "topic": "feature-auth",
        ...     "created": "2025-01-26T12:00:00Z",
        ...     "priority": "P2",
        ...     "entries": [],
        ... }
        >>> is_valid, errors = validate_watercooler_thread(thread)
        >>> assert is_valid and not errors
    """
    if not JSONSCHEMA_AVAILABLE:
        return False, ["jsonschema package not installed. Install with: pip install jsonschema"]

    try:
        schema = load_schema("watercooler_thread.schema.json")
        validate(instance=thread_dict, schema=schema)
        return True, []
    except ValidationError as e:
        return False, [str(e.message)]
    except SchemaError as e:
        return False, [f"Schema error: {e.message}"]
    except FileNotFoundError as e:
        return False, [str(e)]
    except json.JSONDecodeError as e:
        return False, [f"Invalid schema JSON: {e}"]


def is_jsonschema_available() -> bool:
    """Check if jsonschema package is available.

    Returns:
        True if jsonschema is installed, False otherwise
    """
    return JSONSCHEMA_AVAILABLE
