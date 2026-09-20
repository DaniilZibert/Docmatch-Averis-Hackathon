"""The discrepancy report — the deliverable the problem statement describes."""

from __future__ import annotations

from src.comparator import compare
from src.models import Category, ComparisonResult, DocType, EmailResult, ExtractedDocument
from src.report import NO_MISMATCH, render_email, render_report, verdict_line


def result_for(si_kwargs=None, bl_kwargs=None) -> EmailResult:
    si = ExtractedDocument.fake("email_1", DocType.SI, **(si_kwargs or {}))
    bl = ExtractedDocument.fake("email_1", DocType.BL, **(bl_kwargs or {}))
    return EmailResult.from_comparison(Category.BL_COMPARISON, compare(si, bl))


def test_a_clean_check_says_no_mismatch_detected():
    """The brief asks for this sentence, in these words."""
    assert verdict_line(result_for()) == NO_MISMATCH


def test_a_mismatch_names_exactly_what_needs_attention():
    line = verdict_line(result_for({"container_count": 3}, {"container_count": 4}))
    assert "container_count" in line
    assert "1 field" in line


def test_the_rendered_case_shows_si_and_bl_side_by_side():
    """'flag only the container count and show SI: 3 / BL: 4'."""
    text = render_email(result_for({"container_count": 3}, {"container_count": 4}))
    assert "container_count" in text
    assert "3" in text and "4" in text
    assert "shipper" in text          # all seven rows, not only the failing one


def test_the_report_holds_the_summary_and_the_cases():
    results = [result_for(), result_for({"container_count": 3}, {"container_count": 4})]
    markdown = render_report(results)
    assert "2 emails processed" in markdown
    assert "## Discrepancies" in markdown
    assert "## Sent for human review" in markdown
    assert "container_count" in markdown


def test_an_escalation_explains_itself_to_a_human():
    document = ExtractedDocument.fake("email_1", DocType.SI)
    document.fields["port_of_loading"].value = None
    result = EmailResult.from_comparison(
        Category.BL_COMPARISON,
        compare(document, ExtractedDocument.fake("email_1", DocType.BL)))
    line = verdict_line(result)
    assert "human review" in line
    assert "missing_value" in line
    assert "blank" in line
