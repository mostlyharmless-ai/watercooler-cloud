"""Parsing utilities for watercooler thread entries.

These helpers expose structured metadata for individual entries inside a
thread markdown file so higher layers (CLI, MCP, etc.) can work with
entry-level operations without reparsing the raw file repeatedly.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional


_ENTRY_LINE_RE = re.compile(
    r"^Entry:\s*(?P<agent>.+?)\s+(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s*$"
)
_ENTRY_ID_RE = re.compile(r"<!--\s*Entry-ID:\s*([A-Za-z0-9_-]+)\s*-->", re.IGNORECASE)


@dataclass(frozen=True)
class ThreadEntry:
    """Structured representation of a single thread entry."""

    index: int
    header: str
    body: str
    agent: Optional[str]
    timestamp: Optional[str]
    role: Optional[str]
    entry_type: Optional[str]
    title: Optional[str]
    entry_id: Optional[str]
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int


def parse_thread_entries(text: str) -> List[ThreadEntry]:
    """Parse thread entries from a markdown thread file.

    Args:
        text: Full thread markdown content.

    Returns:
        A list of ``ThreadEntry`` instances in order of appearance.
    """

    if not text:
        return []

    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    separator_indexes = [idx for idx, line in enumerate(lines) if line.strip() == "---"]
    if not separator_indexes:
        return []

    header_end_index = separator_indexes[0]
    current_index = header_end_index + 1

    line_starts: List[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line)

    entries: List[ThreadEntry] = []
    entry_counter = 0

    while current_index < len(lines):
        # Skip leading blank lines between separators and the entry header
        while current_index < len(lines) and lines[current_index].strip() == "":
            current_index += 1

        if current_index >= len(lines):
            break

        entry_start_index = current_index

        # Gather lines until the next separator (or EOF)
        inner_index = current_index
        while inner_index < len(lines) and lines[inner_index].strip() != "---":
            inner_index += 1

        entry_line_slice = lines[entry_start_index:inner_index]

        # Prepare next loop iteration (skip separator if present)
        current_index = inner_index + 1 if inner_index < len(lines) else inner_index

        if not entry_line_slice:
            continue

        header_lines, body_lines = _split_entry_header_body(entry_line_slice)

        metadata = _parse_entry_header(header_lines)
        entry_id = _extract_entry_id(entry_line_slice)

        header_text = "".join(header_lines).rstrip("\n")
        body_text = "".join(body_lines).rstrip("\n")

        end_line_index = _resolve_last_content_line(entry_line_slice, entry_start_index)

        entry = ThreadEntry(
            index=entry_counter,
            header=header_text,
            body=body_text,
            agent=metadata.agent,
            timestamp=metadata.timestamp,
            role=metadata.role,
            entry_type=metadata.entry_type,
            title=metadata.title,
            entry_id=entry_id,
            start_line=entry_start_index + 1,
            end_line=end_line_index + 1,
            start_offset=line_starts[entry_start_index],
            end_offset=line_starts[end_line_index] + len(lines[end_line_index]),
        )
        entries.append(entry)
        entry_counter += 1

    return entries


@dataclass(frozen=True)
class _EntryMetadata:
    agent: Optional[str]
    timestamp: Optional[str]
    role: Optional[str]
    entry_type: Optional[str]
    title: Optional[str]


def _split_entry_header_body(entry_lines: Iterable[str]) -> tuple[List[str], List[str]]:
    header_lines: List[str] = []
    body_lines: List[str] = []
    in_header = True

    for line in entry_lines:
        if in_header:
            if line.strip() == "":
                in_header = False
                continue
            header_lines.append(line)
        else:
            body_lines.append(line)

    return header_lines, body_lines


def _parse_entry_header(header_lines: Iterable[str]) -> _EntryMetadata:
    agent: Optional[str] = None
    timestamp: Optional[str] = None
    role: Optional[str] = None
    entry_type: Optional[str] = None
    title: Optional[str] = None

    for raw_line in header_lines:
        line = raw_line.strip()
        if not line:
            continue

        match = _ENTRY_LINE_RE.match(line)
        if match:
            agent = match.group("agent").strip()
            timestamp = match.group("timestamp").strip()
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "role":
            role = value
        elif key == "type":
            entry_type = value
        elif key == "title":
            title = value

    return _EntryMetadata(agent=agent, timestamp=timestamp, role=role, entry_type=entry_type, title=title)


def _extract_entry_id(entry_lines: Iterable[str]) -> Optional[str]:
    joined = "".join(entry_lines)
    match = _ENTRY_ID_RE.search(joined)
    if not match:
        return None
    return match.group(1).strip() or None


def _resolve_last_content_line(entry_lines: List[str], entry_start_index: int) -> int:
    """Return absolute line index for the last line with content in the entry."""

    for reverse_offset, line in enumerate(reversed(entry_lines)):
        if line.strip():
            return entry_start_index + len(entry_lines) - 1 - reverse_offset
    # Fallback to the first line when everything is blank (should be rare)
    return entry_start_index

