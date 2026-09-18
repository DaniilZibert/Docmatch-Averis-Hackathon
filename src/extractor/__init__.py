"""
OWNER: Person A.  Attachment -> ExtractedDocument.

`extract()` is the single entry point the pipeline calls. It dispatches on the file
extension and always returns an ExtractedDocument — never raises, never returns None.
An attachment it cannot read comes back with `unreadable=True` so the comparator can
escalate it instead of guessing.

STATUS: dispatcher works; the per-format extractors are stubs. Fill them in, in this
order: txt (192 files) -> xlsx (22) -> docx (8) -> pdf (28).
"""

from __future__ import annotations

from pathlib import Path

from ..models import DocType, ExtractedDocument


def extract(attachment_path: str, data_dir: str | Path = "data",
            email_id: str = "", doc_type: DocType | None = None) -> ExtractedDocument:
    """Read one attachment and pull out the 7 compared fields.

    attachment_path: exactly as it appears in the email record,
                     e.g. "attachments/email_004_SI.txt"
    """
    path = Path(data_dir) / attachment_path
    if doc_type is None:
        doc_type = DocType.SI if "_SI." in attachment_path else (
            DocType.BL if "_BL." in attachment_path else DocType.UNKNOWN)
    if not email_id:
        email_id = Path(attachment_path).stem.rsplit("_", 1)[0]

    if not path.exists():
        return ExtractedDocument.missing(email_id, doc_type)

    suffix = path.suffix.lower()
    try:
        if suffix == ".txt":
            from .txt_extractor import extract_txt
            return extract_txt(path, email_id, doc_type, attachment_path)
        if suffix == ".xlsx":
            from .xlsx_extractor import extract_xlsx
            return extract_xlsx(path, email_id, doc_type, attachment_path)
        if suffix == ".docx":
            from .docx_extractor import extract_docx
            return extract_docx(path, email_id, doc_type, attachment_path)
        if suffix == ".pdf":
            from .pdf_extractor import extract_pdf
            return extract_pdf(path, email_id, doc_type, attachment_path)
    except Exception as exc:  # never let one bad file kill the run
        return ExtractedDocument(email_id=email_id, doc_type=doc_type,
                                 source_path=attachment_path, unreadable=True,
                                 notes=f"{type(exc).__name__}: {exc}")

    return ExtractedDocument(email_id=email_id, doc_type=doc_type,
                             source_path=attachment_path, unreadable=True,
                             notes=f"unsupported file type: {suffix}")


__all__ = ["extract"]
