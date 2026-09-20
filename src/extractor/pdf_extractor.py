"""
OWNER: Person A.  PDF SI / BL — 28 attachments, the hardest format.

Three kinds of PDF in this dataset, and each needs a different answer:

  1. text-layer PDFs (20 files) — pdfplumber returns the text, but it is NOT the
     `Label: Value` shape the .txt files use. The renderer draws each label at x=20mm
     and its value at x=60mm, so the text layer comes back as colon-less lines:

         Shipper APRIL FINE PAPER TRADING
         POL BUATAN, INDONESIA
         Port of Discharge (POD) FREMANTLE, AUSTRALIA

     Those are split with field_aliases.match_label_prefix (longest alias wins).

  2. scanned / image-only PDFs (6 files) — extract_text() returns nothing. Render the
     page and hand it to Claude vision (llm_extract.extract_from_image). If that is
     unavailable or comes back empty, the document is honestly `unreadable`.

  3. corrupt PDFs (2 files) — zero bytes, or a valid header followed by garbage with
     no xref. pdfplumber raises; that is `unreadable` too, not a crash.

Two traps live in the text-layer PDFs:

  * THE CONTAINER TABLE. It has a "GROSS WEIGHT (KG)" column header, and the number
    under it is ONE container's weight (21,887), not the shipment's (131,322). Reading
    it would put a wrong weight into every PDF comparison. The table body is skipped
    and the weight is taken from the "TOTAL Gross Wt (kgs):" summary line instead.
    This is the same class of trap as "NET WEIGHT" — a plausible label on the wrong
    number.

  * GLYPH COLLISION. "Notify Party/Intermediate Consignee" is long enough to overrun
    the value column, so the text layer interleaves label and value:
    "Notify Party/Intermediate ConsCigEnReIEeX". Neither extract_words() nor an
    x-coordinate filter on chars separates them (the glyphs genuinely alternate in x);
    field_aliases subtracts the known label tail back out. Affects 3 files.

A PDF that yields neither text nor a usable vision result is `unreadable=True` — a
legitimate NEEDS_REVIEW case, not a failure. Never guess field values.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..models import DocType, ExtractedDocument, FieldSource
from ._common import build_document, unreadable_document
from . import field_aliases

log = logging.getLogger(__name__)

# Below this many characters of extracted text, treat the page as scanned.
TEXT_LAYER_MIN_CHARS = 40

_WARNED_NO_PYMUPDF = False

# The container table. Its header carries a "GROSS WEIGHT (KG)" column label and each
# body row carries ONE container's weight, so both must be skipped. Rows are matched by
# the container-number format (4 letters + 7 digits, e.g. PURJ4736471) rather than by a
# start/end state machine: the table's own summary line is labelled with a rotating
# alias ("Container Count:", "No. of Containers:", "Total Containers:"), so any
# end-of-table marker keyed on one spelling silently swallows the others.
_TABLE_HEADER = re.compile(r"^CONTAINER\s+NO\.", re.IGNORECASE)
_CONTAINER_ROW = re.compile(r"^[A-Z]{4}\d{7}\b")
_LABEL_LINE = re.compile(r"^(.{1,60}?):\s*(.*)$")
# "TOTAL Gross Wt (kgs): 131,322 KG" -> the label is "Gross Wt (kgs)".
_TOTAL_PREFIX = re.compile(r"^TOTAL\s+", re.IGNORECASE)


def parse_pdf_text(text: str) -> list[tuple[str, str]]:
    """`(label, value)` pairs from a rendered-PDF text layer."""
    pairs: list[tuple[str, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _TABLE_HEADER.match(line) or _CONTAINER_ROW.match(line):
            continue

        match = _LABEL_LINE.match(line)
        if match:
            pairs.append((_TOTAL_PREFIX.sub("", match.group(1)), match.group(2)))
            continue

        split = field_aliases.match_label_prefix(line)
        if split:
            pairs.append(split)

    return pairs


def _page_images(path: Path, max_pages: int = 2) -> list[bytes]:
    """Render pages to PNG for the vision fallback. Empty list if pymupdf is absent."""
    global _WARNED_NO_PYMUPDF
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf          # older releases only ship the fitz alias
        except ImportError:
            pymupdf = None
    if pymupdf is None:
        if not _WARNED_NO_PYMUPDF:
            _WARNED_NO_PYMUPDF = True
            log.warning("pymupdf is not installed: scanned PDFs cannot be rendered for "
                        "vision and will escalate as unreadable. "
                        "pip install -r requirements.txt")
        return []
    try:
        with pymupdf.open(path) as document:
            return [page.get_pixmap(dpi=200).tobytes("png")
                    for page in list(document)[:max_pages]]
    except Exception as exc:
        log.debug("could not rasterise %s: %s", path, exc)
        return []


def extract_pdf(path: Path, email_id: str, doc_type: DocType,
                source_path: str) -> ExtractedDocument:
    if path.stat().st_size == 0:
        return unreadable_document(email_id, doc_type, source_path, "file is empty (0 bytes)")

    import pdfplumber

    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        return unreadable_document(email_id, doc_type, source_path,
                                   f"PDF will not open: {type(exc).__name__}")

    if len(text.strip()) >= TEXT_LAYER_MIN_CHARS:
        # llm_fallback stays on: a PDF whose text layer reads fine but whose LAYOUT we
        # have no aliases for is cheaper and more accurate to fix with a text call than
        # with vision. Vision below is for pages that have no text at all.
        document = build_document(parse_pdf_text(text), email_id=email_id,
                                  doc_type=doc_type, source_path=source_path, text=text)
        if not document.unreadable:
            return document
        # a text layer we could not make sense of — fall through to vision

    # No usable text layer: this is a scan. Advanced challenge "Scanned documents".
    from .llm_extract import extract_from_image

    for png in _page_images(path):
        document = extract_from_image(png, email_id, doc_type, source_path)
        if document is not None and document.present_field_count >= 3:
            # vision read it, but a scan is not sign-off evidence: see comparator step 5
            document.needs_confirmation = True
            document.notes = "read from a scanned page by Claude vision — needs confirmation"
            return document

    return unreadable_document(email_id, doc_type, source_path,
                               "image-only PDF and no vision result — needs a human")


__all__ = ["TEXT_LAYER_MIN_CHARS", "parse_pdf_text", "extract_pdf"]
