#!/usr/bin/env python3
"""
Measure the pipeline, save the run, and diff two runs.

`run_self_eval.py` asks the organizers' server for a score. This does the rest of what
"Technical Feasibility & Validation" actually means: it keeps every run as an artifact,
tells you WHICH emails changed between two runs, and breaks the errors down by cause so
the next fix is obvious rather than guessed.

    # score a run (needs an answer key; it is NOT in this repo -- see below)
    python scripts/evaluate.py --ground-truth ../sdoc-server/data_v2/ground_truth.json

    # or score it through the organizers' server, which keeps the key private
    python scripts/evaluate.py --server http://localhost:8080

    # keep the result, then compare two runs email by email
    python scripts/evaluate.py --ground-truth <key> --save out/runs/rules-only.json
    python scripts/evaluate.py --compare out/runs/rules-only.json out/runs/with-llm.json

THE ANSWER KEY DOES NOT LIVE HERE. ground_truth.json is gitignored and must stay
outside the repository; pass its path with --ground-truth. The scoring formula below is
the organizers' published one:

    final = 0.30*stage1_macro_f1 + 0.20*stage3_defect_f1 + 0.50*end_to_end

WHAT THE WEIGHTS MEAN IN PRACTICE, on this dataset (46 defect emails, 200 comparable):
  * end-to-end demands the EXACT set of defect fields. 26 of the 46 defect emails have
    two fields; flagging one of the two scores zero there. There is no partial credit.
  * a missed defect costs ~1.31% of the final score, a false alarm ~0.22%. Recall is
    worth about six times precision -- when in doubt, flag.
  * stage-1 macro-F1 weighs the five categories EQUALLY, so the 40 SPAM emails matter
    as much as the 220 comparison ones.
  * status / review_reason are NOT read by any scored axis. They only move the
    reliability numbers, which are reported separately and not part of the final score.
    That is not a reason to get them wrong -- it is the axis a human judge reads.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import Category, Status  # noqa: E402

CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
WEIGHTS = {"stage1": 0.30, "stage3": 0.20, "end_to_end": 0.50}


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------
def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def score(truth: dict, sub: dict) -> dict:
    """The organizers' formula, reimplemented so a run can be scored offline."""
    per = {c: {"tp": 0, "fp": 0, "fn": 0} for c in CATEGORIES}
    confusion: dict[str, Counter] = defaultdict(Counter)
    correct = rule_hits = rule_total = 0

    for eid, t in truth.items():
        actual, pred = t["category"], sub.get(eid, {}).get("category", "GENERAL")
        confusion[actual][pred] += 1
        if pred == actual:
            correct += 1
            per[actual]["tp"] += 1
        else:
            per[actual]["fn"] += 1
            if pred in per:
                per[pred]["fp"] += 1
        if sub.get(eid, {}).get("decided_by") is not None:
            rule_total += 1
            rule_hits += sub[eid]["decided_by"] == "rule"

    macro_f1 = sum(prf(**per[c])[2] for c in CATEGORIES) / len(CATEGORIES)

    tp = fp = fn = exact = doc_total = 0
    for eid, t in truth.items():
        if t["category"] != "BL_COMPARISON" or t.get("status") == "NEEDS_REVIEW":
            continue
        doc_total += 1
        s = sub.get(eid, {})
        routed = s.get("category") == "BL_COMPARISON"
        pred_defect = bool(s.get("has_defect")) and routed
        pred_fields = set(s.get("defect_fields", [])) if routed else set()
        if t["has_defect"] and pred_defect:
            tp += 1
        elif t["has_defect"]:
            fn += 1
        elif pred_defect:
            fp += 1
        exact += pred_fields == set(t["defect_fields"])
    dp, dr, df = prf(tp, fp, fn)

    e2e_total = e2e_ok = 0
    for eid, t in truth.items():
        if not (t["category"] == "BL_COMPARISON" and t.get("has_defect")):
            continue
        e2e_total += 1
        s = sub.get(eid, {})
        e2e_ok += (s.get("category") == "BL_COMPARISON" and bool(s.get("has_defect"))
                   and set(s.get("defect_fields", [])) == set(t["defect_fields"]))

    gold_review = sum(1 for t in truth.values() if t.get("status") == "NEEDS_REVIEW")
    pred_review = sum(1 for s in sub.values() if s.get("status") == "NEEDS_REVIEW")
    esc_ok = sum(1 for eid, t in truth.items()
                 if t.get("status") == "NEEDS_REVIEW"
                 and sub.get(eid, {}).get("status") == "NEEDS_REVIEW")

    e2e_rate = e2e_ok / e2e_total if e2e_total else 0.0
    return {
        "final_score": (WEIGHTS["stage1"] * macro_f1 + WEIGHTS["stage3"] * df
                        + WEIGHTS["end_to_end"] * e2e_rate),
        "stage1": {"accuracy": correct / len(truth), "macro_f1": macro_f1,
                   "per": {c: dict(zip(("precision", "recall", "f1"), prf(**per[c])))
                           for c in CATEGORIES},
                   "confusion": {a: dict(d) for a, d in confusion.items()},
                   "rule_pct": rule_hits / rule_total if rule_total else None},
        "stage3": {"defect_precision": dp, "defect_recall": dr, "defect_f1": df,
                   "exact_match_rate": exact / doc_total if doc_total else 0.0,
                   "doc_total": doc_total},
        "end_to_end": {"success": e2e_ok, "total": e2e_total, "rate": e2e_rate},
        "reliability": {
            "escalation_recall": esc_ok / gold_review if gold_review else 0.0,
            "escalation_precision": esc_ok / pred_review if pred_review else 0.0,
            "gold_review": gold_review, "pred_review": pred_review},
    }


def error_analysis(truth: dict, sub: dict) -> list[dict]:
    """Every email we got wrong, with the axis it cost us. This is the list to work
    down — not the aggregate score."""
    errors = []
    for eid, t in sorted(truth.items()):
        s = sub.get(eid, {})
        axes = []
        if s.get("category") != t["category"]:
            axes.append("stage1")
        comparable = t["category"] == "BL_COMPARISON" and t.get("status") != "NEEDS_REVIEW"
        if comparable and bool(s.get("has_defect")) != t["has_defect"]:
            axes.append("stage3")
        if (t["category"] == "BL_COMPARISON" and t.get("has_defect")
                and set(s.get("defect_fields", [])) != set(t["defect_fields"])):
            axes.append("end_to_end")
        if (t.get("status") == "NEEDS_REVIEW") != (s.get("status") == "NEEDS_REVIEW"):
            axes.append("reliability")
        if axes:
            errors.append({
                "email_id": eid, "costs": axes,
                "gold": {"category": t["category"], "status": t.get("status"),
                         "defect_fields": t["defect_fields"]},
                "ours": {"category": s.get("category"), "status": s.get("status"),
                         "defect_fields": s.get("defect_fields", [])},
            })
    return errors


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def bar(x: float, width: int = 24) -> str:
    return "█" * int(round(x * width)) + "·" * (width - int(round(x * width)))


def print_scoreboard(r: dict) -> None:
    s1, s3, e2e, rel = r["stage1"], r["stage3"], r["end_to_end"], r["reliability"]
    print(f"\nFINAL SCORE  {r['final_score']:.4f}\n")
    print(f"  stage1 macro-F1    {s1['macro_f1']:.4f}  {bar(s1['macro_f1'])}  (30%)")
    print(f"  stage3 defect-F1   {s3['defect_f1']:.4f}  {bar(s3['defect_f1'])}  (20%)")
    print(f"  end-to-end         {e2e['rate']:.4f}  {bar(e2e['rate'])}  (50%)  "
          f"{e2e['success']}/{e2e['total']}")
    if s1.get("rule_pct") is not None:
        print(f"\n  resolved by rules  {s1['rule_pct']:.0%}")
    print(f"  escalation         recall {rel['escalation_recall']:.3f} / "
          f"precision {rel['escalation_precision']:.3f}   "
          f"(flagged {rel['pred_review']}, truly need it {rel['gold_review']})")
    wrong = {a: {p: n for p, n in d.items() if p != a}
             for a, d in s1["confusion"].items()}
    wrong = {a: d for a, d in wrong.items() if d}
    if wrong:
        print("\n  misclassified (actual -> predicted):")
        for actual, preds in sorted(wrong.items()):
            print(f"    {actual:<16} {preds}")


def print_errors(errors: list[dict], limit: int = 25) -> None:
    if not errors:
        print("\nno errors on any axis.")
        return
    by_axis = Counter(axis for e in errors for axis in e["costs"])
    print(f"\n{len(errors)} emails wrong — by axis: {dict(by_axis)}")
    for e in errors[:limit]:
        print(f"  {e['email_id']}  costs {'+'.join(e['costs'])}")
        print(f"     gold {e['gold']['category']}/{e['gold']['status']}/{e['gold']['defect_fields']}")
        print(f"     ours {e['ours']['category']}/{e['ours']['status']}/{e['ours']['defect_fields']}")
    if len(errors) > limit:
        print(f"  ... and {len(errors) - limit} more")


def compare_runs(a_path: Path, b_path: Path) -> None:
    a, b = json.loads(a_path.read_text()), json.loads(b_path.read_text())
    fa, fb = a["score"]["final_score"], b["score"]["final_score"]
    print(f"\n{a['name']}  {fa:.4f}")
    print(f"{b['name']}  {fb:.4f}")
    print(f"delta      {fb - fa:+.4f}\n")
    for axis, get in (("stage1 macro-F1", lambda r: r["score"]["stage1"]["macro_f1"]),
                      ("stage3 defect-F1", lambda r: r["score"]["stage3"]["defect_f1"]),
                      ("end-to-end", lambda r: r["score"]["end_to_end"]["rate"]),
                      ("escalation recall", lambda r: r["score"]["reliability"]["escalation_recall"]),
                      ("escalation precision", lambda r: r["score"]["reliability"]["escalation_precision"])):
        print(f"  {axis:<22} {get(a):.4f} -> {get(b):.4f}  ({get(b) - get(a):+.4f})")

    ea = {e["email_id"] for e in a.get("errors", [])}
    eb = {e["email_id"] for e in b.get("errors", [])}
    if ea - eb:
        print(f"\n  fixed ({len(ea - eb)}): {sorted(ea - eb)[:15]}")
    if eb - ea:
        print(f"  BROKEN ({len(eb - ea)}): {sorted(eb - ea)[:15]}")
    if not (ea ^ eb):
        print("\n  the same emails are wrong in both runs")


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ground-truth", help="path to the answer key (kept OUTSIDE this repo)")
    ap.add_argument("--server", help="score through the organizers' server instead")
    ap.add_argument("--submission", default="submission.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--run", action="store_true", help="run the pipeline first")
    ap.add_argument("--name", default=None, help="label for the saved run")
    ap.add_argument("--save", default=None, help="write the run artifact here")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="diff two saved runs")
    ap.add_argument("--errors", type=int, default=25, help="how many errors to list")
    args = ap.parse_args(argv)

    if args.compare:
        compare_runs(Path(args.compare[0]), Path(args.compare[1]))
        return 0

    elapsed = None
    if args.run:
        from src import pipeline, submission as submission_mod
        started = time.time()
        results = pipeline.run(args.data_dir)
        elapsed = time.time() - started
        submission_mod.save(results, args.submission, args.data_dir)
        print(f"pipeline: {len(results)} emails in {elapsed:.1f}s "
              f"({len(results) / elapsed:.0f}/s)")

    sub_path = Path(args.submission)
    if not sub_path.exists():
        print(f"{sub_path} not found — run `python -m src.pipeline` first", file=sys.stderr)
        return 1
    sub = json.loads(sub_path.read_text())

    if args.server:
        request = urllib.request.Request(
            args.server.rstrip("/") + "/submit", data=json.dumps(sub).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                board = json.loads(response.read())
        except urllib.error.URLError as exc:
            print(f"could not reach {args.server}: {exc}", file=sys.stderr)
            return 1
        print_scoreboard(board)
        errors = []
        result = board
    elif args.ground_truth:
        truth = json.loads(Path(args.ground_truth).read_text())
        result = score(truth, sub)
        errors = error_analysis(truth, sub)
        print_scoreboard(result)
        print_errors(errors, args.errors)
    else:
        print("give me --ground-truth <path> or --server <url> (or --compare A B)",
              file=sys.stderr)
        return 1

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "name": args.name or out.stem,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seconds": elapsed,
            "score": result,
            "errors": errors,
        }, indent=2), encoding="utf-8")
        print(f"\nrun saved -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
