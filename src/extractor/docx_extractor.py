"""
OWNER: Person A.  STUB — 8 attachments are .docx.

Test file: data/attachments/email_055_BL.docx

Fields can live either in paragraphs ("Shipper: ACME") or in a two-column table
(label cell | value cell). Read both: `doc.paragraphs` and `doc.tables`.
"""

from __future__ import annotations

from pathlib import Path

from ..models import DocType, ExtractedDocument


def extract_docx(path: Path, email_id: str, doc_type: DocType,
                 source_path: str) -> ExtractedDocument:
    """TODO(Person A): docx.Document(path); walk paragraphs and table rows."""
    return ExtractedDocument(
        email_id=email_id, doc_type=doc_type, source_path=source_path,
        unreadable=True, notes="docx_extractor not implemented yet",
    )
