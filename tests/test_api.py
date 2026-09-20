"""
The service and the screens.

The point of these is the product behaviour, not the HTML: the inbox is processed
without anyone issuing a command, a reviewer's decision actually changes the verdict
and the report, and the attachment route cannot be talked into serving a file outside
the data directory.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ["SDOC_NO_AUTORUN"] = "1"      # the suite drives the run itself

from fastapi.testclient import TestClient      # noqa: E402

from src.api.main import app                   # noqa: E402
from src.api.store import STORE                # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        STORE.start_run("data")
        while STORE.run.status == "running":
            time.sleep(0.05)      # yield the GIL; a busy-wait starves the run thread
        yield c


def test_the_service_answers_before_the_inbox_is_processed():
    """A health check must work while the first run is still going, or the load
    balancer kills the container during startup."""
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200


def test_the_run_reports_itself(client):
    body = client.get("/health").json()
    assert body["run"]["status"] == "ready"
    assert body["emails"] == 520
    assert body["checks"] == 220
    assert body["run"]["seconds"] is not None


@pytest.mark.parametrize("path", ["/", "/inbox", "/review", "/report",
                                  "/case/email_004"])
def test_every_screen_renders(client, path: str):
    response = client.get(path)
    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


def test_the_overview_leads_to_the_work(client):
    page = client.get("/").text
    assert "need a person" in page
    assert "/case/email_" in page              # the rows are links into the cases


def test_inbox_filters_and_search(client):
    assert client.get("/inbox?category=SPAM").text.count("class=id") == 40
    assert client.get("/inbox?status=NEEDS_REVIEW").text.count("class=id") == 20
    assert "email_004" in client.get("/inbox?q=email_004").text


def test_a_case_shows_the_email_and_both_documents(client):
    page = client.get("/case/email_004").text
    assert "docs@vitalsolutions.sg" in page             # the email itself
    assert "EAST BRIGHT FZ-LLC" in page                 # what the SI said
    assert "UAB NOVAKOPA" in page                       # what the BL said
    assert "/attachment/email_004_SI.txt" in page       # and the source documents
    assert "Confirm discrepancy" in page                # and a decision to make


def test_a_blank_field_is_never_pre_ticked_as_a_defect(client):
    """email_517's SI leaves two ports blank. Pre-ticking them would walk the reviewer
    into calling a missing value a discrepancy — the exact confusion we exist to stop."""
    page = client.get("/case/email_517").text
    assert page.count('type=checkbox value="port_of_loading" checked') == 0
    assert 'value="port_of_loading"' in page            # still tickable by hand

    mismatch = client.get("/case/email_004").text       # a real defect IS pre-ticked
    assert 'value="consignee" checked' in mismatch


def test_a_reviewer_decision_changes_the_verdict_and_the_report(client):
    before = client.get("/health").json()
    response = client.post("/review/email_520",
                           json={"status": "MISMATCH", "defect_fields": ["consignee"],
                                 "reviewer": "tester"})
    assert response.status_code == 200
    assert response.json()["updated"]["status"] == "MISMATCH"

    after = client.get("/health").json()
    assert after["review"] == before["review"] - 1
    assert after["settled"] == before["settled"] + 1
    assert "email_520" in client.get("/report.md").text

    detail = client.get("/results/email_520").json()
    assert detail["resolved_by_human"] is True
    assert detail["resolution"]["reviewer"] == "tester"


def test_submission_stays_valid_after_a_human_edit(client):
    from src.submission import validate_submission
    assert validate_submission(client.get("/submission.json").json(), "data") == []


def test_attachments_are_served_but_only_from_the_data_directory(client):
    assert "SHIPPING INSTRUCTION" in client.get("/attachment/email_004_SI.txt").text
    assert client.get("/attachment/email_059_SI.pdf").status_code == 200
    for attempt in ["../../.env", "../.gitignore", "nope.txt"]:
        assert client.get(f"/attachment/{attempt}").status_code == 404, attempt


def test_unknown_email_is_a_404_not_a_crash(client):
    assert client.get("/case/email_999999").status_code == 404
    assert client.get("/results/email_999999").status_code == 404
    assert client.post("/review/email_999999", json={"status": "OK"}).status_code == 404
