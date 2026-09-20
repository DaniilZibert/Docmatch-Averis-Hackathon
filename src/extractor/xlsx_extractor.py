"""
OWNER: Person A.  Excel SI / BL — 22 attachments.

Layout: the label sits in one cell and the value in the cell to its right.

    ('Shipper/Exporter', 'APRIL FINE PAPER TRADING | ON BEHALF OF ...; SINGAPORE 068896')
    ('Load Port',        'SINGAPORE')
    ('Container Count',  "12 x 20'FCL")
    ('GROSS WEIGHT',     243588)                 <- a real int, not a string

Note the `NAME | ADDRESS` packing: _common.build_document keeps the part before the
pipe, because the matching Word BL writes the same value as `NAME | ADDR | ADDR` and
the two would otherwise never compare equal.
"""

from __future__ import annotations

from pathlib import Path

from ..models import DocType, ExtractedDocument
from ._common import build_document, unreadable_document


def extract_xlsx(path: Path, email_id: str, doc_type: DocType,
                 source_path: str) -> ExtractedDocument:
    import openpyxl

    # data_only=True matters: without it a formula cell yields "=A1", not its value.
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    pairs: list[tuple[str, str]] = []
    text_lines: list[str] = []

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if not cells:
                continue
            text_lines.append(" ".join(cells))
            if len(cells) >= 2:
                pairs.append((cells[0], cells[1]))
    workbook.close()

    if not pairs:
        return unreadable_document(email_id, doc_type, source_path,
                                   "workbook has no label/value rows")

    return build_document(pairs, email_id=email_id, doc_type=doc_type,
                          source_path=source_path, text="\n".join(text_lines))


__all__ = ["extract_xlsx"]
