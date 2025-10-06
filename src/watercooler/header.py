from __future__ import annotations


def _header_split(text: str) -> tuple[str, str]:
    parts = text.split("\n\n", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _replace_header_line(block: str, key: str, value: str) -> str:
    lines = block.splitlines()
    pref = f"{key}:"
    replaced = False
    for i, ln in enumerate(lines):
        if ln.lower().startswith(pref.lower()):
            lines[i] = f"{key}: {value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def bump_header(text: str, *, status: str | None = None, ball: str | None = None) -> str:
    header, body = _header_split(text)
    if status is not None:
        header = _replace_header_line(header, "Status", status)
    if ball is not None:
        header = _replace_header_line(header, "Ball", ball)
    # Always include a separating blank line to preserve header/body structure
    return header + "\n\n" + (body or "")
