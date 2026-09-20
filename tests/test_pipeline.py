"""
End-to-end invariants over the whole inbox.

Deliberately NOT a scoring test: the answer key does not live in this repo. These
assert properties we can know from the data and the problem statement alone, so they
keep working if the organizers reseed the generator.

Use `python scripts/evaluate.py --ground-truth <path outside the repo>` (or
`--server http://localhost:8080`) for the actual score.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src import pipeline
from src.models import Category, EmailRecord, Status
from src.submission import validate_submission
from src.models import build_submission

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def results():
    return pipeline.run(DATA_DIR)


def test_every_email_gets_a_verdict(results):
    assert len(results) == 520
    assert len({r.email_id for r in results}) == 520


def test_the_submission_is_well_formed(results):
    assert validate_submission(build_submission(results), DATA_DIR) == []


def test_every_email_that_carries_an_attachment_is_routed_for_comparison(results):
    """An attachment is the one unambiguous signal in the inbox. If this ever fails,
    defects are being lost before the comparison step — the 50% axis."""
    by_id = {r.email_id: r for r in results}
    for email in EmailRecord.load_all(DATA_DIR):
        if email.attachments:
            assert by_id[email.email_id].category is Category.BL_COMPARISON, email.email_id


def test_escalation_stays_within_the_plausible_band(results):
    """20 of the 520 emails genuinely cannot be decided. A pipeline that escalates far
    more than that is too cautious and is manufacturing false alarms; one that
    escalates none is guessing on documents it could not read."""
    escalated = [r for r in results if r.status is Status.NEEDS_REVIEW]
    assert 10 <= len(escalated) <= 40, f"escalated {len(escalated)}"
    assert all(r.review_reason is not None for r in escalated)


def test_all_four_review_reasons_are_exercised(results):
    reasons = Counter(r.review_reason.value for r in results if r.review_reason)
    assert set(reasons) == {"wrong_doc_type", "missing_attachment", "unreadable",
                            "missing_value"}


def test_non_comparison_emails_never_carry_a_defect(results):
    for result in results:
        if result.category is not Category.BL_COMPARISON:
            assert result.has_defect is False
            assert result.defect_fields == []
            assert result.status is Status.OK


def test_defect_flags_always_agree(results):
    for result in results:
        assert result.has_defect == bool(result.defect_fields), result.email_id
        if result.status is Status.NEEDS_REVIEW:
            assert result.has_defect is False


def test_nothing_crashed(results):
    failed = [r for r in results if r.error]
    assert not failed, f"{len(failed)} emails errored, e.g. {failed[:3]}"


def test_the_run_is_fast_enough_to_demo(results):
    """520 emails, no LLM calls on the happy path. If this creeps into minutes the
    demo stops being a demo."""
    import time
    started = time.time()
    pipeline.run(DATA_DIR, limit=100)
    assert time.time() - started < 15


def test_the_worked_example_from_the_brief(results):
    """email_004: the SI names EAST BRIGHT FZ-LLC as consignee and notify party, the
    draft BL says UAB NOVAKOPA, everything else agrees."""
    result = next(r for r in results if r.email_id == "email_004")
    assert result.category is Category.BL_COMPARISON
    assert result.status is Status.MISMATCH
    assert result.defect_fields == ["consignee", "notify_party"]
    rows = {row.field: row for row in result.comparisons}
    assert rows["consignee"].si_value == "EAST BRIGHT FZ-LLC"
    assert rows["consignee"].bl_value == "UAB NOVAKOPA"
    assert rows["container_count"].match is True
