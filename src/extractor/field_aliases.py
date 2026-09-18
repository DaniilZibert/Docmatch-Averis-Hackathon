"""
OWNER: Person A.  Label -> canonical field mapping.

The whole point of the use case: the SI and the BL call the same thing by different
names ("Port of Loading" vs "Load Port", "Consignee" vs "To the Order of").  This
module is the single place that knows those names.

The aliases below were harvested from the real labels in data/attachments/*.txt
(`grep -hoE "^[A-Za-z][^:]{1,45}:" *.txt | sort | uniq -c`), so they cover the text
documents.  The xlsx/docx/pdf attachments may introduce more — add them here, not in
the individual extractors.

TRAPS worth knowing about:
  * "NET WEIGHT" exists in the data and is NOT gross_weight_kg. Never alias it.
  * "To the Order of" is how a BL names the consignee.
  * Some attachments are a Certificate of Origin, not an SI/BL at all — they carry
    "Certificate No.", "Issuing Authority", "Country of Origin". Those are the
    `wrong_doc_type` cases; see is_foreign_document().
"""

from __future__ import annotations

import re

from ..models import COMPARED_FIELDS

# canonical field -> every label seen (or plausibly used) for it.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "shipper": (
        "shipper",
        "shipper (principal or seller)",
        "shipper/exporter",
        "shipper / exporter",
        "exporter",
        "seller",
    ),
    "consignee": (
        "consignee",
        "consignee (non-negotiable)",
        "consignee (non negotiable)",
        "to the order of",
        "to order of",
        "consigned to",
    ),
    "notify_party": (
        "notify",
        "notify party",
        "notify party/intermediate consignee",
        "notify party / intermediate consignee",
        "intermediate consignee",
        "notify address",
    ),
    "port_of_loading": (
        "port of loading",
        "port of loading (pol)",
        "pol",
        "load port",
        "loading port",
        "port of receipt",
    ),
    "port_of_discharge": (
        "port of discharge",
        "port of discharge (pod)",
        "pod",
        "discharge port",
        "discharging port",
        "port of delivery",
    ),
    "container_count": (
        "no. of containers",
        "no of containers",
        "number of containers",
        "no. of containers or packages",
        "total containers",
        "container count",
        "containers",
    ),
    "gross_weight_kg": (
        "gross wt (kgs)",
        "gross wt",
        "gross weight",
        "gross weight (kg)",
        "gross weight (kgs)",
        "gross wt. (kgs)",
        "total gross weight",
    ),
}

# Labels that look like one of our fields but are NOT — never map these.
BLOCKED_LABELS: frozenset[str] = frozenset({
    "net weight",
    "net wt",
    "net wt (kgs)",
    "tare weight",
    "measurement",
})

# Labels that mark a document as something other than an SI or a draft BL.
FOREIGN_DOCUMENT_LABELS: frozenset[str] = frozenset({
    "certificate no.",
    "issuing authority",
    "country of origin",
    "payment terms",
    "total amount",
    "invoice no.",
})

# Reverse index, built once: normalized label -> canonical field.
_LABEL_TO_FIELD: dict[str, str] = {
    alias: field for field, aliases in FIELD_ALIASES.items() for alias in aliases
}


def normalize_label(label: str) -> str:
    """Lowercase, collapse whitespace, drop a trailing colon — so 'Gross  Wt (kgs):'
    and 'gross wt (kgs)' land on the same key."""
    label = label.strip().rstrip(":").strip()
    label = re.sub(r"\s+", " ", label)
    return label.lower()


def match_field(label: str, *, fuzzy_threshold: int = 88) -> str | None:
    """Canonical field name for a document label, or None if it isn't one of ours.

    Exact alias match first; then a fuzzy pass (rapidfuzz) so unseen spellings like
    "Port Of Loading (P.O.L)" still resolve.  Blocked labels always return None.
    """
    key = normalize_label(label)
    if not key or key in BLOCKED_LABELS:
        return None
    if key in _LABEL_TO_FIELD:
        return _LABEL_TO_FIELD[key]

    try:
        from rapidfuzz import process, fuzz
    except ImportError:  # rapidfuzz not installed yet — exact matching only
        return None

    best = process.extractOne(key, _LABEL_TO_FIELD.keys(), scorer=fuzz.WRatio,
                              score_cutoff=fuzzy_threshold)
    return _LABEL_TO_FIELD[best[0]] if best else None


def is_foreign_document(labels: list[str]) -> bool:
    """True when the labels look like a different document type entirely (certificate
    of origin, invoice...). Person A: use this to raise `wrong_doc_type`."""
    found = {normalize_label(label) for label in labels}
    if found & FOREIGN_DOCUMENT_LABELS:
        # a real SI/BL also carries at least a couple of our own fields
        our_fields = {match_field(label) for label in labels} - {None}
        return len(our_fields) < 3
    return False


__all__ = ["FIELD_ALIASES", "BLOCKED_LABELS", "FOREIGN_DOCUMENT_LABELS",
           "COMPARED_FIELDS", "normalize_label", "match_field", "is_foreign_document"]
