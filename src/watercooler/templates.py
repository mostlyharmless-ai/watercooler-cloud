from __future__ import annotations


def _fill_template(src: str, mapping: dict[str, str]) -> str:
    out = src
    for k, v in mapping.items():
        out = out.replace(f"{{{{{k}}}}}", v)
    return out
