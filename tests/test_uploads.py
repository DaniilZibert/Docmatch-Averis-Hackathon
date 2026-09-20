"""
Letting a judge try the system on their own documents.

The interesting cases here are the hostile ones: a zip that tries to write outside
itself, a file type we cannot read, an archive that is not an archive. An upload form on
a public URL is the one place a stranger hands us bytes.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from src.api import uploads


def zip_of(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


SI = b"SHIPPING INSTRUCTION\nShipper: ACME\nConsignee: BUYER LTD\n"
BL = b"BILL OF LADING (DRAFT)\nShipper: ACME\nTo the Order of: BUYER LTD\n"


# --- one pair --------------------------------------------------------------

def test_a_pair_becomes_a_normal_email_record():
    """An upload must go down the same code path as the bundled inbox, not a parallel
    one with its own bugs."""
    data_dir, email = uploads.save_pair("si.txt", SI, "bl.txt", BL)
    assert email.attachment_for.__self__ is email          # it is a real EmailRecord
    assert (data_dir / email.attachments[0]).read_bytes() == SI
    assert (data_dir / email.attachments[1]).read_bytes() == BL
    assert "_SI." in email.attachments[0]
    assert "_BL." in email.attachments[1]


def test_the_uploaded_filename_does_not_decide_which_document_is_which():
    """The extractor keys off the _SI./_BL. marker, so a file called BL.txt uploaded in
    the SI slot must still be treated as the SI."""
    _dir, email = uploads.save_pair("BL.txt", SI, "SI.txt", BL)
    assert "_SI." in email.attachments[0]
    assert "_BL." in email.attachments[1]


@pytest.mark.parametrize("name", ["notes.md", "archive.tar", "script.sh", "photo.jpeg", "noext"])
def test_formats_we_cannot_read_are_refused(name: str):
    with pytest.raises(uploads.UploadError, match="we read"):
        uploads.save_pair(name, SI, "bl.txt", BL)


def test_an_empty_file_is_refused():
    with pytest.raises(uploads.UploadError, match="empty"):
        uploads.save_pair("si.txt", b"", "bl.txt", BL)


def test_an_oversized_file_is_refused():
    huge = b"x" * (uploads.MAX_FILE_BYTES + 1)
    with pytest.raises(uploads.UploadError, match="limit"):
        uploads.save_pair("si.txt", huge, "bl.txt", BL)


def test_the_subject_and_body_are_optional_but_used():
    _dir, default = uploads.save_pair("si.txt", SI, "bl.txt", BL)
    assert default.subject and default.body                # sensible defaults

    _dir, given = uploads.save_pair("si.txt", SI, "bl.txt", BL,
                                    subject="MY SUBJECT", body="my body")
    assert given.subject == "MY SUBJECT"
    assert given.body == "my body"


# --- a whole inbox ---------------------------------------------------------

def test_a_well_formed_inbox_zip_unpacks():
    record = {"email_id": "email_001", "from": "a@b.c", "subject": "s", "body": "b",
              "attachments": ["attachments/email_001_SI.txt",
                              "attachments/email_001_BL.txt"]}
    root = uploads.save_inbox_zip(zip_of({
        "inbox/email_001.json": json.dumps(record).encode(),
        "attachments/email_001_SI.txt": SI,
        "attachments/email_001_BL.txt": BL,
    }))
    assert (root / "inbox" / "email_001.json").exists()
    assert (root / "attachments" / "email_001_SI.txt").read_bytes() == SI


def test_a_zip_with_one_wrapping_folder_still_works():
    """Zipping a directory is the normal way to make one of these."""
    record = {"email_id": "email_001", "from": "a@b.c", "subject": "s", "body": "b",
              "attachments": ["attachments/email_001_SI.txt"]}
    root = uploads.save_inbox_zip(zip_of({
        "my-data/inbox/email_001.json": json.dumps(record).encode(),
        "my-data/attachments/email_001_SI.txt": SI,
    }))
    assert (root / "inbox" / "email_001.json").exists()


def test_a_zip_that_writes_outside_itself_is_refused():
    """The classic archive attack: a member path that escapes the extraction root."""
    with pytest.raises(uploads.UploadError, match="outside"):
        uploads.save_inbox_zip(zip_of({
            "inbox/email_001.json": b"{}",
            "../../../../tmp/owned.txt": b"pwned",
        }))


def test_something_that_is_not_a_zip_is_refused():
    with pytest.raises(uploads.UploadError, match="does not open"):
        uploads.save_inbox_zip(b"this is just text, not an archive at all")


def test_a_zip_without_an_inbox_is_refused():
    with pytest.raises(uploads.UploadError, match="no inbox"):
        uploads.save_inbox_zip(zip_of({"readme.txt": b"hello"}))


def test_an_inbox_with_no_records_is_refused():
    with pytest.raises(uploads.UploadError, match="no .json"):
        uploads.save_inbox_zip(zip_of({"inbox/notes.txt": b"hello"}))


def test_an_oversized_zip_is_refused():
    with pytest.raises(uploads.UploadError, match="limit"):
        uploads.save_inbox_zip(b"x" * (uploads.MAX_ZIP_BYTES + 1))


# --- through the service ---------------------------------------------------

def test_uploading_a_pair_returns_the_comparison(tmp_path, monkeypatch):
    """End to end: the same seven rows a bundled case shows."""
    import os
    os.environ["SDOC_NO_AUTORUN"] = "1"
    from fastapi.testclient import TestClient
    from src.api.main import app

    with TestClient(app) as client:
        response = client.post("/try", files={
            "si": ("si.txt", open("data/attachments/email_004_SI.txt", "rb"), "text/plain"),
            "bl": ("bl.txt", open("data/attachments/email_004_BL.txt", "rb"), "text/plain"),
        })
    assert response.status_code == 200
    page = response.text
    assert "EAST BRIGHT FZ-LLC" in page          # what the SI said
    assert "UAB NOVAKOPA" in page                # what the BL said
    assert "consignee" in page and "notify_party" in page


def test_a_bad_upload_explains_itself_rather_than_500ing():
    import os
    os.environ["SDOC_NO_AUTORUN"] = "1"
    from fastapi.testclient import TestClient
    from src.api.main import app

    with TestClient(app) as client:
        response = client.post("/try", files={
            "si": ("si.exe", b"binary", "application/octet-stream"),
            "bl": ("bl.txt", BL, "text/plain"),
        })
    assert response.status_code == 400
    assert "we read" in response.text
