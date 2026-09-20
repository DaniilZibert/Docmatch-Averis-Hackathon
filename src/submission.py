"""
OWNER: Person B.  Submission file assembly + shape validation.

The assembly itself lives in models.build_submission / models.write_submission; what
belongs here is the guard rail: EVERY email_id in the dataset must be present, with
exactly the 5 keys the scorer reads. A missing email_id is silently scored as GENERAL,
which is a free loss.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .models import EmailResult, build_submission, write_submission

# The five keys sample_submission.json defines. Every entry must carry all of them.
REQUIRED_KEYS = {"category", "status", "review_reason", "defect_fields", "has_defect"}

# Extra keys we are allowed to add. `decided_by` is read by the organizers' scorer
# (scoring.py -> score_stage1 -> rule_pct) to report what share of the inbox our rules
# resolved without an LLM call. Anything not listed here is a typo, and a typo in a
# submission is a silent zero — so unknown keys are reported as a problem.
OPTIONAL_KEYS = {"decided_by"}

# Values the scorer recognises, so a misspelling is caught here and not on the leaderboard.
VALID_CATEGORIES = {"BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"}
VALID_STATUSES = {"OK", "MISMATCH", "NEEDS_REVIEW"}
VALID_REVIEW_REASONS = {None, "wrong_doc_type", "missing_attachment", "unreadable",
                        "missing_value"}
COMPARED_FIELD_NAMES = {"shipper", "consignee", "notify_party", "port_of_loading",
                        "port_of_discharge", "container_count", "gross_weight_kg"}


def validate_submission(submission: dict[str, Any], data_dir: str | Path = "data") -> list[str]:
    """Return a list of problems; empty list means the file is well formed."""
    problems: list[str] = []

    sample_path = Path(data_dir) / "sample_submission.json"
    if sample_path.exists():
        expected_ids = set(json.loads(sample_path.read_text(encoding="utf-8")))
        missing = expected_ids - set(submission)
        extra = set(submission) - expected_ids
        if missing:
            problems.append(f"{len(missing)} email_id(s) missing, e.g. {sorted(missing)[:3]}")
        if extra:
            problems.append(f"{len(extra)} unexpected email_id(s), e.g. {sorted(extra)[:3]}")

    for email_id, entry in submission.items():
        keys = set(entry)
        missing_keys = REQUIRED_KEYS - keys
        unknown_keys = keys - REQUIRED_KEYS - OPTIONAL_KEYS
        if missing_keys or unknown_keys:
            problems.append(
                f"{email_id}: missing keys {sorted(missing_keys)}, "
                f"unknown keys {sorted(unknown_keys)}")
            break  # one example is enough, they will all be the same shape

    # Value-level checks. A misspelled category scores as a miss on two axes at once
    # and there is nothing in the scoreboard that tells you it was a typo.
    for email_id, entry in submission.items():
        if entry.get("category") not in VALID_CATEGORIES:
            problems.append(f"{email_id}: category {entry.get('category')!r} is not one of "
                            f"{sorted(VALID_CATEGORIES)}")
            break
    for email_id, entry in submission.items():
        if entry.get("status") not in VALID_STATUSES:
            problems.append(f"{email_id}: status {entry.get('status')!r} is not one of "
                            f"{sorted(VALID_STATUSES)}")
            break
    for email_id, entry in submission.items():
        if entry.get("review_reason") not in VALID_REVIEW_REASONS:
            problems.append(f"{email_id}: review_reason {entry.get('review_reason')!r} "
                            f"is not a recognised reason")
            break
    for email_id, entry in submission.items():
        bad = set(entry.get("defect_fields") or []) - COMPARED_FIELD_NAMES
        if bad:
            problems.append(f"{email_id}: defect_fields contains unknown field(s) {sorted(bad)}")
            break
    # has_defect and defect_fields must agree, or end-to-end silently fails.
    for email_id, entry in submission.items():
        if bool(entry.get("has_defect")) != bool(entry.get("defect_fields")):
            problems.append(
                f"{email_id}: has_defect={entry.get('has_defect')} but "
                f"defect_fields={entry.get('defect_fields')} — the scorer needs both")
            break
    return problems


def save(results: Iterable[EmailResult], path: str | Path = "submission.json",
         data_dir: str | Path = "data",
         include_diagnostics: bool = True) -> tuple[Path, list[str]]:
    """Write submission.json and report any shape problems alongside it."""
    results = list(results)
    submission = build_submission(results, include_diagnostics)
    problems = validate_submission(submission, data_dir)
    out = write_submission(results, path, include_diagnostics)
    return out, problems


__all__ = ["REQUIRED_KEYS", "OPTIONAL_KEYS", "validate_submission", "save"]
