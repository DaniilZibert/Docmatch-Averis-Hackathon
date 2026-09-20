"""
THE CONTRACT — shared by both contributors. Do not change without telling the other person.

Everything in this file is the agreed interface between the two halves of the project:

    Person A  (classifier.py, extractor/*)  PRODUCES  Category, ExtractedDocument
    Person B  (comparator.py, submission.py)  CONSUMES  them, PRODUCES  ComparisonResult, EmailResult

Because both sides code against these models, neither has to wait for the other: build
fake ExtractedDocuments with `ExtractedDocument.fake()` and you can test comparison logic
before a single real extractor exists.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums — the exact strings the organizers' scorer expects. Do not re-spell these.
# ---------------------------------------------------------------------------

class Category(str, Enum):
    BL_COMPARISON = "BL_COMPARISON"
    SI_REQUEST = "SI_REQUEST"
    INVOICE_QUERY = "INVOICE_QUERY"
    GENERAL = "GENERAL"
    SPAM = "SPAM"


class Status(str, Enum):
    OK = "OK"                      # all 7 fields matched
    MISMATCH = "MISMATCH"          # >=1 field differs
    NEEDS_REVIEW = "NEEDS_REVIEW"  # we cannot decide — escalate to a human


class ReviewReason(str, Enum):
    WRONG_DOC_TYPE = "wrong_doc_type"        # attachment is not the SI/BL we expected
    MISSING_ATTACHMENT = "missing_attachment"  # SI or BL simply isn't there
    UNREADABLE = "unreadable"                # file is corrupt / empty / un-OCR-able
    MISSING_VALUE = "missing_value"          # document readable but a needed field is absent


class DocType(str, Enum):
    SI = "SI"            # Shipping Instruction — the reference document
    BL = "BL"            # draft Bill of Lading — the document being checked
    UNKNOWN = "UNKNOWN"   # could not tell what this document is


class FieldSource(str, Enum):
    RULE = "rule"      # found by regex / alias lookup
    LLM = "llm"        # extracted by Claude from text
    VISION = "vision"  # extracted by Claude from a rendered page image (scanned PDF)


class DecidedBy(str, Enum):
    RULE = "rule"
    LLM = "llm"


# The 7 fields that get compared. Order matters only for display.
COMPARED_FIELDS: tuple[str, ...] = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

# Fields whose values are numbers, not text — comparator parses these numerically.
NUMERIC_FIELDS: frozenset[str] = frozenset({"container_count", "gross_weight_kg"})


# ---------------------------------------------------------------------------
# Input: an email as it appears in data/inbox/email_XXX.json
# ---------------------------------------------------------------------------

class EmailRecord(BaseModel):
    """One inbox record. `sender` is spelled `from` in the JSON (reserved word in Python)."""

    model_config = ConfigDict(populate_by_name=True)

    email_id: str
    sender: str = Field(default="", alias="from")
    subject: str = ""
    body: str = ""
    attachments: list[str] = Field(default_factory=list)

    # -- convenience ------------------------------------------------------
    def attachment_for(self, doc_type: DocType) -> str | None:
        """Path of the SI or BL attachment, or None if this email has none.

        Filenames follow `attachments/email_004_SI.txt` / `..._BL.pdf`, so we match on
        the `_SI.` / `_BL.` marker rather than on the extension.
        """
        marker = f"_{doc_type.value}."
        for path in self.attachments:
            if marker in path:
                return path
        return None

    @property
    def text(self) -> str:
        """Subject + body, what the classifier reads."""
        return f"{self.subject}\n{self.body}"

    @classmethod
    def load_all(cls, data_dir: str | Path = "data") -> list["EmailRecord"]:
        """Read every email_*.json from <data_dir>/inbox, sorted by email_id."""
        inbox = Path(data_dir) / "inbox"
        records = [cls.model_validate_json(p.read_text(encoding="utf-8"))
                   for p in sorted(inbox.glob("email_*.json"))]
        return records


# ---------------------------------------------------------------------------
# Person A's output: a document with its 7 fields pulled out
# ---------------------------------------------------------------------------

class ExtractedField(BaseModel):
    """One of the 7 fields, as found in one document.

    `value` is a str for text fields and an int/float for NUMERIC_FIELDS; None means
    "this document does not state it" (which the comparator turns into missing_value).
    `raw_label` is the label the value was found under — kept as evidence for the
    human-review screen ("we read Load Port: SINGAPORE").
    """

    value: str | int | float | None = None
    confidence: float = 0.0
    source: FieldSource = FieldSource.RULE
    raw_label: str | None = None

    @property
    def is_present(self) -> bool:
        return self.value is not None and str(self.value).strip() != ""


class ExtractedDocument(BaseModel):
    """The result of reading ONE attachment (either the SI or the BL of one email)."""

    email_id: str
    doc_type: DocType
    source_path: str | None = None
    fields: dict[str, ExtractedField] = Field(default_factory=dict)

    # Set when the file could not be read at all (corrupt, empty, OCR gave nothing).
    unreadable: bool = False
    # Set when the file was read but turned out to be a different kind of document.
    wrong_doc_type: bool = False
    # Set when the values were recovered from a scan by vision rather than from a text
    # layer. The document IS readable, but nobody should auto-approve a bill of lading
    # off an OCR'd image: the comparator escalates it to a human with the values filled
    # in, so confirming is one click instead of a re-read.
    needs_confirmation: bool = False
    # Free text for debugging / the review screen.
    notes: str | None = None

    # -- convenience ------------------------------------------------------
    @property
    def present_field_count(self) -> int:
        return sum(1 for name in COMPARED_FIELDS
                   if name in self.fields and self.fields[name].is_present)

    @property
    def missing_fields(self) -> list[str]:
        return [name for name in COMPARED_FIELDS
                if name not in self.fields or not self.fields[name].is_present]

    def value_of(self, field_name: str) -> str | int | float | None:
        field = self.fields.get(field_name)
        return field.value if field else None

    @classmethod
    def missing(cls, email_id: str, doc_type: DocType) -> "ExtractedDocument":
        """The attachment wasn't in the email at all."""
        return cls(email_id=email_id, doc_type=doc_type, source_path=None,
                   unreadable=True, notes="attachment not present in email")

    @classmethod
    def fake(cls, email_id: str = "email_test", doc_type: DocType = DocType.SI,
             **field_values: Any) -> "ExtractedDocument":
        """Build a document by hand — for tests, before the real extractors exist.

            ExtractedDocument.fake("email_001", DocType.BL, consignee="ACME LTD",
                                   container_count=4)

        Any of the 7 fields you don't pass are filled with a plausible default so the
        document counts as fully extracted.
        """
        defaults: dict[str, Any] = {
            "shipper": "TEST SHIPPER SDN BHD",
            "consignee": "TEST CONSIGNEE FZ-LLC",
            "notify_party": "TEST CONSIGNEE FZ-LLC",
            "port_of_loading": "SINGAPORE (SGSIN)",
            "port_of_discharge": "KARACHI, PAKISTAN (PKKHI)",
            "container_count": 3,
            "gross_weight_kg": 22000,
        }
        defaults.update(field_values)
        return cls(
            email_id=email_id,
            doc_type=doc_type,
            source_path=f"attachments/{email_id}_{doc_type.value}.txt",
            fields={name: ExtractedField(value=defaults[name], confidence=1.0,
                                         source=FieldSource.RULE, raw_label=name)
                    for name in COMPARED_FIELDS},
        )


# ---------------------------------------------------------------------------
# Person B's output: the comparison, then the final per-email verdict
# ---------------------------------------------------------------------------

class FieldComparison(BaseModel):
    """One row of the discrepancy report — what the SI said vs what the BL said."""

    field: str
    si_value: str | int | float | None = None
    bl_value: str | int | float | None = None
    match: bool = False
    note: str | None = None


class ComparisonResult(BaseModel):
    """Outcome of comparing one SI against one BL."""

    email_id: str
    status: Status
    review_reason: ReviewReason | None = None
    has_defect: bool = False
    defect_fields: list[str] = Field(default_factory=list)
    comparisons: list[FieldComparison] = Field(default_factory=list)

    @classmethod
    def needs_review(cls, email_id: str, reason: ReviewReason,
                     comparisons: Iterable[FieldComparison] = ()) -> "ComparisonResult":
        return cls(email_id=email_id, status=Status.NEEDS_REVIEW, review_reason=reason,
                   has_defect=False, defect_fields=[], comparisons=list(comparisons))


class EmailResult(BaseModel):
    """The final verdict for one email — one entry of submission.json, plus our own
    bookkeeping fields (which `to_submission_entry` strips out)."""

    email_id: str
    category: Category
    status: Status = Status.OK
    review_reason: ReviewReason | None = None
    has_defect: bool = False
    defect_fields: list[str] = Field(default_factory=list)

    # -- our own bookkeeping, not part of the organizers' schema ----------
    decided_by: DecidedBy = DecidedBy.RULE
    # which classifier rule fired ("bl:has-attachment", "llm", ...) — shown on the
    # review screen so a human can see why an email was routed where it was.
    classified_by_rule: str | None = None
    needs_human_review: bool = False
    comparisons: list[FieldComparison] = Field(default_factory=list)
    error: str | None = None

    @classmethod
    def non_comparison(cls, email_id: str, category: Category,
                       decided_by: DecidedBy = DecidedBy.RULE) -> "EmailResult":
        """Emails that are not BL_COMPARISON only need a category; the scorer wants
        status OK / no defect for them (matching sample_submission.json)."""
        return cls(email_id=email_id, category=category, status=Status.OK,
                   review_reason=None, has_defect=False, defect_fields=[],
                   decided_by=decided_by)

    @classmethod
    def from_comparison(cls, category: Category, comparison: ComparisonResult,
                        decided_by: DecidedBy = DecidedBy.RULE) -> "EmailResult":
        return cls(
            email_id=comparison.email_id,
            category=category,
            status=comparison.status,
            review_reason=comparison.review_reason,
            has_defect=comparison.has_defect,
            defect_fields=list(comparison.defect_fields),
            decided_by=decided_by,
            needs_human_review=comparison.status is Status.NEEDS_REVIEW,
            comparisons=list(comparison.comparisons),
        )

    def to_submission_entry(self, include_diagnostics: bool = True) -> dict[str, Any]:
        """One entry of submission.json.

        The 5 keys of sample_submission.json, plus `decided_by`. That sixth key is not
        decoration: the organizers' scorer reads it (scoring.py, score_stage1) and
        reports `rule_pct` — "resolved by rules (cost)" — on the scoreboard. Omitting it
        silently throws away the one number that evidences our rules-first design.
        Nothing else is added: the scorer ignores unknown keys, but a submission is a
        contract, not a scratchpad.

        Pass include_diagnostics=False for a submission that is byte-identical in shape
        to sample_submission.json.
        """
        entry: dict[str, Any] = {
            "category": self.category.value,
            "status": self.status.value,
            "review_reason": self.review_reason.value if self.review_reason else None,
            "defect_fields": list(self.defect_fields),
            "has_defect": bool(self.has_defect),
        }
        if include_diagnostics:
            entry["decided_by"] = self.decided_by.value
        return entry


# ---------------------------------------------------------------------------
# submission.json
# ---------------------------------------------------------------------------

def build_submission(results: Iterable[EmailResult],
                     include_diagnostics: bool = True) -> dict[str, dict[str, Any]]:
    """Turn our results into the `{email_id: {...}}` object the scorer expects."""
    return {r.email_id: r.to_submission_entry(include_diagnostics) for r in results}


def write_submission(results: Iterable[EmailResult], path: str | Path = "submission.json",
                     include_diagnostics: bool = True) -> Path:
    path = Path(path)
    payload = build_submission(results, include_diagnostics)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
