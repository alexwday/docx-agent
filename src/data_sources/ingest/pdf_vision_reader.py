"""Vision-based PDF reader.

Each PDF page is rendered to a PNG image and sent to an OpenAI vision model
which returns rich structured markdown:

  - OCR text (headers, bullet points, footnotes, disclaimers)
  - Markdown pipe tables (converted from visual tables)
  - Text descriptions of every chart, graph, or infographic

The resulting ``RawSheet.raw_content`` is used by the downstream
``extract_sheet_metadata`` step to generate keywords, metrics, and embeddings.

Requires: pip install pymupdf
"""

from __future__ import annotations

import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from data_sources.auth import build_openai_client
from data_sources.models import RawSheet

if TYPE_CHECKING:
    from data_sources.config import DataSourcesConfig

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_S = 2.0

# Retryable OpenAI errors — resolved at call time to avoid import-time side effects.
_RETRYABLE_ERROR_NAMES = (
    "RateLimitError",
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
)

_EXTRACTION_PROMPT = """\
You are processing a single page from a Canadian bank financial document \
(investor presentation, supplementary financial package, or regulatory disclosure).

Extract ALL content from this page into this exact structure:

## [Page title or main topic — infer from content if not explicitly labelled]

### Text
[All visible text, faithfully transcribed. Use markdown heading levels (###, ####) \
for section headers and bullet points (-) for lists. Include every footnote, \
disclaimer, caption, axis label, and watermark.]

### Tables
[Reproduce every table as a markdown pipe table with a header row and --- separator.
Include all column headers and every data row with values. \
If no tables are present, omit this section entirely.]

### Charts and Visuals
[For every chart, graph, diagram, icon grid, or infographic on the page:]

**[Chart title, or "Untitled Chart" if no title is visible]**
- Type: [bar / line / stacked bar / waterfall / pie / scatter / area / other]
- Shows: [what metric or comparison is displayed, including time span and units]
- Data points: [every readable number, label, and percentage — from axes, bars, \
data labels, and legends]
- Key insight: [one sentence on what the visual communicates]

[If no charts or visuals are present, omit this section entirely.]

Rules:
- Transcribe every number visible on the page, including chart axis values and \
small data labels.
- Do not skip footnotes, asterisks, source attributions, or legal disclaimers.
- If the page is blank or purely decorative (no text or data), \
output only: ## Blank or Decorative Page
- Respond with ONLY the structured markdown above — no preamble, no closing remarks.
"""


def _retryable_errors() -> tuple[type[Exception], ...]:
    """Build the tuple of retryable OpenAI exception classes at call time."""
    try:
        import openai  # type: ignore[import]
    except ImportError:
        return ()
    return tuple(
        cls
        for name in _RETRYABLE_ERROR_NAMES
        if (cls := getattr(openai, name, None)) is not None
    )


def _render_all_pages(pdf_path: Path, dpi_scale: float) -> list[bytes]:
    """Open the PDF once and render every page to PNG bytes.

    Opening once (vs. once-per-page) avoids repeated structure-tree
    validation and is significantly faster for large documents.

    MuPDF writes structural errors (e.g. "no common ancestor in structure
    tree") directly to stderr at the C level — they are PDF/UA
    accessibility issues that do not affect visual rasterisation.
    ``mupdf_display_errors(False)`` suppresses that C-level output so it
    does not pollute logs; ``mupdf_warnings()`` clears the Python-level
    warning buffer.  Both are restored after rendering.
    """
    try:
        import fitz  # type: ignore[import]  # pymupdf
    except ImportError as exc:
        raise ImportError(
            "Vision PDF processing requires PyMuPDF: pip install pymupdf"
        ) from exc

    # Suppress MuPDF's direct stderr error output during rendering.
    fitz.TOOLS.mupdf_display_errors(False)
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        fitz.TOOLS.mupdf_display_errors(True)
        logger.error("Failed to open PDF '%s': %s", pdf_path.name, exc)
        return []

    # Clear any warnings accumulated during open (structure tree etc.)
    fitz.TOOLS.mupdf_warnings()

    images: list[bytes] = []
    try:
        mat = fitz.Matrix(dpi_scale, dpi_scale)
        for page_idx in range(len(doc)):
            try:
                pix = doc[page_idx].get_pixmap(matrix=mat, alpha=False)
                images.append(pix.tobytes("png"))
            except Exception as exc:
                logger.warning(
                    "Failed to render page %d of '%s' (%s) — inserting blank placeholder",
                    page_idx + 1,
                    pdf_path.name,
                    exc,
                )
                images.append(b"")  # blank placeholder; vision API step will skip
            finally:
                fitz.TOOLS.mupdf_warnings()  # clear per-page warning buffer
    finally:
        doc.close()
        fitz.TOOLS.mupdf_display_errors(True)

    return images


def _call_vision_api(
    img_bytes: bytes,
    *,
    config: DataSourcesConfig,
    model: str,
    max_tokens: int,
) -> str:
    """Send one rendered page image to the vision model; return extracted markdown."""
    client = build_openai_client(config)
    b64 = base64.b64encode(img_bytes).decode()
    retryable = _retryable_errors()

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": _EXTRACTION_PROMPT},
                        ],
                    }
                ],
                max_completion_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""

        except retryable as exc:
            if attempt == _MAX_RETRIES:
                logger.error("Vision API failed after %d attempts: %s", _MAX_RETRIES, exc)
                raise
            wait = _RETRY_DELAY_S * attempt
            logger.warning(
                "Vision API retry %d/%d after %.1fs: %s", attempt, _MAX_RETRIES, wait, exc,
                exc_info=True,
            )
            time.sleep(wait)

    raise RuntimeError("Exhausted retries")  # unreachable; satisfies type checker


def read_pdf_sheets_with_vision(
    path: Path,
    *,
    config: DataSourcesConfig,
    model: str = "gpt-4o-mini",
    max_tokens: int = 4000,
    max_workers: int = 4,
    dpi_scale: float = 2.0,
) -> list[RawSheet]:
    """Process every page of a PDF with an OpenAI vision model.

    Steps:
      1. Render all pages to PNG images locally (PyMuPDF, fast).
      2. Send each image to the vision API concurrently (up to max_workers).
      3. Return one ``RawSheet`` per page with rich markdown as ``raw_content``.

    Sheet names follow the ``Page_{N}`` convention (1-indexed) to match the
    naming used by the Excel reader and the stress-test ``answer_pages`` field.
    """
    try:
        import fitz  # type: ignore[import]  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Vision PDF processing requires PyMuPDF: pip install pymupdf"
        ) from exc

    # ── Step 1: Render all pages to PNG locally (single open) ────────
    logger.info("Rendering pages from '%s' to PNG (dpi=%.1fx)...", path.name, dpi_scale)
    page_images = _render_all_pages(path, dpi_scale=dpi_scale)
    num_pages = len(page_images)
    rendered = sum(1 for b in page_images if b)
    total_kb = sum(len(b) for b in page_images) // 1024

    logger.info(
        "Vision PDF reader: %d pages in '%s' (%d rendered, model=%s, workers=%d)",
        num_pages,
        path.name,
        rendered,
        model,
        max_workers,
    )
    logger.info("Rendered %d/%d pages (%d KB total). Submitting to vision API...", rendered, num_pages, total_kb)

    # ── Step 2: Extract pages concurrently via vision API ────────────
    results: dict[int, str] = {}

    def _process(idx: int) -> tuple[int, str]:
        img = page_images[idx]
        if not img:
            logger.warning("  Page %d/%d skipped (render failed)", idx + 1, num_pages)
            return idx, "## Page Render Failed\n\nThis page could not be rendered."
        content = _call_vision_api(
            img,
            config=config,
            model=model,
            max_tokens=max_tokens,
        )
        logger.info(
            "  Page %d/%d extracted (%d chars)", idx + 1, num_pages, len(content)
        )
        return idx, content

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process, i): i for i in range(num_pages)}
        for future in as_completed(futures):
            idx, content = future.result()
            results[idx] = content

    # ── Step 3: Assemble in page order ───────────────────────────────
    return [
        RawSheet(
            sheet_index=i,
            sheet_name=f"Page_{i + 1}",
            raw_content=results[i],
        )
        for i in range(num_pages)
    ]
