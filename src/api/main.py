"""
OWNER: Person B.  The service: screens for the people who do the work, JSON for
anything that wants to integrate.

    uvicorn src.api.main:app --reload        # http://localhost:8000

The inbox is processed automatically when the service starts, so the product shows its
own data without anyone typing a command. `Re-run` in the header does it again.

Screens
    GET  /                     overview — what came in, what needs a person
    GET  /inbox                every email, filterable and searchable
    GET  /case/{email_id}      one case: the email, the two documents, the decision
    GET  /review               the queue of cases a person has to settle
    GET  /report               the discrepancy report

JSON / integration
    GET  /health               liveness + run state, for the load balancer
    POST /run                  process the inbox again (returns immediately)
    GET  /results              every verdict; ?status= ?category= ?limit=
    GET  /results/{email_id}   one verdict + the seven comparison rows
    GET  /review.json          the open queue with full evidence
    POST /review/{email_id}    a person confirms or corrects a verdict
    GET  /report.md            the report as Markdown
    GET  /submission.json      the file for the organizers' self-eval
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse)

from .. import config
from ..models import EmailResult, Status, build_submission
from ..report import render_report, verdict_line
from . import ui
from .store import STORE

from pydantic import BaseModel

# Where the inbox lives. Set DATA_DIR to aim the service at a different drop of
# emails; nothing else has to change.
DATA_DIR = config.data_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Process the inbox on boot, in the background, so the first page load is useful
    # and the service is still up while it works.
    import os
    if os.environ.get("SDOC_NO_AUTORUN") != "1":
        STORE.start_run(DATA_DIR)
    yield


app = FastAPI(title="SDOC — shipping document verification", version="1.0.0",
              lifespan=lifespan)


class LlmSetting(BaseModel):
    """The Claude on/off switch."""
    enabled: bool


class ReviewDecision(BaseModel):
    """What a reviewer sends back after looking at a case."""
    status: Status
    defect_fields: list[str] = []
    reviewer: str = "unknown"
    note: str | None = None


# ---------------------------------------------------------------------------
# Why nothing here is behind a password
# ---------------------------------------------------------------------------
# The submission rules require the live prototype to be publicly accessible, and the
# organizers confirmed that gating any part of it — including the actions that spend
# API credits — is not allowed. So every endpoint below is open, POST /run included.
#
# That is only safe because the spending is defended somewhere else entirely:
#
#   * every AI response is cached on disk by a hash of the request (llm_extract).
#     The six vision calls are on six files that never change, so the first run pays
#     and every run after it is free. Somebody hammering /run costs us nothing.
#   * a cumulative spend ceiling (LLM_SPEND_CAP_USD) written to disk on every call,
#     which switches the AI off by itself when reached and survives restarts.
#   * a short cooldown on /run, which throttles rather than denies: everyone can still
#     press the button, just not a thousand times a second.
#
# Limiting our own resource consumption is not the same as limiting access, and the
# distinction is the whole reason this arrangement works.
_MIN_SECONDS_BETWEEN_RUNS = 20
_last_run_at = 0.0


def _llm() -> dict[str, Any]:
    from ..extractor.llm_extract import llm_status
    return llm_status()


def _entry(result: EmailResult) -> dict[str, Any]:
    return {
        "email_id": result.email_id,
        "category": result.category.value,
        "status": result.status.value,
        "review_reason": result.review_reason.value if result.review_reason else None,
        "has_defect": result.has_defect,
        "defect_fields": result.defect_fields,
        "verdict": verdict_line(result),
        "decided_by": result.decided_by.value,
        "classified_by_rule": result.classified_by_rule,
        "resolved_by_human": result.email_id in STORE.resolutions,
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# screens
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def screen_overview() -> str:
    return ui.overview(STORE, _llm())


@app.get("/inbox", response_class=HTMLResponse)
def screen_inbox(category: str | None = None, status: str | None = None,
                 q: str | None = None, page: int = 1) -> str:
    return ui.inbox(STORE, category or None, status or None, q or None, page,
                    llm=_llm())


@app.get("/review", response_class=HTMLResponse)
def screen_review() -> str:
    return ui.review_list(STORE, _llm())


@app.get("/case/{email_id}", response_class=HTMLResponse)
def screen_case(email_id: str, back: str = "/") -> HTMLResponse:
    result = STORE.result(email_id)
    if result is None:
        raise HTTPException(404, f"no result for {email_id}")
    return HTMLResponse(ui.case(STORE, result, back, _llm()))


@app.get("/report", response_class=HTMLResponse)
def screen_report() -> str:
    return ui.report_page(STORE, render_report(STORE.ordered()), _llm())


@app.get("/attachment/{path:path}")
def attachment(path: str) -> Response:
    """Serve the SI or BL itself, so a reviewer can check our reading against the source.

    "Escalate with the source evidence" means the evidence has to be reachable. Text
    documents render in the browser; pdf/xlsx/docx download. Confined to the data
    directory — a path that resolves outside it is a 404, not a file.
    """
    root = (Path(DATA_DIR) / "attachments").resolve()
    target = (root / Path(path).name).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, f"no such attachment: {path}")
    if target.suffix.lower() == ".txt":
        return PlainTextResponse(target.read_text(encoding="utf-8", errors="replace"))
    return FileResponse(target, filename=target.name)


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# json
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, Any]:
    llm = _llm()
    return {"status": "ok", "version": config.version(),
            "run": STORE.run.as_dict(), **STORE.counts(),
            "llm": "available" if llm["available"] else "rules-only",
            "llm_detail": llm}


@app.get("/settings/llm")
def get_llm_setting() -> dict[str, Any]:
    return _llm()


@app.post("/settings/llm")
def set_llm_setting(setting: LlmSetting) -> dict[str, Any]:
    """Turn the Claude fallbacks on or off, at runtime, without a redeploy.

    The rules score 1.0000 on the sample inbox without any of this, so the switch is
    off by default and the budget is only spent when somebody deliberately says so.
    The setting is written to a state file and survives a restart.
    """
    from ..extractor.llm_extract import forget_client
    config.set_llm_enabled(setting.enabled)
    forget_client()                 # next call re-reads the switch and the key
    return _llm()


@app.post("/run")
def run_pipeline(limit: int | None = None) -> dict[str, Any]:
    """Process the inbox again. Returns immediately; poll /health for progress."""
    global _last_run_at
    waited = time.time() - _last_run_at
    if waited < _MIN_SECONDS_BETWEEN_RUNS:
        raise HTTPException(429, f"a run was started {waited:.0f}s ago; "
                                 f"wait {_MIN_SECONDS_BETWEEN_RUNS - waited:.0f}s more")
    _last_run_at = time.time()
    started = STORE.start_run(DATA_DIR, limit)
    return {"started": started, "run": STORE.run.as_dict()}


@app.get("/results")
def list_results(status: str | None = None, category: str | None = None,
                 limit: int = 100) -> dict[str, Any]:
    rows = STORE.filtered(category, status)
    return {"total": len(rows), "results": [_entry(r) for r in rows[:limit]]}


@app.get("/results/{email_id}")
def get_result(email_id: str) -> dict[str, Any]:
    result = STORE.result(email_id)
    if result is None:
        raise HTTPException(404, f"no result for {email_id}")
    email = STORE.email(email_id)
    return {
        **_entry(result),
        "comparisons": [row.model_dump() for row in result.comparisons],
        "email": {"from": email.sender, "subject": email.subject,
                  "attachments": email.attachments} if email else None,
        "resolution": STORE.resolutions.get(email_id),
    }


@app.get("/review.json")
def review_queue() -> dict[str, Any]:
    """Everything the pipeline refused to decide, with the evidence to decide it.

    "Escalate to a person with the relevant context, rather than guessing or failing
    silently" — the context is the seven rows plus the label each value was read under.
    """
    queue = [{**_entry(r), "comparisons": [row.model_dump() for row in r.comparisons]}
             for r in STORE.open_reviews()]
    return {"open": len(queue), "queue": queue}


@app.post("/review/{email_id}")
def resolve_review(email_id: str, decision: ReviewDecision) -> dict[str, Any]:
    """A person confirms or corrects a verdict; the report updates immediately."""
    result = STORE.resolve(email_id, decision.status, decision.defect_fields,
                           decision.reviewer, decision.note)
    if result is None:
        raise HTTPException(404, f"no result for {email_id}")
    return {"email_id": email_id, "updated": _entry(result)}


@app.get("/report.md", response_class=PlainTextResponse)
def report_markdown() -> str:
    return render_report(STORE.ordered())


@app.get("/submission.json")
def submission() -> JSONResponse:
    return JSONResponse(build_submission(STORE.ordered()))
