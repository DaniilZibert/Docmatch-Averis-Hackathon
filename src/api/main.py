"""
OWNER: Person B.  STUB — the FastAPI service.

Endpoints to build (see docs/hackathon-tasks.md, days 2-3):

    POST /run                  run the pipeline over the whole inbox, store results
    GET  /results              every verdict, filterable by status
    GET  /results/{email_id}   one verdict + the 7 side-by-side comparison rows
    GET  /review               the open human-review queue
    POST /review/{email_id}    a human confirms or corrects a verdict
    GET  /submission.json      the file for the organizers' self-eval
    GET  /health               liveness, for the EC2 deployment

Run locally:  uvicorn src.api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="SDOC — shipping document verification", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# TODO(Person B): the endpoints above.
