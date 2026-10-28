"""Bundled workbench user manual for the AI assistant.

The desktop 使用帮助 panel renders the manual that ships inside the API
image at ``fde_api/control/bundled/help_manual.md``. Without that copy the
server-side model has no grounding for "how do I use the workbench"
questions — the chat flow only feeds it conversation history. The manual is
reference data, not instructions: text inside it never changes what the
assistant is allowed to do.
"""
from __future__ import annotations

import re
from importlib import resources

_SECTION_HEADER = re.compile(r"^##\s+(?:([0-9]+)\.\s*)?(.+?)\s*$", re.MULTILINE)
_WINDOW_CHARS = 16_000


def _manual_text() -> str | None:
    try:
        return resources.files("fde_api.control.bundled").joinpath("help_manual.md").read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None


def _sections(text: str) -> list[tuple[str, str, int]]:
    """(number, title, char offset) for every ``## `` section."""
    return [(match.group(1) or "", match.group(2), match.start())
            for match in _SECTION_HEADER.finditer(text)]


def section_index() -> list[dict[str, str]]:
    text = _manual_text()
    if text is None:
        return []
    sections = _sections(text)
    return [{"number": number, "title": title, "characters": str(end - start)}
            for (number, title, start), end in zip(sections, [s[2] for s in sections[1:]] + [len(text)])]


def fetch_section(heading: str = "", start: int = 0) -> dict[str, object]:
    """Return one bounded window of the manual, anchored on a section title.

    ``heading`` matches a section title case-insensitively; an empty or
    unmatched heading keeps ``start`` so the caller can page through.
    """
    from fde_api.control.service import ControlServiceError

    text = _manual_text()
    if text is None:
        raise ControlServiceError("help_unavailable", "使用手册未随镜像分发，无法检索。", 409)
    if type(start) is not int or start < 0:
        raise ControlServiceError("invalid_request", "正文偏移无效。", 400)
    offset = start
    matched = ""
    if heading.strip():
        wanted = heading.strip().lower()
        for number, title, pos in _sections(text):
            if wanted in title.lower():
                offset = pos
                matched = title
                break
    end = min(len(text), offset + _WINDOW_CHARS)
    return {"source": "workbench_help_manual", "heading": matched, "text": text[offset:end],
            "offset": offset, "next_offset": end if end < len(text) else None,
            "total_characters": len(text),
            "sections": [{"number": n, "title": t} for n, t, _ in _sections(text)]}


def section_titles() -> list[str]:
    text = _manual_text()
    if text is None:
        return []
    return [title for _, title, _ in _sections(text)]
