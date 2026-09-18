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

REQUIRED_KEYS = {"category", "status", "review_reason", "defect_fields", "has_defect"}


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
        if keys != REQUIRED_KEYS:
            problems.append(f"{email_id}: keys {sorted(keys)} != {sorted(REQUIRED_KEYS)}")
            break  # one example is enough, they will all be the same shape
    return problems


def save(results: Iterable[EmailResult], path: str | Path = "submission.json",
         data_dir: str | Path = "data") -> tuple[Path, list[str]]:
    """Write submission.json and report any shape problems alongside it."""
    results = list(results)
    submission = build_submission(results)
    problems = validate_submission(submission, data_dir)
    out = write_submission(results, path)
    return out, problems


__all__ = ["REQUIRED_KEYS", "validate_submission", "save"]
