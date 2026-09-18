"""
OWNER: Person B.  STUB — SI x BL -> ComparisonResult.

You do NOT need Person A's extractors to build this. Test against hand-made documents:

    from src.models import ExtractedDocument, DocType
    si = ExtractedDocument.fake("email_1", DocType.SI, container_count=3)
    bl = ExtractedDocument.fake("email_1", DocType.BL, container_count=4)
    compare(si, bl)   # -> MISMATCH, defect_fields == ["container_count"]

Decision order (get this right — it is the reliability axis of the score):

    1. SI or BL attachment absent          -> NEEDS_REVIEW / missing_attachment
    2. either document unreadable          -> NEEDS_REVIEW / unreadable
    3. either document is the wrong kind    -> NEEDS_REVIEW / wrong_doc_type
    4. a compared field absent on either side -> NEEDS_REVIEW / missing_value
    5. otherwise compare all 7             -> OK  or  MISMATCH + defect_fields

Rule 4 is the subtle one: escalating is correct, but escalating too eagerly destroys
defect recall (20 of 220 comparison emails are genuine NEEDS_REVIEW cases — if you
return far more than that, the logic is too cautious).

Always fill `comparisons` with all 7 rows, matching or not — the review screen shows SI
and BL side by side, and the use case asks for exactly that report.
"""

from __future__ import annotations

from .models import ComparisonResult, ExtractedDocument, ReviewReason


def compare(si: ExtractedDocument, bl: ExtractedDocument) -> ComparisonResult:
    """TODO(Person B): implement the decision order above.

    Until implemented, everything escalates — honest placeholder that keeps the
    pipeline runnable and produces a valid submission.json.
    """
    return ComparisonResult.needs_review(
        email_id=si.email_id or bl.email_id,
        reason=ReviewReason.UNREADABLE,
    )


__all__ = ["compare"]
