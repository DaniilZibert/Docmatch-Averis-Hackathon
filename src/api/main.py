"""
OWNER: Person B.  The service layer and the human-review screen.

    uvicorn src.api.main:app --reload        # http://localhost:8000

Endpoints
    GET  /                     the review screen (HTML)
    GET  /health               liveness, for the deployment
    POST /run                  run the pipeline over the inbox and store the results
    GET  /results              every verdict; ?status=/?category=/?limit= to filter
    GET  /results/{email_id}   one verdict + the 7 side-by-side comparison rows
    GET  /review               the open human-review queue
    POST /review/{email_id}    a human confirms or corrects a verdict
    GET  /report               the discrepancy report (Markdown)
    GET  /submission.json      the file for the organizers' self-eval

The store is in-memory: the pipeline is a sub-second batch over 520 emails, so a
database buys nothing during the event. `src/db/schema.sql` is the same shape and is
what this swaps onto for a real inbox, where runs are incremental and the review queue
has to outlive the process.
"""

from __future__ import annotations

import html
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi import Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from ..models import Category, EmailResult, ReviewReason, Status, build_submission
from ..report import render_email, render_report, verdict_line

app = FastAPI(title="SDOC — shipping document verification", version="1.0.0")

# email_id -> EmailResult
RESULTS: dict[str, EmailResult] = {}
# email_id -> what a human decided
RESOLUTIONS: dict[str, dict[str, Any]] = {}


class ReviewDecision(BaseModel):
    """What a reviewer sends back after looking at a case."""
    status: Status
    defect_fields: list[str] = []
    reviewer: str = "unknown"
    note: str | None = None


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
        "resolved_by_human": result.email_id in RESOLUTIONS,
        "error": result.error,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    from ..extractor.llm_extract import llm_available
    return {"status": "ok", "results": len(RESULTS), "open_reviews": len(_open_reviews()),
            "llm": "available" if llm_available() else "rules-only"}


@app.post("/run")
def run_pipeline(data_dir: str = "data", limit: int | None = None) -> dict[str, Any]:
    """Process the inbox. Idempotent: it replaces the stored results."""
    from .. import pipeline
    results = pipeline.run(data_dir, limit)
    RESULTS.clear()
    RESULTS.update({r.email_id: r for r in results})
    counts: dict[str, int] = {}
    for r in results:
        counts[r.category.value] = counts.get(r.category.value, 0) + 1
    return {"processed": len(results), "categories": counts,
            "needs_review": len(_open_reviews())}


@app.get("/results")
def list_results(status: str | None = None, category: str | None = None,
                 limit: int = 100) -> dict[str, Any]:
    rows = list(RESULTS.values())
    if status:
        rows = [r for r in rows if r.status.value == status.upper()]
    if category:
        rows = [r for r in rows if r.category.value == category.upper()]
    return {"total": len(rows), "results": [_entry(r) for r in rows[:limit]]}


@app.get("/results/{email_id}")
def get_result(email_id: str) -> dict[str, Any]:
    result = RESULTS.get(email_id)
    if result is None:
        raise HTTPException(404, f"no result for {email_id} — POST /run first")
    payload = _entry(result)
    payload["comparisons"] = [row.model_dump() for row in result.comparisons]
    payload["resolution"] = RESOLUTIONS.get(email_id)
    return payload


def _open_reviews() -> list[EmailResult]:
    return [r for r in RESULTS.values()
            if r.status is Status.NEEDS_REVIEW and r.email_id not in RESOLUTIONS]


@app.get("/review")
def review_queue() -> dict[str, Any]:
    """Everything the pipeline refused to decide, with the evidence to decide it.

    "escalate to a person with the relevant context, rather than guessing or failing
    silently" — the context is the 7 rows plus the label each value was read under.
    """
    queue = []
    for result in _open_reviews():
        queue.append({
            **_entry(result),
            "comparisons": [row.model_dump() for row in result.comparisons],
        })
    return {"open": len(queue), "queue": queue}


@app.post("/review/{email_id}")
def resolve_review(email_id: str, decision: ReviewDecision) -> dict[str, Any]:
    """A human confirms or corrects a verdict; the report updates immediately."""
    result = RESULTS.get(email_id)
    if result is None:
        raise HTTPException(404, f"no result for {email_id}")

    result.status = decision.status
    result.defect_fields = sorted(decision.defect_fields)
    result.has_defect = decision.status is Status.MISMATCH
    result.review_reason = None if decision.status is not Status.NEEDS_REVIEW \
        else result.review_reason
    result.needs_human_review = decision.status is Status.NEEDS_REVIEW
    RESOLUTIONS[email_id] = decision.model_dump(mode="json")
    return {"email_id": email_id, "updated": _entry(result)}


@app.get("/report", response_class=PlainTextResponse)
def report() -> str:
    return render_report(RESULTS.values())


@app.get("/submission.json")
def submission() -> JSONResponse:
    return JSONResponse(build_submission(RESULTS.values()))


# ---------------------------------------------------------------------------
# the review screen
# ---------------------------------------------------------------------------
_STYLE = """
*{box-sizing:border-box}
body{font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;
 background:#f6f7f9;color:#15181d}
header{background:#1d2430;color:#fff;padding:18px 28px;position:sticky;top:0;z-index:5}
header h1{margin:0;font-size:17px;font-weight:600}
header p{margin:4px 0 0;opacity:.7;font-size:13px}
main{padding:24px 28px;max-width:1120px}
h2{font-size:15px;margin:28px 0 12px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:14px 18px;min-width:118px}
.card b{display:block;font-size:24px;font-weight:600}
.card span{font-size:12px;color:#697586;text-transform:uppercase;letter-spacing:.04em}
.case{background:#fff;border:1px solid #e3e6ea;border-radius:8px;margin-bottom:14px;overflow:hidden}
.case>h3{margin:0;padding:12px 18px;font-size:14px;border-bottom:1px solid #eef0f3;
 display:flex;gap:10px;align-items:center}
.tag{font-size:11px;padding:2px 8px;border-radius:99px;font-weight:600;letter-spacing:.03em}
.MISMATCH{background:#fdecec;color:#b42318}.NEEDS_REVIEW{background:#fff5e5;color:#b54708}
.OK{background:#e9f7ef;color:#067647}
.done{margin-left:auto;font-size:11px;color:#067647;font-weight:600}
.why{padding:10px 18px;color:#475467;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:7px 18px;border-top:1px solid #eef0f3;vertical-align:top}
th{color:#697586;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td.pick{width:34px;padding-right:0}
tr.bad td{background:#fef6f6}tr.bad td.f{font-weight:600;color:#b42318}
.src{color:#98a2b3;font-size:11px}
.actions{padding:12px 18px;border-top:1px solid #eef0f3;background:#fbfcfd;
 display:flex;gap:8px;align-items:center}
button{font:inherit;font-size:13px;padding:6px 14px;border-radius:6px;cursor:pointer;
 border:1px solid #cdd3da;background:#fff}
button:hover{background:#f2f4f7}
button.primary{background:#b42318;border-color:#b42318;color:#fff}
button.primary:hover{background:#96201a}
button.clean{background:#067647;border-color:#067647;color:#fff}
button.clean:hover{background:#05603a}
.hint{color:#98a2b3;font-size:12px;margin-left:auto}
.empty{color:#98a2b3;padding:20px 0}
"""

_SCRIPT = """
async function decide(id, status) {
  const box = document.getElementById('case-' + id);
  const fields = status === 'MISMATCH'
    ? [...box.querySelectorAll('input[type=checkbox]:checked')].map(c => c.value)
    : [];
  if (status === 'MISMATCH' && fields.length === 0) {
    alert('Tick the fields that actually differ, or mark the case clean.');
    return;
  }
  box.querySelectorAll('button').forEach(b => b.disabled = true);
  const r = await fetch('/review/' + id, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: status, defect_fields: fields, reviewer: 'reviewer'})
  });
  if (r.ok) { location.reload(); }
  else { alert('Could not save: ' + r.status); box.querySelectorAll('button').forEach(b => b.disabled = false); }
}
"""


def _case_html(result: EmailResult, actionable: bool = True) -> str:
    rows = []
    for row in result.comparisons:
        bad = not row.match
        note = f'<div class="src">{html.escape(row.note)}</div>' if row.note else ""
        pick = (f'<td class="pick"><input type="checkbox" value="{html.escape(row.field)}"'
                f'{" checked" if bad else ""}></td>') if actionable else ""
        rows.append(
            f'<tr{" class=bad" if bad else ""}>{pick}'
            f'<td class="f">{html.escape(row.field)}</td>'
            f"<td>{html.escape(str(row.si_value if row.si_value is not None else '—'))}</td>"
            f"<td>{html.escape(str(row.bl_value if row.bl_value is not None else '—'))}{note}</td></tr>")
    head = ('<tr><th></th><th>field</th><th>Shipping Instruction</th>'
            '<th>draft Bill of Lading</th></tr>') if actionable else            ('<tr><th>field</th><th>Shipping Instruction</th>'
            '<th>draft Bill of Lading</th></tr>')
    table = f"<table>{head}{''.join(rows)}</table>" if rows else ""

    resolved = result.email_id in RESOLUTIONS
    actions = ""
    if actionable and not resolved:
        eid = html.escape(result.email_id)
        actions = (
            '<div class="actions">'
            f"<button class=\"primary\" onclick=\"decide('{eid}','MISMATCH')\">"
            "Confirm mismatch</button>"
            f"<button class=\"clean\" onclick=\"decide('{eid}','OK')\">"
            "No mismatch</button>"
            f"<button onclick=\"decide('{eid}','NEEDS_REVIEW')\">Leave open</button>"
            '<span class="hint">tick the rows that really differ, then confirm</span>'
            "</div>")

    return (f'<div class="case" id="case-{html.escape(result.email_id)}">'
            f'<h3>{html.escape(result.email_id)}'
            f'<span class="tag {result.status.value}">{result.status.value}</span>'
            f'{"<span class=done>settled by a human</span>" if resolved else ""}</h3>'
            f'<div class="why">{html.escape(verdict_line(result))}'
            f'<div class="src">routed by {html.escape(result.classified_by_rule or "—")} '
            f'({result.decided_by.value})</div></div>{table}{actions}</div>')


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
def review_screen() -> str:
    mismatches = [r for r in RESULTS.values() if r.status is Status.MISMATCH]
    reviews = _open_reviews()
    settled = [r for r in RESULTS.values() if r.email_id in RESOLUTIONS]
    comparisons = [r for r in RESULTS.values() if r.category is Category.BL_COMPARISON]
    body = []

    if not RESULTS:
        body.append('<p class="empty">Nothing processed yet — '
                    '<code>curl -X POST localhost:8000/run</code></p>')
    else:
        body.append(
            '<div class="cards">'
            f'<div class="card"><b>{len(RESULTS)}</b><span>emails</span></div>'
            f'<div class="card"><b>{len(comparisons)}</b><span>doc checks</span></div>'
            f'<div class="card"><b>{len(mismatches)}</b><span>discrepancies</span></div>'
            f'<div class="card"><b>{len(reviews)}</b><span>need a human</span></div>'
            f'<div class="card"><b>{len(settled)}</b><span>settled</span></div>'
            '</div>')
        body.append("<h2>Needs a human</h2>")
        body.append("".join(_case_html(r) for r in reviews[:25])
                    or '<p class="empty">Nothing is waiting.</p>')
        body.append("<h2>Discrepancies</h2>")
        body.append("".join(_case_html(r) for r in mismatches[:25])
                    or '<p class="empty">No mismatch detected.</p>')

    return (f"<!doctype html><meta charset=utf-8><title>SDOC review</title>"
            f"<style>{_STYLE}</style><script>{_SCRIPT}</script>"
            f"<header><h1>Shipping document verification</h1>"
            f"<p>SI vs draft BL — discrepancies and the cases a person has to settle</p>"
            f"</header><main>{''.join(body)}</main>")
