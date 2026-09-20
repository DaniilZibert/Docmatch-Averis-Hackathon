"""
Letting someone try the system on their own documents.

Two ways in, because judges want different things at different moments:

  a pair      drop an SI and a draft BL and see the seven fields compared. Thirty
              seconds, no setup, and it is the question the product exists to answer.
  an inbox    a .zip shaped like data/ — inbox/*.json plus attachments/ — which
              replaces the working dataset and re-runs everything.

Uploaded documents are, by definition, layouts we have never seen. That is the point:
the rules will parse what they recognise and Claude reads the rest, so an upload is the
honest demonstration of the hybrid rather than a rehearsed one. It is also the case
where the AI genuinely earns its place.

Nothing is written into `data/`. Uploads live under a scratch directory and the bundled
dataset is always one click away again.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from ..models import DocType, EmailRecord

# A judge is trying a document, not uploading a corpus. These are generous for the
# former and small enough that nobody can fill the disk with the latter.
MAX_FILE_BYTES = 8 * 1024 * 1024          # 8 MB per attachment
MAX_ZIP_BYTES = 64 * 1024 * 1024          # 64 MB per inbox
MAX_ZIP_ENTRIES = 4000
ALLOWED_SUFFIXES = {".txt", ".pdf", ".xlsx", ".docx", ".json"}

UPLOAD_ROOT = Path(tempfile.gettempdir()) / "sdoc-uploads"


class UploadError(ValueError):
    """Something about the upload is wrong, and the message says what."""


def _check(name: str, data: bytes, limit: int = MAX_FILE_BYTES) -> None:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError(f"{name}: we read .txt, .pdf, .xlsx and .docx — not {suffix or 'that'}")
    if not data:
        raise UploadError(f"{name} is empty")
    if len(data) > limit:
        raise UploadError(f"{name} is {len(data) // 1024 // 1024} MB; the limit is "
                          f"{limit // 1024 // 1024} MB")


def save_pair(si_name: str, si_bytes: bytes, bl_name: str, bl_bytes: bytes,
              subject: str = "", body: str = "") -> tuple[Path, EmailRecord]:
    """Write one uploaded SI/BL pair into a throwaway dataset directory.

    Returns (data_dir, email) ready for pipeline.process_email — the same code path the
    bundled inbox takes, so an upload is not a special case with its own bugs.
    """
    _check(si_name, si_bytes)
    _check(bl_name, bl_bytes)

    email_id = "upload_" + uuid.uuid4().hex[:8]
    root = UPLOAD_ROOT / email_id
    (root / "attachments").mkdir(parents=True, exist_ok=True)

    # The extractor decides SI from BL by the _SI. / _BL. marker in the filename, so the
    # uploaded names are normalised rather than trusted.
    si_path = f"attachments/{email_id}_SI{Path(si_name).suffix.lower()}"
    bl_path = f"attachments/{email_id}_BL{Path(bl_name).suffix.lower()}"
    (root / si_path).write_bytes(si_bytes)
    (root / bl_path).write_bytes(bl_bytes)

    email = EmailRecord(
        email_id=email_id,
        sender="upload@docmatch.tech",
        subject=subject.strip() or f"TO CONFIRM DOCS _ uploaded pair _ {si_name} / {bl_name}",
        body=body.strip() or ("Uploaded through the website: please compare the attached "
                              "shipping instruction against the draft bill of lading."),
        attachments=[si_path, bl_path],
    )
    (root / "inbox").mkdir(exist_ok=True)
    (root / "inbox" / f"{email_id}.json").write_text(
        json.dumps({"email_id": email.email_id, "from": email.sender,
                    "subject": email.subject, "body": email.body,
                    "attachments": email.attachments}, indent=2), encoding="utf-8")
    return root, email


def save_inbox_zip(data: bytes) -> Path:
    """Unpack an uploaded .zip into a dataset directory and return its path.

    Expects the shape of `data/`: an `inbox/` of email_*.json and an `attachments/`.
    A single wrapping folder is tolerated, because that is what zipping a directory
    usually produces.
    """
    if len(data) > MAX_ZIP_BYTES:
        raise UploadError(f"the zip is {len(data) // 1024 // 1024} MB; "
                          f"the limit is {MAX_ZIP_BYTES // 1024 // 1024} MB")

    root = UPLOAD_ROOT / ("inbox_" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True, exist_ok=True)
    staging = root / "_unpacked"

    try:
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            if len(members) > MAX_ZIP_ENTRIES:
                raise UploadError(f"{len(members)} files in the zip; "
                                  f"the limit is {MAX_ZIP_ENTRIES}")
            for m in members:
                # Reject absolute paths and ../ escapes rather than trusting the archive.
                target = (staging / m.filename).resolve()
                if not str(target).startswith(str(staging.resolve())):
                    raise UploadError(f"{m.filename}: the zip tries to write outside itself")
                if Path(m.filename).suffix.lower() not in ALLOWED_SUFFIXES:
                    continue                       # skip the README, .DS_Store and friends
            zf.extractall(staging)
    except zipfile.BadZipFile:
        shutil.rmtree(root, ignore_errors=True)
        raise UploadError("that does not open as a zip file")

    # find the directory that actually holds inbox/
    candidates = [p.parent for p in staging.rglob("inbox") if p.is_dir()]
    if not candidates:
        shutil.rmtree(root, ignore_errors=True)
        raise UploadError("no inbox/ folder in the zip — it should look like data/: "
                          "inbox/email_*.json plus attachments/")
    base = candidates[0]
    if not list((base / "inbox").glob("*.json")):
        shutil.rmtree(root, ignore_errors=True)
        raise UploadError("inbox/ contains no .json email records")

    for name in ("inbox", "attachments"):
        src = base / name
        if src.is_dir():
            shutil.move(str(src), str(root / name))
    (root / "attachments").mkdir(exist_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    return root


def cleanup(older_than_seconds: int = 6 * 3600) -> int:
    """Delete stale upload directories. Returns how many went."""
    import time
    if not UPLOAD_ROOT.exists():
        return 0
    cutoff = time.time() - older_than_seconds
    gone = 0
    for d in UPLOAD_ROOT.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                gone += 1
        except OSError:
            pass
    return gone


__all__ = ["UploadError", "MAX_FILE_BYTES", "MAX_ZIP_BYTES", "ALLOWED_SUFFIXES",
           "UPLOAD_ROOT", "save_pair", "save_inbox_zip", "cleanup"]
