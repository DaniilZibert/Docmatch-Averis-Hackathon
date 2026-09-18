#!/usr/bin/env python3
"""
Score submission.json against the organizers' self-eval server.

Prerequisite: the organizers' docker bundle is running.

    unzip sdoc-hackathon-docker.zip -d sdoc-server
    cd sdoc-server && docker compose up --build       # serves http://localhost:8080

Then:

    python scripts/run_self_eval.py                    # scores ./submission.json
    python scripts/run_self_eval.py --url http://localhost:8080 --submission out.json

The server holds the answer key privately and never returns it — it just grades us.
That is the only measurement we should be using; the key itself does not belong in
this repository.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://localhost:8080"


def submit(submission: dict, url: str) -> dict:
    request = urllib.request.Request(
        url.rstrip("/") + "/submit",
        data=json.dumps(submission).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def print_scoreboard(board: dict) -> None:
    stage1 = board.get("stage1", {})
    stage3 = board.get("stage3", {})
    e2e = board.get("end_to_end", {})
    rel = board.get("reliability", {})

    print(f"\nFINAL SCORE          {board.get('final_score', 0):.4f}\n")
    print(f"  stage1 accuracy    {stage1.get('accuracy', 0):.4f}")
    print(f"  stage1 macro-F1    {stage1.get('macro_f1', 0):.4f}   (30% of final)")
    print(f"  stage3 defect-F1   {stage3.get('defect_f1', 0):.4f}   (20% of final)")
    print(f"  stage3 field-F1    {stage3.get('field_f1', 0):.4f}")
    print(f"  end-to-end rate    {e2e.get('rate', 0):.4f}   "
          f"({e2e.get('success', 0)}/{e2e.get('total', 0)}, 50% of final)")
    print(f"\n  escalation recall     {rel.get('escalation_recall', 0):.4f}")
    print(f"  escalation precision  {rel.get('escalation_precision', 0):.4f}   "
          f"(we escalated {rel.get('pred_review', 0)}, truly needing it: {rel.get('gold_review', 0)})")

    confusion = stage1.get("confusion")
    if confusion:
        print("\n  confusion (actual -> predicted):")
        for actual, predictions in sorted(confusion.items()):
            wrong = {p: n for p, n in predictions.items() if p != actual}
            if wrong:
                print(f"    {actual:<16} {wrong}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", default="submission.json")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args(argv)

    path = Path(args.submission)
    if not path.exists():
        print(f"{path} not found — run `python -m src.pipeline` first", file=sys.stderr)
        return 1

    submission = json.loads(path.read_text(encoding="utf-8"))
    print(f"submitting {len(submission)} results to {args.url} ...")

    try:
        board = submit(submission, args.url)
    except urllib.error.URLError as exc:
        print(f"could not reach the self-eval server at {args.url}: {exc}\n"
              f"Is the organizers' `docker compose up` running?", file=sys.stderr)
        return 1

    print_scoreboard(board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
