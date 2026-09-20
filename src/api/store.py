"""
The service's state, and the run that fills it.

Deliberately in-memory: the pipeline is a sub-second batch over the whole inbox, so a
database during the event would be a moving part with nothing to move.
`src/db/schema.sql` records the shape a real deployment persists, where runs are
incremental and the review queue has to outlive the process.

The inbox is processed automatically when the service starts. Nobody should have to
issue a command to make the product show its own data.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import Category, EmailRecord, EmailResult, Status


@dataclass
class RunState:
    """What the last (or current) pass over the inbox is doing."""

    status: str = "idle"                 # idle | running | ready | failed
    started_at: float | None = None
    finished_at: float | None = None
    processed: int = 0
    error: str | None = None
    llm_calls: int = 0

    @property
    def seconds(self) -> float | None:
        if self.started_at is None:
            return None
        return (self.finished_at or time.time()) - self.started_at

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "processed": self.processed,
                "seconds": round(self.seconds, 2) if self.seconds else None,
                "llm_calls": self.llm_calls, "error": self.error}


class Store:
    """Everything the screens read. One instance, guarded by a lock so a re-run cannot
    be seen half-applied by a request in flight."""

    def __init__(self) -> None:
        self.emails: dict[str, EmailRecord] = {}
        self.results: dict[str, EmailResult] = {}
        self.resolutions: dict[str, dict[str, Any]] = {}
        self.run = RunState()
        self._lock = threading.Lock()

    # -- reading ---------------------------------------------------------
    @property
    def ready(self) -> bool:
        return bool(self.results)

    def result(self, email_id: str) -> EmailResult | None:
        return self.results.get(email_id)

    def email(self, email_id: str) -> EmailRecord | None:
        return self.emails.get(email_id)

    def ordered(self) -> list[EmailResult]:
        return [self.results[eid] for eid in sorted(self.results)]

    def filtered(self, category: str | None = None, status: str | None = None,
                 query: str | None = None) -> list[EmailResult]:
        rows = self.ordered()
        if category:
            rows = [r for r in rows if r.category.value == category.upper()]
        if status:
            rows = [r for r in rows if r.status.value == status.upper()]
        if query:
            needle = query.lower()
            rows = [r for r in rows
                    if needle in r.email_id.lower()
                    or needle in (self.emails[r.email_id].subject.lower()
                                  if r.email_id in self.emails else "")
                    or needle in (self.emails[r.email_id].sender.lower()
                                  if r.email_id in self.emails else "")]
        return rows

    def open_reviews(self) -> list[EmailResult]:
        return [r for r in self.ordered()
                if r.status is Status.NEEDS_REVIEW and r.email_id not in self.resolutions]

    def mismatches(self) -> list[EmailResult]:
        return [r for r in self.ordered() if r.status is Status.MISMATCH]

    def comparisons(self) -> list[EmailResult]:
        return [r for r in self.ordered() if r.category is Category.BL_COMPARISON]

    def counts(self) -> dict[str, int]:
        return {
            "emails": len(self.results),
            "checks": len(self.comparisons()),
            "discrepancies": len(self.mismatches()),
            "review": len(self.open_reviews()),
            "settled": len(self.resolutions),
        }

    def next_open_review(self, after: str) -> str | None:
        queue = [r.email_id for r in self.open_reviews()]
        later = [eid for eid in queue if eid > after]
        return later[0] if later else (queue[0] if queue else None)

    # -- writing ---------------------------------------------------------
    def start_run(self, data_dir: str | Path = "data", limit: int | None = None) -> bool:
        """Kick off a pass in the background. False if one is already going."""
        with self._lock:
            if self.run.status == "running":
                return False
            self.run = RunState(status="running", started_at=time.time())
        threading.Thread(target=self._run, args=(data_dir, limit), daemon=True).start()
        return True

    def _run(self, data_dir: str | Path, limit: int | None) -> None:
        from .. import pipeline
        from ..extractor.llm_extract import calls_made, reset_budget
        try:
            reset_budget()
            emails = EmailRecord.load_all(data_dir)
            if limit:
                emails = emails[:limit]
            results = [pipeline.process_email(e, data_dir) for e in emails]
            with self._lock:
                self.emails = {e.email_id: e for e in emails}
                self.results = {r.email_id: r for r in results}
                self.resolutions.clear()
                self.run.processed = len(results)
                self.run.llm_calls = calls_made()
                self.run.finished_at = time.time()
                self.run.status = "ready"
        except Exception as exc:                     # a failed run must be visible
            with self._lock:
                self.run.error = f"{type(exc).__name__}: {exc}"
                self.run.finished_at = time.time()
                self.run.status = "failed"

    def resolve(self, email_id: str, status: Status, defect_fields: list[str],
                reviewer: str, note: str | None = None) -> EmailResult | None:
        """Record a human's decision and fold it into the verdict."""
        result = self.results.get(email_id)
        if result is None:
            return None
        with self._lock:
            result.status = status
            result.defect_fields = sorted(defect_fields)
            result.has_defect = status is Status.MISMATCH
            if status is not Status.NEEDS_REVIEW:
                result.review_reason = None
            result.needs_human_review = status is Status.NEEDS_REVIEW
            self.resolutions[email_id] = {
                "status": status.value, "defect_fields": result.defect_fields,
                "reviewer": reviewer, "note": note, "at": time.time(),
            }
        return result


STORE = Store()

__all__ = ["RunState", "Store", "STORE"]
