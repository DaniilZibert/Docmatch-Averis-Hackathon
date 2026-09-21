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


def test_an_escalation_with_no_attachments_is_not_a_dead_end(client):
    """email_506 is routed to BL_COMPARISON but nothing was attached, so there are no
    comparison rows. The queue still asks a person to look at it, so the case has to
    say what is missing and offer a way to close it — otherwise the reviewer arrives
    to an empty column under a banner telling them to review."""
    page = client.get("/case/email_506").text
    assert "Nothing to decide on this one" not in page
    assert "There is nothing to compare" in page
    assert "nothing was attached" in page                # what actually arrived
    assert "Reply to the sender" in page                 # what to do about it
    assert "Documents requested" in page                 # and two ways to close it
    assert "No check needed" in page


def test_leave_open_really_leaves_the_case_open(client):
    """Recording a resolution is exactly what removes a case from the queue, so the
    button labelled "leave open" must not record one. It used to, and quietly drained
    the review queue one click at a time."""
    open_before = len(STORE.open_reviews())
    page = client.get("/case/email_501").text            # a case with rows to tick
    assert ">Leave open</a>" in page                     # a link, not a decision
    assert "'NEEDS_REVIEW'" not in page                  # nothing settles it as-is
    assert len(STORE.open_reviews()) == open_before


def test_a_clean_email_still_offers_nothing_to_decide(client):
    """The fix must not hand review buttons to the 400-odd emails that are simply fine."""
    page = client.get("/case/email_011").text            # GENERAL, no rows, status OK
    assert "Nothing to decide on this one" in page
    assert "Documents requested" not in page


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


def test_the_llm_switch_is_reachable_from_the_service(client, tmp_path, monkeypatch):
    """The header switch posts here. Off is the default and must survive being read."""
    monkeypatch.setenv("SDOC_STATE_FILE", str(tmp_path / "state.json"))

    assert client.get("/settings/llm").json()["enabled"] is False

    on = client.post("/settings/llm", json={"enabled": True}).json()
    assert on["enabled"] is True
    assert client.get("/health").json()["llm_detail"]["enabled"] is True

    off = client.post("/settings/llm", json={"enabled": False}).json()
    assert off["enabled"] is False


def test_every_screen_shows_the_switch(client):
    for path in ["/", "/inbox", "/review", "/report", "/case/email_004"]:
        assert "toggleLlm" in client.get(path).text, path


def test_the_run_watcher_waits_for_the_dom(client):
    """Regression: 'processing the inbox…' used to hang forever.

    The <script> tag sits in the head, before <body> is parsed, so a top-level
    `document.body.dataset.run` check read null, armed nothing, and left the banner
    spinning until somebody reloaded by hand. The watcher must be deferred.
    """
    page = client.get("/").text
    script_at = page.index("<script>")
    body_at = page.index("<body")
    assert script_at < body_at, "the script still runs before <body> is parsed"

    script = page[script_at:page.index("</script>", script_at)]
    assert "DOMContentLoaded" in script, "the watcher must wait for the DOM"
    # nothing may touch document.body outside a function or the listener
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or not stripped:
            continue
        if "document.body" in stripped:
            assert stripped.startswith(("if (!document.body", "results", "const", "let")) \
                or "function" in script[:script.index(stripped)].rsplit("\n", 40)[0], \
                f"top-level document.body access: {stripped}"


def test_the_page_advertises_the_run_state_for_the_watcher(client):
    """The watcher keys off data-run; if the attribute goes, it silently never fires."""
    assert 'data-run="ready"' in client.get("/").text


def test_a_whole_list_row_is_a_link_to_its_case(client):
    """A single small link in the first column did not read as "open this" — people
    could not find their way into a case. The row carries the target now."""
    for path in ("/inbox", "/review", "/"):
        page = client.get(path).text
        if "class=id" not in page:
            continue                                  # an empty list on this screen
        assert 'tr class=row data-href="/case/' in page, path
        # the id must stay a real anchor: middle-click and open-in-new-tab depend on it
        assert '<td class=id><a href="/case/' in page, path


def test_the_row_click_handler_leaves_real_interactions_alone(client):
    """Widening the click target must not swallow a link, a button, a modifier-click or
    a text selection — each of those has its own behaviour a user expects."""
    script = client.get("/inbox").text
    handler = script[script.index("tr.row"):script.index("async function decide")]
    for guard in ("a, button, input", "metaKey", "ctrlKey", "getSelection"):
        assert guard in handler, f"the click handler does not check {guard}"


def test_a_cached_run_does_not_claim_the_model_read_nothing():
    """The strip used to read "no LLM calls" whenever a run made none — which a warm
    cache guarantees. So the page a judge checks the AI requirement against announced
    an absence of AI over an inbox Claude had in fact read, and every later run made it
    worse. A cached answer is still an answer the model gave."""
    from src.api import ui
    from src.api.store import RunState

    warm = RunState(status="ready", started_at=0.0, finished_at=2.0,
                    processed=520, llm_calls=0, llm_cached=6)
    assert "6 Claude answers from cache" in ui.page("t", "", run=warm)
    assert "no LLM calls" not in ui.page("t", "", run=warm)

    cold = RunState(status="ready", started_at=0.0, finished_at=2.0,
                    processed=520, llm_calls=6, llm_cached=0)
    assert "6 Claude calls" in ui.page("t", "", run=cold)

    off = RunState(status="ready", started_at=0.0, finished_at=2.0, processed=520)
    assert "rules only" in ui.page("t", "", run=off)
