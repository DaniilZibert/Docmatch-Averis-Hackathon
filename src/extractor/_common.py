"""
OWNER: Person A.  Shared plumbing for every format-specific extractor.

Each extractor's only job is to turn its file into a list of `(label, value)` pairs.
Everything after that — resolving labels through field_aliases, telling a blank apart
from a value, parsing numbers, deciding "this is not an SI/BL at all" — happens here,
once, so the four extractors cannot drift apart.
"""

from __future__ import annotations

from ..models import (COMPARED_FIELDS, NUMERIC_FIELDS, DocType, ExtractedDocument,
                      ExtractedField, FieldSource)
from ..normalize import is_blank, parse_number
from . import field_aliases

# A document that yields fewer than this many recognisable labels is not a document
# we managed to read — it is a parse failure or a foreign file.
MIN_LABELS_FOR_READABLE = 3


def build_document(pairs: list[tuple[str, str]], *, email_id: str, doc_type: DocType,
                   source_path: str, text: str = "",
                   source: FieldSource = FieldSource.RULE,
                   confidence: float = 0.95) -> ExtractedDocument:
    """Assemble an ExtractedDocument from `(label, value)` pairs.

    Rules applied here:
      * first occurrence of a field wins (documents restate a field only in summaries);
      * a blank placeholder ("???", "TBA", "____MT", "") is recorded as a *present
        label with no value*, which `missing_fields` reports and the comparator turns
        into NEEDS_REVIEW / missing_value — never into a mismatch;
      * numeric fields go through normalize.parse_number so "6 x 40'HC" -> 6;
      * a document whose title or labels say it is an invoice / packing list /
        certificate is flagged `wrong_doc_type`;
      * a document with almost no recognisable labels is flagged `unreadable`.
    """
    fields: dict[str, ExtractedField] = {}
    seen_labels: list[str] = []

    for raw_label, raw_value in pairs:
        seen_labels.append(raw_label)
        field = field_aliases.match_field(raw_label)
        if field is None or field in fields:
            continue

        if is_blank(raw_value):
            fields[field] = ExtractedField(value=None, confidence=0.0, source=source,
                                           raw_label=str(raw_label).strip())
            continue

        value: str | int | float | None
        if field in NUMERIC_FIELDS:
            value = parse_number(raw_value)
        else:
            # xlsx/docx pack "NAME | ADDRESS" into one cell; compare the name.
            value = str(raw_value).split("|")[0].strip()
            value = value or None

        fields[field] = ExtractedField(value=value,
                                       confidence=confidence if value is not None else 0.0,
                                       source=source, raw_label=str(raw_label).strip())

    kind, _foreign_by_title = field_aliases.detect_document_kind(text) if text else (None, False)
    wrong_doc_type = field_aliases.is_foreign_document(seen_labels, text)

    recognised = len(fields)
    unreadable = recognised < MIN_LABELS_FOR_READABLE and not wrong_doc_type

    notes = None
    if wrong_doc_type:
        notes = f"document looks like a {kind or 'different document type'}, not an SI/BL"
    elif unreadable:
        notes = f"only {recognised} of {len(COMPARED_FIELDS)} fields recognised"
    elif kind:
        notes = f"read as {kind}"

    return ExtractedDocument(
        email_id=email_id, doc_type=doc_type, source_path=source_path,
        fields=fields, unreadable=unreadable, wrong_doc_type=wrong_doc_type,
        notes=notes,
    )


def unreadable_document(email_id: str, doc_type: DocType, source_path: str,
                        why: str) -> ExtractedDocument:
    """A file we could not read at all. An honest escalation, not a failure."""
    return ExtractedDocument(email_id=email_id, doc_type=doc_type,
                             source_path=source_path, unreadable=True, notes=why)


__all__ = ["MIN_LABELS_FOR_READABLE", "build_document", "unreadable_document"]
