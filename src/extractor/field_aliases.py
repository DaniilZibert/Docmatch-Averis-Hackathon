"""
OWNER: Person A.  Label -> canonical field mapping, and "is this even an SI/BL?".

The whole point of the use case: the SI and the BL call the same thing by different
names ("Port of Loading" vs "Load Port", "Consignee" vs "To the Order of").  This
module is the single place that knows those names.

The aliases below cover every label that appears in data/attachments — the plain-text
documents and the xlsx/docx/pdf ones, including the bilingual Word layout where the
label reads "Gross Weight毛重(KGS) (毛重 KGS)".  The Chinese-suffixed spellings are
resolved by the fuzzy pass, not by exact match, so rapidfuzz is a hard requirement
rather than a nice-to-have (see _FUZZY_AVAILABLE below).

TRAPS worth knowing about:
  * "NET WEIGHT" exists in the data and is NOT gross_weight_kg. Never alias it.
  * "To the Order of" is how a BL names the consignee.
  * The PDF container table has a "GROSS WEIGHT (KG)" *column header*; the number
    under it is one container's weight, not the shipment's. pdf_extractor skips the
    table body and reads the "TOTAL Gross Wt (kgs):" line instead.
  * Some attachments are not an SI/BL at all — a Commercial Invoice, a Packing List
    or a Certificate of Origin. Those are the `wrong_doc_type` cases. Detect them by
    the document TITLE first (see detect_document_kind); the label-set heuristic
    alone misses the Packing List, whose labels are Shipper / Consignee / Booking Ref.
"""

from __future__ import annotations

import logging
import re

from ..models import COMPARED_FIELDS

log = logging.getLogger(__name__)

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
    "net wt (kg)",
    "tare weight",
    "measurement",
    # the PDF container table's column headers, not field labels
    "container no.",
    "container no",
    "description",
})

# Labels that mark a document as something other than an SI or a draft BL.
# Kept for the invoice / certificate cases; the title check below is the primary
# signal because a Packing List carries none of these.
FOREIGN_DOCUMENT_LABELS: frozenset[str] = frozenset({
    "certificate no.",
    "issuing authority",
    "country of origin",
    "payment terms",
    "total amount",
    "invoice no.",
    "invoice date",
    "carton no.",
})

# Document titles, as they appear on the first line of an attachment.
# value -> the human-readable kind we show on the review screen.
SI_BL_TITLES: dict[str, str] = {
    "shipping instruction": "Shipping Instruction",
    "bill of lading": "Bill of Lading",
    "bill of lading (draft)": "draft Bill of Lading",
    "bill of lading instruction": "BL Instruction",
    "bl instruction": "BL Instruction",
}

FOREIGN_DOCUMENT_TITLES: dict[str, str] = {
    "commercial invoice": "Commercial Invoice",
    "packing list": "Packing List",
    "certificate of origin": "Certificate of Origin",
    "delivery order": "Delivery Order",
    "sea waybill": "Sea Waybill",
}

# The generator stamps an explicit disclaimer on the wrong-document attachments,
# e.g. "*** PACKING LIST ONLY - NO PORT OR VESSEL DETAILS ***". A real inbox will
# not be this polite, so it is a secondary signal only.
_NOT_SI_BL_MARKER = re.compile(r"NOT\s+(AN?\s+)?(SI|BL|SHIPPING INSTRUCTION|B/?L)\b",
                               re.IGNORECASE)

# Reverse index, built once: normalized label -> canonical field.
_LABEL_TO_FIELD: dict[str, str] = {
    alias: field for field, aliases in FIELD_ALIASES.items() for alias in aliases
}

try:
    from rapidfuzz import fuzz, process
    _FUZZY_AVAILABLE = True
except ImportError:  # pragma: no cover - environment problem, not a code path
    _FUZZY_AVAILABLE = False
    log.warning(
        "rapidfuzz is not installed: label matching falls back to exact spellings only. "
        "The bilingual Word/Excel labels ('Gross Weight毛重(KGS)', 'Shipper (发货人)') "
        "will NOT resolve and those documents will look empty. "
        "Run: pip install -r requirements.txt"
    )


def normalize_label(label: str) -> str:
    """Lowercase, collapse whitespace, drop a trailing colon — so 'Gross  Wt (kgs):'
    and 'gross wt (kgs)' land on the same key."""
    label = str(label).strip().rstrip(":").strip()
    label = re.sub(r"\s+", " ", label)
    return label.lower()


def match_field(label: str, *, fuzzy_threshold: int = 88) -> str | None:
    """Canonical field name for a document label, or None if it isn't one of ours.

    Exact alias match first; then a fuzzy pass (rapidfuzz) so unseen spellings like
    "Port Of Loading (P.O.L)" and the bilingual "Port of Loading (装货港)" still
    resolve.  Blocked labels always return None.
    """
    key = normalize_label(label)
    if not key or key in BLOCKED_LABELS:
        return None
    if key in _LABEL_TO_FIELD:
        return _LABEL_TO_FIELD[key]
    if not _FUZZY_AVAILABLE:
        return None

    # Guard the blocked labels through the fuzzy pass too: "Net Wt (kgs) (净重)"
    # is 90%+ similar to "gross wt (kgs)" on WRatio and must stay unmapped.
    for blocked in BLOCKED_LABELS:
        if key.startswith(blocked):
            return None

    best = process.extractOne(key, _LABEL_TO_FIELD.keys(), scorer=fuzz.WRatio,
                              score_cutoff=fuzzy_threshold)
    return _LABEL_TO_FIELD[best[0]] if best else None


# A long label drawn at x=20mm can physically overrun the value column at x=60mm.
# The PDF text layer then interleaves the two runs of glyphs, e.g.
#   "Notify Party/Intermediate Consignee" + "CERIEX"
#     -> "Notify Party/Intermediate ConsCigEnReIEeX"
# Neither extract_text() nor extract_words() nor an x-coordinate filter on chars can
# separate them, because the glyphs genuinely alternate in x. But the label is known,
# so its tail can be subtracted back out. Only attempted when the shared prefix is at
# least this long, so a chance prefix never triggers a bogus "recovery".
_MIN_COLLISION_PREFIX = 10


def _recover_collision(text: str, alias: str) -> tuple[str, str] | None:
    """Undo a label/value glyph collision for one candidate alias.

    Returns (label, value) when `text` is `alias` interleaved with a value, else None.
    """
    lowered = text.lower()
    shared = 0
    for i in range(min(len(alias), len(text))):
        if lowered[i] != alias[i]:
            break
        shared = i + 1
    if shared < _MIN_COLLISION_PREFIX or shared >= len(alias):
        return None

    tail = alias[shared:]            # the part of the label that got mixed in
    mangled = text[shared:]
    recovered: list[str] = []
    ti = 0
    for ch in mangled:
        if ti < len(tail) and ch.lower() == tail[ti]:
            ti += 1                  # this glyph belongs to the label
        else:
            recovered.append(ch)     # this glyph belongs to the value
    if ti != len(tail):              # the whole label tail must be accounted for
        return None
    value = "".join(recovered).strip()
    if not value:
        return None
    return text[:shared] + tail, value


def match_label_prefix(line: str) -> tuple[str, str] | None:
    """Split a colon-less "Label Value" line, as the PDF layout renders them.

        "Port of Discharge (POD) FREMANTLE, AUSTRALIA"
            -> ("Port of Discharge (POD)", "FREMANTLE, AUSTRALIA")
        "Notify Party/Intermediate ConsCigEnReIEeX"
            -> ("Notify Party/Intermediate Consignee", "CERIeX")

    Longest alias wins, so "Port of Loading (POL)" is preferred over "POL", and a
    collided long label is recovered before a shorter alias can mis-split it.
    Returns None when the line does not start with a known label.
    """
    text = line.strip()
    lowered = text.lower()
    for alias in _ALIASES_BY_LENGTH:
        if lowered.startswith(alias):
            if len(text) > len(alias) + 1:
                return text[:len(alias)], text[len(alias):].strip()
            continue
        recovered = _recover_collision(text, alias)
        if recovered:
            return recovered
    return None


_ALIASES_BY_LENGTH: tuple[str, ...] = tuple(
    sorted(_LABEL_TO_FIELD, key=len, reverse=True)
)


def detect_document_kind(text: str) -> tuple[str | None, bool]:
    """Read the document's own title.

    Returns `(human_readable_kind, is_foreign)`:

        "SHIPPING INSTRUCTION\\n===..."     -> ("Shipping Instruction", False)
        "PACKING LIST\\n===..."             -> ("Packing List", True)
        "no recognisable title"            -> (None, False)

    The title is the most reliable wrong_doc_type signal in this dataset: every
    substituted attachment (Commercial Invoice, Packing List, Certificate of
    Origin) announces itself on line 1, while its *labels* can look exactly like
    an SI's.
    """
    for raw_line in text.splitlines()[:6]:
        line = normalize_label(raw_line).strip("*= \t")
        if not line:
            continue
        for title, kind in FOREIGN_DOCUMENT_TITLES.items():
            if line.startswith(title):
                return kind, True
        for title, kind in SI_BL_TITLES.items():
            if line.startswith(title):
                return kind, False
    return None, False


def is_foreign_document(labels: list[str], text: str = "") -> bool:
    """True when this attachment is not an SI or a draft BL at all.

    Three independent signals, cheapest first:
      1. the document title (see detect_document_kind) — catches the Packing List,
         which the label heuristic alone cannot;
      2. an explicit "... NOT AN SI OR BL ..." disclaimer in the body;
      3. foreign labels (Certificate No., Total Amount, ...) on a document that
         carries fewer than three of our own fields.

    `text` is optional so the older call style `is_foreign_document(labels)` keeps
    working; pass the document text whenever you have it.
    """
    if text:
        _kind, foreign = detect_document_kind(text)
        if foreign:
            return True
        if _NOT_SI_BL_MARKER.search(text):
            return True

    found = {normalize_label(label) for label in labels}
    if found & FOREIGN_DOCUMENT_LABELS:
        # a real SI/BL also carries at least a couple of our own fields
        our_fields = {match_field(label) for label in labels} - {None}
        return len(our_fields) < 3
    return False


__all__ = ["FIELD_ALIASES", "BLOCKED_LABELS", "FOREIGN_DOCUMENT_LABELS",
           "SI_BL_TITLES", "FOREIGN_DOCUMENT_TITLES", "COMPARED_FIELDS",
           "normalize_label", "match_field", "match_label_prefix",
           "detect_document_kind", "is_foreign_document"]
