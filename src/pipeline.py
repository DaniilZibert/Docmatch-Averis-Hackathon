"""
SHARED — the glue: classify -> extract -> compare -> submission.json.

    python -m src.pipeline                 # run over data/, write submission.json
    python -m src.pipeline --limit 20      # quick pass over the first 20 emails
    python -m src.pipeline --report out/report.md   # also write the discrepancy report

ROUTING A COMPARISON EMAIL WITH NO ATTACHMENTS — the one non-obvious decision here.

94 of the 220 BL_COMPARISON emails arrive with nothing attached, and they are NOT all
the same case:

    91x  "Please assist to send the draft BL for <booking> for checking asap."
         The sender is asking US for the document. There is nothing to compare yet and
         nothing has gone wrong: status OK, no defect, no escalation.
      3x  "Please compare the SI and draft BL ... (attachments appear to have been
         dropped)." The sender believes they attached the documents. A human has to go
         back to them: NEEDS_REVIEW / missing_attachment.

classifier.expects_attachments() draws that line. Escalating all 94 would not change
the final score at all (the scorer reads only category / has_defect / defect_fields)
but it drops escalation precision from 1.00 to 0.18 on the reliability axis, and
"without creating false alarms" is the use case's own wording.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from . import classifier, comparator, submission as submission_mod
from .extractor import extract
from .models import (Category, ComparisonResult, DocType, EmailRecord, EmailResult,
                     ReviewReason, Status)

log = logging.getLogger(__name__)


def process_email(email: EmailRecord, data_dir: str | Path = "data") -> EmailResult:
    """Stage 1 -> 2 -> 3 for one email. Never raises: a crash becomes NEEDS_REVIEW,
    because a silent failure is worse than an honest escalation."""
    try:
        category, decided_by, rule = classifier.classify_with_evidence(email)

        # Only document-comparison requests continue to the checking step.
        if category is not Category.BL_COMPARISON:
            result = EmailResult.non_comparison(email.email_id, category, decided_by)
            result.classified_by_rule = rule
            return result

        si_path = email.attachment_for(DocType.SI)
        bl_path = email.attachment_for(DocType.BL)

        if si_path is None or bl_path is None:
            if classifier.expects_attachments(email):
                # documents were promised but are not here — a human must chase them
                result = EmailResult.from_comparison(
                    category,
                    ComparisonResult.needs_review(email.email_id,
                                                  ReviewReason.MISSING_ATTACHMENT),
                    decided_by)
            else:
                # "please send the draft BL": correctly routed, nothing to compare yet
                result = EmailResult.non_comparison(email.email_id, category, decided_by)
            result.classified_by_rule = rule
            return result

        si = extract(si_path, data_dir, email.email_id, DocType.SI)
        bl = extract(bl_path, data_dir, email.email_id, DocType.BL)

        result = EmailResult.from_comparison(category, comparator.compare(si, bl), decided_by)
        result.classified_by_rule = rule
        return result

    except Exception as exc:  # one bad email must not lose the other 519
        log.exception("email %s failed", email.email_id)
        return EmailResult(
            email_id=email.email_id,
            category=Category.BL_COMPARISON,
            status=Status.NEEDS_REVIEW,
            review_reason=ReviewReason.UNREADABLE,
            needs_human_review=True,
            error=f"{type(exc).__name__}: {exc}",
        )


def run(data_dir: str | Path = "data", limit: int | None = None) -> list[EmailResult]:
    emails = EmailRecord.load_all(data_dir)
    if limit:
        emails = emails[:limit]
    return [process_email(email, data_dir) for email in emails]


def summarise(results: list[EmailResult], elapsed: float) -> str:
    """The run summary. Two numbers here are worth watching on every run:

      * NEEDS_REVIEW total — 20 of the 520 emails genuinely cannot be decided. A run
        that escalates many more than that has logic that is too cautious.
      * decided by rules — the share of the inbox the deterministic path handled,
        the same number the organizers' scoreboard prints as `rule_pct`.
    """
    from .extractor.llm_extract import llm_available

    categories = Counter(r.category.value for r in results)
    statuses = Counter(r.status.value for r in results
                       if r.category is Category.BL_COMPARISON)
    reasons = Counter(r.review_reason.value for r in results if r.review_reason)
    by_rule = sum(1 for r in results if r.decided_by.value == "rule")
    errors = [r for r in results if r.error]

    lines = [f"processed {len(results)} emails in {elapsed:.1f}s", "", "category"]
    for name, count in sorted(categories.items()):
        lines.append(f"  {name:<28} {count}")
    lines += ["", "BL_COMPARISON outcome"]
    for name, count in sorted(statuses.items()):
        lines.append(f"  {name:<28} {count}")
    if reasons:
        lines += ["", "escalated to a human"]
        for name, count in sorted(reasons.items()):
            lines.append(f"  {name:<28} {count}")
        lines.append(f"  {'TOTAL':<28} {sum(reasons.values())}   (20 are genuinely undecidable)")
    lines += ["", f"decided by rules             {by_rule}/{len(results)} "
                  f"({by_rule / max(len(results), 1):.0%})",
              f"Claude available             {'yes' if llm_available() else 'no (rules only)'}"]
    if errors:
        lines += ["", f"errors                       {len(errors)}"]
        for r in errors[:5]:
            lines.append(f"  {r.email_id}: {r.error}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SDOC pipeline over the inbox.")
    parser.add_argument("--data-dir", default="data", help="folder holding inbox/ and attachments/")
    parser.add_argument("--out", default="submission.json", help="where to write the submission")
    parser.add_argument("--limit", type=int, default=None, help="only the first N emails")
    parser.add_argument("--report", default=None,
                        help="also write the human-readable discrepancy report here")
    parser.add_argument("--plain-submission", action="store_true",
                        help="omit decided_by, matching sample_submission.json exactly")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    started = time.time()
    results = run(args.data_dir, args.limit)
    elapsed = time.time() - started

    out_path, problems = submission_mod.save(
        results, args.out, args.data_dir,
        include_diagnostics=not args.plain_submission)

    print(summarise(results, elapsed))
    print(f"\nsubmission -> {out_path}")

    if args.report:
        from .report import write_report
        report_path = write_report(results, args.report)
        print(f"report     -> {report_path}")

    if problems:
        print("\nsubmission shape problems:")
        for problem in problems:
            print(f"  ! {problem}")
        return 1
    print("submission shape OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
