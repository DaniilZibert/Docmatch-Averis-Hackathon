"""
OWNER: Person A.  STUB — 22 attachments are .xlsx.

Test files: data/attachments/email_005_SI.xlsx, email_005_BL.xlsx, email_055_SI.xlsx

Expected layout: label in one cell, value in the cell to its right. Walk every sheet,
every row; for each non-empty cell treat it as a candidate label and the next non-empty
cell in that row as the value. Resolve labels through field_aliases.match_field().
"""

from __future__ import annotations

from pathlib import Path

from ..models import DocType, ExtractedDocument


def extract_xlsx(path: Path, email_id: str, doc_type: DocType,
                 source_path: str) -> ExtractedDocument:
    """TODO(Person A): openpyxl.load_workbook(path, data_only=True), scan cells.

    Same output contract as extract_txt. `data_only=True` matters — without it you get
    formula strings instead of values.
    """
    return ExtractedDocument(
        email_id=email_id, doc_type=doc_type, source_path=source_path,
        unreadable=True, notes="xlsx_extractor not implemented yet",
    )
