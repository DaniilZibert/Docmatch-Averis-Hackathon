"""
OWNER: Person A.  STUB — 28 attachments are .pdf. The hardest format, do it last.

Test files: data/attachments/email_059_SI.pdf, email_059_BL.pdf

Two kinds of PDF in this dataset:
  1. text-layer PDFs  -> pdfplumber gives you the text, parse it like a .txt
  2. scanned/image-only PDFs -> page.extract_text() comes back empty or near-empty.
     Render the page to PNG (pymupdf: page.get_pixmap(dpi=200).tobytes("png")) and
     hand it to llm_extract.extract_from_image() — that is the `vision` source and
     the "Scanned documents" advanced challenge in the use case.

A PDF that yields neither text nor a usable vision result is `unreadable=True` — that
is a legitimate NEEDS_REVIEW case, not a failure. Do not guess field values.
"""

from __future__ import annotations

from pathlib import Path

from ..models import DocType, ExtractedDocument

# Below this many characters of extracted text, treat the page as scanned.
TEXT_LAYER_MIN_CHARS = 40


def extract_pdf(path: Path, email_id: str, doc_type: DocType,
                source_path: str) -> ExtractedDocument:
    """TODO(Person A): text layer first, vision fallback second."""
    return ExtractedDocument(
        email_id=email_id, doc_type=doc_type, source_path=source_path,
        unreadable=True, notes="pdf_extractor not implemented yet",
    )
