"""
Smoke tests for the shared contract (src/models.py).

These must stay green for both of you — they are what guarantees that Person A's output
still fits Person B's input. Run: `pytest -q`

They deliberately do NOT test classifier/extractor/comparator behaviour; each of you
writes those tests in your own file (tests/test_extractor.py, tests/test_comparator.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.models import (COMPARED_FIELDS, Category, ComparisonResult, DecidedBy,
                        DocType, EmailRecord, EmailResult, ExtractedDocument,
                        ReviewReason, Status, build_submission)
from src.submission import REQUIRED_KEYS, validate_submission

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_inbox_loads():
    emails = EmailRecord.load_all(DATA_DIR)
    assert len(emails) == 520
    assert emails[0].email_id == "email_001"
    # `from` is a reserved word in Python, so it is exposed as `sender`
    assert all(isinstance(e.sender, str) for e in emails)


def test_attachment_lookup():
    email = next(e for e in EmailRecord.load_all(DATA_DIR) if e.email_id == "email_004")
    assert email.attachment_for(DocType.SI) == "attachments/email_004_SI.txt"
    assert email.attachment_for(DocType.BL) == "attachments/email_004_BL.txt"


def test_fake_document_is_fully_populated():
    doc = ExtractedDocument.fake("email_1", DocType.SI)
    assert doc.present_field_count == len(COMPARED_FIELDS)
    assert doc.missing_fields == []


def test_fake_document_accepts_overrides():
    bl = ExtractedDocument.fake("email_1", DocType.BL, container_count=4,
                                consignee="OTHER COMPANY LTD")
    assert bl.value_of("container_count") == 4
    assert bl.value_of("consignee") == "OTHER COMPANY LTD"


def test_missing_document_is_unreadable():
    doc = ExtractedDocument.missing("email_1", DocType.BL)
    assert doc.unreadable is True
    assert doc.source_path is None


def test_submission_entry_has_exactly_the_scorer_keys():
    result = EmailResult.from_comparison(
        Category.BL_COMPARISON,
        ComparisonResult(email_id="email_1", status=Status.MISMATCH, has_defect=True,
                         defect_fields=["consignee"]),
    )
    entry = result.to_submission_entry()
    assert set(entry) == REQUIRED_KEYS
    assert entry["status"] == "MISMATCH"
    assert entry["defect_fields"] == ["consignee"]
    assert entry["review_reason"] is None


def test_needs_review_entry_carries_its_reason():
    result = EmailResult.from_comparison(
        Category.BL_COMPARISON,
        ComparisonResult.needs_review("email_1", ReviewReason.MISSING_ATTACHMENT),
    )
    entry = result.to_submission_entry()
    assert entry["status"] == "NEEDS_REVIEW"
    assert entry["review_reason"] == "missing_attachment"
    assert entry["has_defect"] is False


def test_non_comparison_emails_are_clean():
    result = EmailResult.non_comparison("email_1", Category.SPAM, DecidedBy.RULE)
    entry = result.to_submission_entry()
    assert entry == {"category": "SPAM", "status": "OK", "review_reason": None,
                     "defect_fields": [], "has_defect": False}


def test_submission_shape_matches_organizers_sample():
    """Our generated shape must be identical to sample_submission.json, key for key."""
    sample = json.loads((DATA_DIR / "sample_submission.json").read_text())
    results = [EmailResult.non_comparison(eid, Category.GENERAL) for eid in sample]
    ours = build_submission(results)

    assert set(ours) == set(sample)
    assert set(next(iter(ours.values()))) == set(next(iter(sample.values())))
    assert validate_submission(ours, DATA_DIR) == []


def test_validate_submission_catches_missing_emails():
    problems = validate_submission({"email_001": {k: None for k in REQUIRED_KEYS}}, DATA_DIR)
    assert problems and "missing" in problems[0]
