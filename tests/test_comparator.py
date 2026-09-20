"""
The decision order in comparator.compare — the reliability axis of the score.

Of the 220 comparison emails exactly 20 genuinely cannot be decided. Each of the four
reasons has its own trigger, and the order they are checked in decides which reason a
human is shown.
"""

from __future__ import annotations

from src.comparator import compare
from src.models import DocType, ExtractedDocument, ReviewReason, Status


def si(**overrides) -> ExtractedDocument:
    return ExtractedDocument.fake("email_1", DocType.SI, **overrides)


def bl(**overrides) -> ExtractedDocument:
    return ExtractedDocument.fake("email_1", DocType.BL, **overrides)


def test_identical_documents_are_ok():
    result = compare(si(), bl())
    assert result.status is Status.OK
    assert result.has_defect is False
    assert result.defect_fields == []


def test_one_differing_field_is_a_mismatch():
    result = compare(si(container_count=3), bl(container_count=4))
    assert result.status is Status.MISMATCH
    assert result.has_defect is True
    assert result.defect_fields == ["container_count"]


def test_two_differing_fields_are_both_reported():
    """End-to-end scoring needs the EXACT set — 26 of the 46 defect emails have two
    fields, and flagging one of the two scores zero."""
    result = compare(si(consignee="A LTD", notify_party="A LTD"),
                     bl(consignee="B LTD", notify_party="B LTD"))
    assert result.defect_fields == ["consignee", "notify_party"]


def test_all_seven_rows_are_always_present():
    """The report shows SI and BL side by side whatever the verdict."""
    for result in (compare(si(), bl()),
                   compare(si(container_count=3), bl(container_count=4))):
        assert len(result.comparisons) == 7
        assert [row.field for row in result.comparisons] == [
            "shipper", "consignee", "notify_party", "port_of_loading",
            "port_of_discharge", "container_count", "gross_weight_kg"]


def test_a_blank_field_escalates_instead_of_flagging():
    """The single most expensive confusion: a blank is uncertainty, not a defect."""
    document = si()
    document.fields["port_of_loading"].value = None
    result = compare(document, bl())
    assert result.status is Status.NEEDS_REVIEW
    assert result.review_reason is ReviewReason.MISSING_VALUE
    assert result.has_defect is False
    assert result.defect_fields == []


def test_missing_attachment_beats_every_other_reason():
    missing = ExtractedDocument.missing("email_1", DocType.BL)
    assert compare(si(), missing).review_reason is ReviewReason.MISSING_ATTACHMENT


def test_unreadable_beats_missing_value():
    """An empty file is missing all seven fields; 'unreadable' is the useful reason."""
    broken = ExtractedDocument(email_id="email_1", doc_type=DocType.BL,
                               source_path="attachments/email_1_BL.pdf", unreadable=True)
    assert compare(si(), broken).review_reason is ReviewReason.UNREADABLE


def test_wrong_doc_type_beats_missing_value():
    """An invoice sent instead of a BL is missing six fields, but 'we were sent the
    wrong document' is what the human needs to hear."""
    invoice = ExtractedDocument(email_id="email_1", doc_type=DocType.BL,
                                source_path="attachments/email_1_BL.txt",
                                wrong_doc_type=True)
    assert compare(si(), invoice).review_reason is ReviewReason.WRONG_DOC_TYPE


def test_a_scan_read_by_vision_still_asks_a_human():
    """We read it, and we show what we read — but an OCR'd image is not enough to sign
    off a bill of lading."""
    scanned = si()
    scanned.needs_confirmation = True
    result = compare(scanned, bl())
    assert result.status is Status.NEEDS_REVIEW
    assert result.review_reason is ReviewReason.UNREADABLE
    assert all(row.si_value is not None for row in result.comparisons)  # evidence shown
