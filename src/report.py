"""
OWNER: Person B.  The discrepancy report — the actual deliverable of the use case.

The problem statement asks for exactly this, in these words:

    "The report should make it easy to see which email was checked, whether a mismatch
     was found, and exactly what needs attention. If all seven fields match, report
     'No mismatch detected.'"
    "Compare - Check the values and surface any mismatched fields, showing the SI and
     BL values side by side."
    "Ask for help - escalate to a person with the relevant context."

So every rendered case carries three things: the verdict, the seven rows side by side,
and — when we escalated — the reason plus the evidence a human needs to resolve it.

    render_email(result)              -> one case as plain text
    render_report(results)            -> the whole run as Markdown
    write_report(results, path)       -> ... to a file
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from .models import Category, EmailResult, Status

NO_MISMATCH = "No mismatch detected."

REVIEW_EXPLANATION = {
    "wrong_doc_type": "the second attachment is not a draft BL",
    "missing_attachment": "the documents were referenced but not attached",
    "unreadable": "a file could not be read (empty, corrupt, or a scan with no text)",
    "missing_value": "a required field is blank on one of the documents",
}


def _format_value(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def verdict_line(result: EmailResult) -> str:
    """One sentence a human can act on."""
    if result.category is not Category.BL_COMPARISON:
        return f"Not a document check — filed as {result.category.value}."
    if result.status is Status.OK:
        return NO_MISMATCH
    if result.status is Status.MISMATCH:
        fields = ", ".join(result.defect_fields)
        plural = "field" if len(result.defect_fields) == 1 else "fields"
        return f"Mismatch on {len(result.defect_fields)} {plural}: {fields}."
    reason = result.review_reason.value if result.review_reason else "unknown"
    return (f"Sent for human review — {reason}: "
            f"{REVIEW_EXPLANATION.get(reason, 'the pipeline could not decide')}.")


def render_email(result: EmailResult, width: int = 34) -> str:
    """One case as plain text, with the seven rows side by side."""
    lines = [f"{result.email_id}  [{result.category.value}]  {result.status.value}",
             f"  {verdict_line(result)}"]
    if result.classified_by_rule:
        lines.append(f"  routed by: {result.classified_by_rule} ({result.decided_by.value})")
    if result.error:
        lines.append(f"  error: {result.error}")

    if result.comparisons:
        lines.append("")
        lines.append(f"  {'field':<20} {'SI':<{width}} {'BL':<{width}}")
        lines.append(f"  {'-' * 20} {'-' * width} {'-' * width}")
        for row in result.comparisons:
            flag = " " if row.match else "!"
            lines.append(f"{flag} {row.field:<20} {_format_value(row.si_value):<{width}} "
                         f"{_format_value(row.bl_value):<{width}}")
            if row.note and not row.match:
                lines.append(f"  {'':<20} ({row.note})")
    return "\n".join(lines)


def render_report(results: Iterable[EmailResult]) -> str:
    """The whole run as Markdown: a summary, then every case that needs attention."""
    results = list(results)
    categories = Counter(r.category.value for r in results)
    mismatches = [r for r in results if r.status is Status.MISMATCH]
    reviews = [r for r in results if r.status is Status.NEEDS_REVIEW]
    comparisons = [r for r in results if r.category is Category.BL_COMPARISON]
    clean = [r for r in comparisons if r.status is Status.OK]
    by_rule = sum(1 for r in results if r.decided_by.value == "rule")

    out = [
        "# Shipping document verification — run report",
        "",
        f"**{len(results)} emails processed.** "
        f"{len(comparisons)} document checks, of which {len(mismatches)} have a "
        f"discrepancy, {len(clean)} are clean and {len(reviews)} need a human.",
        "",
        "| | count |",
        "|---|---|",
    ]
    for name, count in sorted(categories.items()):
        out.append(f"| {name} | {count} |")
    out += [
        f"| — of those, discrepancies found | {len(mismatches)} |",
        f"| — of those, escalated to a human | {len(reviews)} |",
        f"| decided by rules (no LLM call) | {by_rule}/{len(results)} "
        f"({by_rule / max(len(results), 1):.0%}) |",
        "",
    ]

    if mismatches:
        field_counts = Counter(f for r in mismatches for f in r.defect_fields)
        out += ["## Which fields go wrong", "", "| field | times flagged |", "|---|---|"]
        out += [f"| {name} | {count} |" for name, count in field_counts.most_common()]
        out.append("")

    out += ["## Discrepancies", ""]
    if not mismatches:
        out.append(f"_{NO_MISMATCH}_")
    for result in mismatches:
        out += [f"### {result.email_id}", "", verdict_line(result), "",
                "| field | SI | BL | |", "|---|---|---|---|"]
        for row in result.comparisons:
            mark = "" if row.match else "**differs**"
            out.append(f"| {row.field} | {_format_value(row.si_value)} | "
                       f"{_format_value(row.bl_value)} | {mark} |")
        out.append("")

    out += ["## Sent for human review", ""]
    if not reviews:
        out.append("_Nothing needed a human._")
    else:
        out += ["| email | reason | what a human needs to do |", "|---|---|---|"]
        for result in reviews:
            reason = result.review_reason.value if result.review_reason else "unknown"
            out.append(f"| {result.email_id} | `{reason}` | "
                       f"{REVIEW_EXPLANATION.get(reason, '—')} |")
    out.append("")
    return "\n".join(out)


def write_report(results: Iterable[EmailResult], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(results), encoding="utf-8")
    return path


__all__ = ["NO_MISMATCH", "verdict_line", "render_email", "render_report", "write_report"]
