"""
OWNER: Person B.  Value normalisation, shared by the comparator and by Person A's
extractors.

This is where "the same information looks different" gets resolved at the VALUE level
(field_aliases.py does it at the LABEL level).

Three jobs:

  1. `is_blank()`  — tell a *missing* value apart from a *different* one. The dataset
     writes absent values as "???", "_______", "TBA", "TBC", "N/A", "____MT" or an
     empty string. A blank is uncertainty (-> NEEDS_REVIEW / missing_value), never a
     discrepancy. Getting this wrong turns an honest escalation into a false alarm.

  2. `parse_number()` — "131,058 KG" -> 131058 ; "6 x 40'HC" -> 6 ; 243588 -> 243588.

  3. `normalize_text()` / `values_match()` — case, whitespace, punctuation and the
     trailing UN/LOCODE in "NANTONG, CHINA (CNNTG)".

Judgement call that matters: normalise CONSERVATIVELY. In this dataset a planted defect
is a genuinely different value (a different consignee company, a different port), not a
typo — so aggressive fuzzy matching would "forgive" real defects and cost us the 50%
end-to-end axis. We deliberately do NOT strip legal suffixes (LLC / LTD / FZE / PTE):
two company names that differ only by suffix are two different companies.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 1. blank detection
# ---------------------------------------------------------------------------

# Exactly the placeholders the documents use for "this was not filled in".
# Source: the blank tokens observed across data/attachments (???, _______, TBA,
# TBC, N/A, ____MT, and a plain empty value).
_BLANK_RE = re.compile(
    r"""^(
          |               # empty
          [?]+            # ???
          |[_\-–—.]+   # _______  ----  ---  ...
          |[_\-]+\s*(?:MT|MTS|KG|KGS)   # ____MT
          |N\s*/?\s*A     # N/A  NA  N / A
          |TBA|TBC|TBD    # to be advised / confirmed / determined
          |NIL|NONE|UNKNOWN
          |X+             # XXXX
        )$""",
    re.IGNORECASE | re.VERBOSE,
)


def is_blank(value: object) -> bool:
    """True when the document left this value unfilled.

    A blank is NOT a mismatch — the comparator escalates it as `missing_value`.

        is_blank("???")     -> True
        is_blank("____MT")  -> True
        is_blank("TBA")     -> True
        is_blank(0)         -> False   (a real number, however odd)
        is_blank("SINGAPORE") -> False
    """
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return False
    return bool(_BLANK_RE.match(str(value).strip()))


# ---------------------------------------------------------------------------
# 2. numbers
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d[\d,\s]*(?:\.\d+)?")


def parse_number(value: str | int | float | None) -> int | float | None:
    """First number in the value, thousands separators removed.

        "131,058 KG"  -> 131058
        "6 x 40'HC"   -> 6          (the count, not the container size)
        "243,588"     -> 243588
        243588        -> 243588
        "???"         -> None

    Returns None when there is no number to read — never 0 as a stand-in for
    "absent", because 0 compares equal to 0 and would hide a missing value.
    """
    if value is None:
        return None
    if isinstance(value, bool):          # bool is an int subclass; not a quantity
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if is_blank(text):
        return None

    match = _NUMBER_RE.search(text)
    if not match:
        return None
    cleaned = re.sub(r"[,\s]", "", match.group())
    if not cleaned or cleaned == ".":
        return None
    number = float(cleaned)
    return int(number) if number.is_integer() else number


# ---------------------------------------------------------------------------
# 3. text
# ---------------------------------------------------------------------------

# "NANTONG, CHINA (CNNTG)" -> the UN/LOCODE is decoration, not part of the name.
_LOCODE_RE = re.compile(r"\(\s*[A-Z]{5}\s*\)")


def normalize_text(value: str | int | float | None) -> str | None:
    """Uppercase, drop the trailing LOCODE, collapse punctuation and whitespace.

        "  east bright  fz-llc " -> "EAST BRIGHT FZ LLC"
        "NANTONG, CHINA (CNNTG)" -> "NANTONG CHINA"

    Returns None for blanks, so callers can tell "absent" from "empty string".
    """
    if value is None:
        return None
    text = str(value).strip()
    if is_blank(text):
        return None

    # xlsx/docx pack "NAME | ADDRESS" into one cell; the name is what we compare.
    text = text.split("|")[0]
    text = _LOCODE_RE.sub(" ", text.upper())
    text = re.sub(r"[^A-Z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text) or None


def values_match(field_name: str, si_value, bl_value) -> bool:
    """Do the SI and the BL agree on this field?

    Numeric fields compare as numbers, everything else as normalised text. Both
    sides absent is NOT a match — that is a missing_value case, and the caller
    (comparator.compare) checks for it before asking this question.
    """
    from .models import NUMERIC_FIELDS

    if field_name in NUMERIC_FIELDS:
        si_number = parse_number(si_value)
        bl_number = parse_number(bl_value)
        if si_number is None or bl_number is None:
            return False
        return float(si_number) == float(bl_number)

    si_text = normalize_text(si_value)
    bl_text = normalize_text(bl_value)
    if si_text is None or bl_text is None:
        return False
    return si_text == bl_text


__all__ = ["is_blank", "normalize_text", "parse_number", "values_match"]
