"""
OWNER: Person A.  STUB — implement me first (192 of the 250 attachments are .txt).

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

So: `Label: Value` one per line, with an optional indented continuation line holding
the address. The label spelling differs between SI and BL — resolve it through
field_aliases.match_field(), never by hardcoding a string here.

Note `Total Containers: 6 x 40'HC` -> container_count is 6, and
`Gross Wt (kgs): 131,058 KG` -> gross_weight_kg is 131058. Use parse_number() from
src/normalize.py (Person B owns it) so both sides parse numbers the same way.
"""

from __future__ import annotations

from pathlib import Path

from ..models import DocType, ExtractedDocument


def extract_txt(path: Path, email_id: str, doc_type: DocType,
                source_path: str) -> ExtractedDocument:
    """TODO(Person A): parse `Label: Value` lines into ExtractedDocument.fields.

    Suggested steps:
      1. text = path.read_text(encoding="utf-8", errors="replace")
      2. for each line matching r"^([^:]{1,60}):\\s*(.*)$" -> (label, value)
      3. field = field_aliases.match_field(label); skip when None
      4. numeric fields -> normalize.parse_number(value)
      5. ExtractedField(value=..., confidence=0.95, source=FieldSource.RULE,
                        raw_label=label)
      6. if field_aliases.is_foreign_document(all_labels) -> wrong_doc_type=True
      7. if the file is empty / has no recognisable labels -> unreadable=True
    """
    return ExtractedDocument(
        email_id=email_id, doc_type=doc_type, source_path=source_path,
        unreadable=True, notes="txt_extractor not implemented yet",
    )
