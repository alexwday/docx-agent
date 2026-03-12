"""Data structures used by the DOCX service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RunStyleTemplate:
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    font_name: str | None = None
    font_size: Any = None
    font_color: Any = None


@dataclass(slots=True)
class ParagraphStyleTemplate:
    style_name: str | None = None
    alignment: Any = None
    left_indent: Any = None
    right_indent: Any = None
    first_line_indent: Any = None
    space_before: Any = None
    space_after: Any = None
    line_spacing: Any = None
    line_spacing_rule: Any = None
    run_style: RunStyleTemplate = field(default_factory=RunStyleTemplate)


@dataclass(slots=True)
class SelectorRange:
    start_index: int
    end_exclusive: int
    selector_mode: str
    selector_details: dict[str, Any]
