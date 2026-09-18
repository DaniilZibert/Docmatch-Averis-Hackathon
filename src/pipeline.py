"""
SHARED — the glue. Written at step 0, changed by whoever needs it (tell the other person).

This is the whole system in one readable function, and it already runs: with today's
stubs it produces a valid submission.json for all 520 emails. As each of you fills in
your modules, the numbers improve and nothing here has to change.

    python -m src.pipeline                 # run over data/, write submission.json
    python -m src.pipeline --limit 20      # quick pass over the first 20 emails
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import classifier, comparator, submission as submission_mod
from .extractor import extract
from .models import (Category, ComparisonResult, DocType, EmailRecord, EmailResult,
                     ReviewReason, Status)


def process_email(email: EmailRecord, data_dir: str | Path = "data") -> EmailResult:
    """Stage 1 -> 2 -> 3 for one email. Never raises: a crash becomes NEEDS_REVIEW,
    because a silent failure is worse than an honest escalation."""
    try:
        category, decided_by = classifier.classify(email)

        # Only document-comparison requests continue to the checking step.
        if category is not Category.BL_COMPARISON:
            return EmailResult.non_comparison(email.email_id, category, decided_by)

        si_path = email.attachment_for(DocType.SI)
        bl_path = email.attachment_for(DocType.BL)

        if si_path is None or bl_path is None:
            return EmailResult.from_comparison(
                category,
                ComparisonResult.needs_review(email.email_id,
                                              ReviewReason.MISSING_ATTACHMENT),
                decided_by,
            )

        si = extract(si_path, data_dir, email.email_id, DocType.SI)
        bl = extract(bl_path, data_dir, email.email_id, DocType.BL)

        return EmailResult.from_comparison(category, comparator.compare(si, bl), decided_by)

    except Exception as exc:  # one bad email must not lose the other 519
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SDOC pipeline over the inbox.")
    parser.add_argument("--data-dir", default="data", help="folder holding inbox/ and attachments/")
    parser.add_argument("--out", default="submission.json", help="where to write the submission")
    parser.add_argument("--limit", type=int, default=None, help="only the first N emails")
    args = parser.parse_args(argv)

    results = run(args.data_dir, args.limit)

    counts: dict[str, int] = {}
    for r in results:
        key = r.category.value if r.category is not Category.BL_COMPARISON else \
            f"BL_COMPARISON/{r.status.value}"
        counts[key] = counts.get(key, 0) + 1

    out_path, problems = submission_mod.save(results, args.out, args.data_dir)

    print(f"processed {len(results)} emails -> {out_path}")
    for key in sorted(counts):
        print(f"  {key:<28} {counts[key]}")
    if problems:
        print("\nsubmission shape problems:")
        for p in problems:
            print(f"  ! {p}")
        return 1
    print("\nsubmission shape OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
