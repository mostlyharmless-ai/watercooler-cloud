from __future__ import annotations

from textwrap import dedent

from watercooler.thread_entries import parse_thread_entries


def _sample_thread() -> str:
    return dedent(
        """\
        # sample-thread — Thread
        Status: OPEN
        Ball: Codex (caleb)
        Topic: sample-thread
        Created: 2025-01-01T00:00:00Z

        ---
        Entry: Codex (caleb) 2025-01-01T00:01:00Z
        Role: planner
        Type: Plan
        Title: First Entry

        Spec: planner
        Body line 1
        Body line 2
        <!-- Entry-ID: 01ABCDEF1234567890ABCDEFGH -->

        ---
        Entry: Claude (caleb) 2025-01-01T00:02:00Z
        Role: critic
        Type: Note
        Title: Second Entry

        Spec: critic
        Another body line
        <!-- Entry-ID: 01ABCDEF1234567890ABCDEFGJ -->
        """
    )


def test_parse_thread_entries_extracts_metadata() -> None:
    text = _sample_thread()
    entries = parse_thread_entries(text)

    assert len(entries) == 2

    first = entries[0]
    assert first.agent == "Codex (caleb)"
    assert first.timestamp == "2025-01-01T00:01:00Z"
    assert first.role == "planner"
    assert first.entry_type == "Plan"
    assert first.title == "First Entry"
    assert first.entry_id == "01ABCDEF1234567890ABCDEFGH"
    assert first.start_line == 8
    assert first.end_line == 18  # includes trailing blank + separator
    segment = text[first.start_offset:first.end_offset]
    assert "Entry: Codex (caleb)" in segment
    assert "<!-- Entry-ID: 01ABCDEF1234567890ABCDEFGH -->" in segment

    second = entries[1]
    assert second.index == 1
    assert second.entry_id == "01ABCDEF1234567890ABCDEFGJ"
    assert second.start_line > first.end_line
    assert "Another body line" in second.body


def test_parse_thread_entries_handles_missing_entries() -> None:
    text = dedent(
        """\
        # empty-thread — Thread
        Status: OPEN
        Ball: Codex (caleb)
        Topic: empty-thread
        Created: 2025-01-01T00:00:00Z
        """
    )
    assert parse_thread_entries(text) == []
