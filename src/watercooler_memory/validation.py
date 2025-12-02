"""Schema validation for LeanRAG export format.

Defines JSON schemas and validation functions to ensure export
format compatibility with LeanRAG's expected input.
"""

from __future__ import annotations

from typing import Any

# JSON Schema for LeanRAG chunk format (minimal required fields)
LEANRAG_CHUNK_SCHEMA = {
    "type": "object",
    "required": ["hash_code", "text"],
    "properties": {
        "hash_code": {
            "type": "string",
            "description": "Unique identifier for the chunk",
            "minLength": 1,
        },
        "text": {
            "type": "string",
            "description": "Text content of the chunk",
        },
        "embedding": {
            "type": ["array", "null"],
            "items": {"type": "number"},
            "description": "Vector embedding (optional)",
        },
        "metadata": {
            "type": "object",
            "description": "Additional metadata",
        },
    },
}

# JSON Schema for LeanRAG document format
LEANRAG_DOCUMENT_SCHEMA = {
    "type": "object",
    "required": ["doc_id", "content", "chunks"],
    "properties": {
        "doc_id": {
            "type": "string",
            "description": "Unique document identifier",
            "minLength": 1,
        },
        "title": {
            "type": ["string", "null"],
            "description": "Document title",
        },
        "content": {
            "type": "string",
            "description": "Full document content",
        },
        "summary": {
            "type": ["string", "null"],
            "description": "Document summary (optional)",
        },
        "chunks": {
            "type": "array",
            "items": LEANRAG_CHUNK_SCHEMA,
            "description": "List of chunks",
        },
        "metadata": {
            "type": "object",
            "description": "Document metadata",
        },
        "embedding": {
            "type": ["array", "null"],
            "items": {"type": "number"},
            "description": "Document-level embedding (optional)",
        },
    },
}

# JSON Schema for LeanRAG thread format
LEANRAG_THREAD_SCHEMA = {
    "type": "object",
    "required": ["thread_id"],
    "properties": {
        "thread_id": {
            "type": "string",
            "description": "Thread topic identifier",
            "minLength": 1,
        },
        "title": {
            "type": ["string", "null"],
            "description": "Thread title",
        },
        "status": {
            "type": ["string", "null"],
            "description": "Thread status (OPEN, CLOSED, etc.)",
        },
        "ball": {
            "type": ["string", "null"],
            "description": "Current ball owner",
        },
        "created_at": {
            "type": ["string", "null"],
            "description": "Thread creation timestamp",
        },
        "updated_at": {
            "type": ["string", "null"],
            "description": "Last update timestamp",
        },
        "summary": {
            "type": ["string", "null"],
            "description": "Thread summary",
        },
        "entry_count": {
            "type": "integer",
            "minimum": 0,
        },
        "entry_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}

# JSON Schema for LeanRAG manifest
LEANRAG_MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["format", "version", "statistics", "files"],
    "properties": {
        "format": {
            "type": "string",
            "const": "leanrag",
        },
        "version": {
            "type": "string",
            "pattern": r"^\d+\.\d+$",
        },
        "source": {
            "type": "string",
        },
        "statistics": {
            "type": "object",
            "required": ["threads", "documents", "chunks"],
            "properties": {
                "threads": {"type": "integer", "minimum": 0},
                "documents": {"type": "integer", "minimum": 0},
                "chunks": {"type": "integer", "minimum": 0},
                "embeddings_included": {"type": "boolean"},
            },
        },
        "files": {
            "type": "object",
            "required": ["documents", "threads"],
            "properties": {
                "documents": {"type": "string"},
                "threads": {"type": "string"},
            },
        },
    },
}

# JSON Schema for pipeline chunk format (minimal for LeanRAG ingestion)
LEANRAG_PIPELINE_CHUNK_SCHEMA = {
    "type": "object",
    "required": ["hash_code", "text"],
    "properties": {
        "hash_code": {
            "type": "string",
            "minLength": 1,
        },
        "text": {
            "type": "string",
        },
        "embedding": {
            "type": ["array", "null"],
            "items": {"type": "number"},
        },
        "metadata": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "thread_id": {"type": "string"},
                "entry_id": {"type": "string"},
                "chunk_index": {"type": "integer"},
                "event_time": {"type": ["string", "null"]},
                "agent": {"type": ["string", "null"]},
                "role": {"type": ["string", "null"]},
                "entry_type": {"type": ["string", "null"]},
                "entry_title": {"type": ["string", "null"]},
            },
        },
    },
}


class ValidationError(Exception):
    """Raised when export validation fails."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or []


def validate_chunk(chunk: dict[str, Any]) -> list[str]:
    """Validate a single chunk against LeanRAG schema.

    Args:
        chunk: Chunk dictionary to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Required fields
    if "hash_code" not in chunk:
        errors.append("Missing required field: hash_code")
    elif not isinstance(chunk["hash_code"], str) or not chunk["hash_code"]:
        errors.append("hash_code must be a non-empty string")

    if "text" not in chunk:
        errors.append("Missing required field: text")
    elif not isinstance(chunk["text"], str):
        errors.append("text must be a string")

    # Optional embedding validation
    if "embedding" in chunk and chunk["embedding"] is not None:
        if not isinstance(chunk["embedding"], list):
            errors.append("embedding must be a list or null")
        elif not all(isinstance(x, (int, float)) for x in chunk["embedding"]):
            errors.append("embedding must contain only numbers")

    return errors


def validate_document(doc: dict[str, Any]) -> list[str]:
    """Validate a document against LeanRAG schema.

    Args:
        doc: Document dictionary to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Required fields
    if "doc_id" not in doc:
        errors.append("Missing required field: doc_id")
    elif not isinstance(doc["doc_id"], str) or not doc["doc_id"]:
        errors.append("doc_id must be a non-empty string")

    if "content" not in doc:
        errors.append("Missing required field: content")
    elif not isinstance(doc["content"], str):
        errors.append("content must be a string")

    if "chunks" not in doc:
        errors.append("Missing required field: chunks")
    elif not isinstance(doc["chunks"], list):
        errors.append("chunks must be a list")
    else:
        for i, chunk in enumerate(doc["chunks"]):
            chunk_errors = validate_chunk(chunk)
            for err in chunk_errors:
                errors.append(f"chunks[{i}]: {err}")

    return errors


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Validate a manifest against LeanRAG schema.

    Args:
        manifest: Manifest dictionary to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Required fields
    if manifest.get("format") != "leanrag":
        errors.append("format must be 'leanrag'")

    if "version" not in manifest:
        errors.append("Missing required field: version")

    if "statistics" not in manifest:
        errors.append("Missing required field: statistics")
    else:
        stats = manifest["statistics"]
        for field in ["threads", "documents", "chunks"]:
            if field not in stats:
                errors.append(f"statistics missing required field: {field}")
            elif not isinstance(stats[field], int) or stats[field] < 0:
                errors.append(f"statistics.{field} must be a non-negative integer")

    if "files" not in manifest:
        errors.append("Missing required field: files")
    else:
        files = manifest["files"]
        for field in ["documents", "threads"]:
            if field not in files:
                errors.append(f"files missing required field: {field}")

    return errors


def validate_export(
    documents: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """Validate a complete LeanRAG export.

    Args:
        documents: List of document dictionaries.
        threads: List of thread dictionaries.
        manifest: Export manifest dictionary.

    Raises:
        ValidationError: If any validation fails.
    """
    all_errors: list[dict[str, Any]] = []

    # Validate manifest
    manifest_errors = validate_manifest(manifest)
    if manifest_errors:
        all_errors.append({
            "type": "manifest",
            "errors": manifest_errors,
        })

    # Validate documents
    for i, doc in enumerate(documents):
        doc_errors = validate_document(doc)
        if doc_errors:
            all_errors.append({
                "type": "document",
                "index": i,
                "doc_id": doc.get("doc_id", "unknown"),
                "errors": doc_errors,
            })

    # Validate threads
    for i, thread in enumerate(threads):
        if "thread_id" not in thread:
            all_errors.append({
                "type": "thread",
                "index": i,
                "errors": ["Missing required field: thread_id"],
            })

    # Check consistency
    manifest_doc_count = manifest.get("statistics", {}).get("documents", 0)
    if manifest_doc_count != len(documents):
        all_errors.append({
            "type": "consistency",
            "errors": [
                f"Manifest documents count ({manifest_doc_count}) "
                f"does not match actual count ({len(documents)})"
            ],
        })

    manifest_thread_count = manifest.get("statistics", {}).get("threads", 0)
    if manifest_thread_count != len(threads):
        all_errors.append({
            "type": "consistency",
            "errors": [
                f"Manifest threads count ({manifest_thread_count}) "
                f"does not match actual count ({len(threads)})"
            ],
        })

    if all_errors:
        raise ValidationError(
            f"Export validation failed with {len(all_errors)} error(s)",
            errors=all_errors,
        )


def validate_pipeline_chunks(chunks: list[dict[str, Any]]) -> None:
    """Validate chunks for LeanRAG pipeline consumption.

    Args:
        chunks: List of chunk dictionaries.

    Raises:
        ValidationError: If any chunk is invalid.
    """
    all_errors: list[dict[str, Any]] = []

    for i, chunk in enumerate(chunks):
        chunk_errors = validate_chunk(chunk)
        if chunk_errors:
            all_errors.append({
                "type": "chunk",
                "index": i,
                "hash_code": chunk.get("hash_code", "unknown"),
                "errors": chunk_errors,
            })

    if all_errors:
        raise ValidationError(
            f"Pipeline chunk validation failed with {len(all_errors)} error(s)",
            errors=all_errors,
        )
