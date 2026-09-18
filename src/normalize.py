"""
OWNER: Person B.  STUB — value normalisation, shared by the comparator and (for numbers)
by Person A's extractors.

This is where "the same information looks different" gets resolved at the VALUE level
(field_aliases.py does it at the LABEL level).

Judgement call that matters: normalise conservatively. In this dataset a planted defect
is a genuinely different value (a different consignee company, a different port), not a
typo — so aggressive fuzzy matching would "forgive" real defects and cost us the 50%
end-to-end axis. Strip case, punctuation and whitespace; do NOT accept two different
company names as equal because they share a word.
"""

from __future__ import annotations


def normalize_text(value: str | None) -> str:
    """TODO(Person B): uppercase, collapse whitespace, strip punctuation and trailing
    legal-suffix noise, so "EAST BRIGHT FZ-LLC" == "East Bright  FZ LLC"."""
    raise NotImplementedError("normalize.normalize_text")


def parse_number(value: str | int | float | None) -> int | float | None:
    """TODO(Person B): "131,058 KG" -> 131058 ; "6 x 40'HC" -> 6 ; "22000" -> 22000.

    Person A's extractors call this too, so it lands here rather than in the extractors.
    Return None when there is no number to read — never 0 as a stand-in for "absent".
    """
    raise NotImplementedError("normalize.parse_number")


def values_match(field_name: str, si_value, bl_value) -> bool:
    """TODO(Person B): numeric fields compare as numbers, everything else as normalised
    text. Both sides absent is NOT a match — that is a missing_value case for the caller."""
    raise NotImplementedError("normalize.values_match")


__all__ = ["normalize_text", "parse_number", "values_match"]
