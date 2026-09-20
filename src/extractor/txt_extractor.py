"""
OWNER: Person A.  Plain-text SI / BL — 192 of the 250 attachments.

Shape of a real .txt attachment (data/attachments/email_004_SI.txt):

    SHIPPING INSTRUCTION
    ========================================

    Shipper: APRIL FAR EAST (M) SDN BHD
      TOWER 2, AVENUE 5, LEVEL 6; BANGSAR SOUTH CITY...
    Consignee (Non-Negotiable): EAST BRIGHT FZ-LLC
      RAKEZ AMENITY CENTER; AL HAMRA INDUSTRIAL ZONE, RAK, UAE
    Notify: EAST BRIGHT FZ-LLC
    Port of Loading (POL): NANTONG, CHINA (CNNTG)
    POD: KARACHI, PAKISTAN (PKKHI)
    Total Containers: 6 x 40'HC
    Gross Wt (kgs): 131,058 KG

`Label: Value` one per line, plus an INDENTED continuation line holding the address.
Those continuation lines are skipped: the address belongs to whoever the name says it
belongs to, and the generator copies the address verbatim even when it mutates the
name — so comparing addresses would mask a real consignee defect.

The label spelling differs between SI and BL; it is always resolved through
field_aliases.match_field(), never by hardcoding a string here.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import DocType, ExtractedDocument
from ._common import build_document, unreadable_document

# "Label: value" — the label is short and colon-free by construction.
LABEL_LINE = re.compile(r"^([^:]{1,60}):\s*(.*)$")


def parse_label_lines(text: str) -> list[tuple[str, str]]:
    """Every `Label: Value` pair in a block of text. Indented continuation lines
    (addresses) are ignored. Shared with the PDF and DOCX extractors."""
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip() or line[:1].isspace():
            continue                       # blank line, or an indented address
        match = LABEL_LINE.match(line)
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def extract_txt(path: Path, email_id: str, doc_type: DocType,
                source_path: str) -> ExtractedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return unreadable_document(email_id, doc_type, source_path, "file is empty")

    return build_document(parse_label_lines(text), email_id=email_id, doc_type=doc_type,
                          source_path=source_path, text=text)


__all__ = ["LABEL_LINE", "parse_label_lines", "extract_txt"]
