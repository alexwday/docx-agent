"""Read PDF pages into RawSheet objects for ingestion."""

from __future__ import annotations

from pathlib import Path

from data_sources.models import RawSheet


def read_pdf_sheets(path: Path) -> list[RawSheet]:
    """Extract text from each PDF page, returning one RawSheet per page.

    Sheet names follow the convention ``Page_{N}`` (1-indexed) to match the
    naming style used by the Excel reader and the stress-test answer_pages field.
    """
    try:
        import pypdf  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "PDF ingestion requires pypdf: pip install pypdf"
        ) from exc

    sheets: list[RawSheet] = []
    reader = pypdf.PdfReader(str(path))

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        text = page.extract_text() or ""
        # Normalize whitespace while preserving paragraph structure
        lines = [line.rstrip() for line in text.splitlines()]
        raw_content = "\n".join(lines).strip()
        sheets.append(
            RawSheet(
                sheet_index=page_idx,
                sheet_name=f"Page_{page_num}",
                raw_content=raw_content,
            )
        )

    return sheets
