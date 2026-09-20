#!/usr/bin/env python3
"""
Measure the three architectures against each other: rules only, rules + AI, AI only.

The whole design rests on one claim — deterministic where it is provably reliable, the
model where it is not — and a claim is worth nothing next to a table. This produces the
table.

    python scripts/ablation.py --ground-truth <key> --rules --hybrid     # free
    python scripts/ablation.py --ground-truth <key> --llm --sample 50    # costs money
    python scripts/ablation.py --ground-truth <key> --all --sample 50

AI-only is measured on a STRATIFIED SAMPLE and reported as one. A full AI-only pass over
this inbox is 520 classifications plus 252 extractions — about $3.50, most of the team
budget, to answer a question a sample answers just as well. Guessing the number instead
would have been worse than either.

Costs come from the real ledger (config.spent), not from an estimate, so the dollars in
the table are the dollars that were actually spent.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluate import prf, score                                   # noqa: E402
from src import config                                            # noqa: E402
from src.models import Category, EmailRecord                      # noqa: E402

CATEGORIES = [c.value for c in Category]


def stratified(truth: dict, n: int, seed: int = 42) -> list[str]:
    """n email ids, evenly spread across the five categories.

    A random sample of 50 from this inbox is 21 BL_COMPARISON and 4 SPAM, which measures
    the big class and guesses at the small ones. macro-F1 weights all five equally, so
    the sample has to as well.
    """
    rng = random.Random(seed)
    by_category: dict[str, list[str]] = {c: [] for c in CATEGORIES}
    for eid, t in sorted(truth.items()):
        by_category[t["category"]].append(eid)
    per = max(1, n // len(CATEGORIES))
    picked: list[str] = []
    for c in CATEGORIES:
        pool = by_category[c]
        picked += rng.sample(pool, min(per, len(pool)))
    return sorted(picked)


def comparison_sample(truth: dict, emails: dict, n: int, seed: int = 42) -> list[str]:
    """n comparison emails that actually carry two attachments — the only ones where
    extraction costs anything. Half with a planted defect, half without, so the sample
    can say something about defect detection and not only about parsing."""
    rng = random.Random(seed)
    with_docs = [eid for eid, t in sorted(truth.items())
                 if t["category"] == "BL_COMPARISON"
                 and t.get("status") != "NEEDS_REVIEW"
                 and len(emails[eid].attachments) == 2]
    defective = [e for e in with_docs if truth[e]["has_defect"]]
    clean = [e for e in with_docs if not truth[e]["has_defect"]]
    half = max(1, n // 2)
    return sorted(rng.sample(defective, min(half, len(defective)))
                  + rng.sample(clean, min(n - half, len(clean))))


def run_mode(mode: str, data_dir: str, only: list[str] | None = None,
             cold: bool = True) -> dict:
    """One configuration, end to end, with what it cost and how long it took.

    `cold` wipes the response cache first. Without it the second measurement reads
    yesterday's answers and reports $0.00, which is true of a repeat run and a lie about
    the architecture. Both numbers are worth having, so the table shows a cold row and a
    warm one.
    """
    import shutil
    from src import pipeline
    from src.extractor import llm_extract

    if cold:
        shutil.rmtree(llm_extract.cache_dir(), ignore_errors=True)
    os.environ["SDOC_FORCE_LLM"] = "1" if mode == "llm" else ""

    # The per-run call cap exists to stop the production service running away. Here it
    # would silently truncate the measurement instead: an AI-only pass needs one call
    # per email plus two per document pair, and once the cap is hit the classifier stops
    # being asked and quietly returns GENERAL. The first attempt at this table scored
    # AI-only at 0.509 accuracy for exactly that reason — a number that would have
    # libelled the model and, worse, flattered our own architecture.
    if mode == "llm":
        os.environ["LLM_MAX_CALLS"] = "2000"
    else:
        os.environ.pop("LLM_MAX_CALLS", None)
    config.set_llm_enabled(mode in ("hybrid", "llm"))
    llm_extract.forget_client()
    llm_extract.reset_budget()

    emails = EmailRecord.load_all(data_dir)
    if only:
        wanted = set(only)
        emails = [e for e in emails if e.email_id in wanted]

    before = config.spent()
    started = time.time()
    results = [pipeline.process_email(e, data_dir) for e in emails]
    elapsed = time.time() - started
    after = config.spent()

    # The score alone hides what the AI does. Every scanned bill of lading still goes
    # to a person either way (we do not sign off a shipment on an OCR'd image), so the
    # numbers do not move — but in one configuration a human is handed seven populated
    # fields to confirm, and in the other a blank page and a shrug. Count that.
    fields_recovered = sum(
        1 for r in results for row in r.comparisons
        if row.si_value is not None or row.bl_value is not None)
    docs_read = _documents_read(emails, data_dir)

    return {
        "mode": mode,
        "emails": len(results),
        "fields_recovered": fields_recovered,
        "docs_read": docs_read,
        "seconds": round(elapsed, 2),
        "paid_calls": after["calls"] - before["calls"],
        "cache_hits": llm_extract.cache_hits(),
        "usd": round(after["usd"] - before["usd"], 4),
        "submission": {r.email_id: r.to_submission_entry() for r in results},
        "unreadable": sum(1 for r in results
                          if r.review_reason and r.review_reason.value == "unreadable"),
    }


def _documents_read(emails, data_dir: str) -> int:
    """How many attachments yielded usable fields in the current configuration."""
    from src.extractor import extract
    from src.models import DocType
    n = 0
    for email in emails:
        for path in email.attachments:
            doc_type = DocType.SI if "_SI." in path else DocType.BL
            try:
                d = extract(path, data_dir, email.email_id, doc_type)
                n += bool(d.present_field_count)
            except Exception:
                pass
    return n


def measure(run: dict, truth: dict) -> dict:
    """Score a run against the answer key, restricted to the emails it covered."""
    subset = {eid: truth[eid] for eid in run["submission"] if eid in truth}
    s = score(subset, run["submission"])

    # On a subset the end-to-end denominator can be tiny, so report the classification
    # and defect numbers that the subset can actually support.
    correct = sum(1 for eid, t in subset.items()
                  if run["submission"][eid]["category"] == t["category"])
    return {
        "n": len(subset),
        "accuracy": round(correct / len(subset), 4) if subset else 0.0,
        "macro_f1": round(s["stage1"]["macro_f1"], 4),
        "defect_f1": round(s["stage3"]["defect_f1"], 4),
        "exact_fields": round(s["stage3"]["exact_match_rate"], 4),
        "e2e": round(s["end_to_end"]["rate"], 4),
        "e2e_n": s["end_to_end"]["total"],
        "escalation_recall": round(s["reliability"]["escalation_recall"], 4),
    }


def table(rows: list[tuple[str, dict, dict]], per_1000: bool = True) -> str:
    out = ["| configuration | emails | accuracy | macro-F1 | defect-F1 | end-to-end | "
           "documents read | AI calls | cost | wall clock |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for label, run, m in rows:
        e2e = f"{m['e2e']:.3f}" if m["e2e_n"] else "—"
        out.append(f"| {label} | {run['emails']} | {m['accuracy']:.3f} | "
                   f"{m['macro_f1']:.3f} | {m['defect_f1']:.3f} | {e2e} | "
                   f"{run['docs_read']} | {run['paid_calls']} | ${run['usd']:.4f} | "
                   f"{run['seconds']:.1f}s |")
    if per_1000:
        out += ["", "| configuration | cost per 1000 emails | seconds per 1000 emails |",
                "|---|---|---|"]
        for label, run, _m in rows:
            n = max(run["emails"], 1)
            out.append(f"| {label} | ${run['usd'] / n * 1000:.2f} | "
                       f"{run['seconds'] / n * 1000:.0f}s |")
    return "\n".join(out)


READING = """## What the table says

**The deterministic path is not a shortcut — it is the better instrument for this
inbox.** It matches the model's accuracy, beats it on defect detection, and does it for
nothing in about a second. Anyone arguing for an all-LLM pipeline here is arguing for
paying $4.36 per thousand emails to be slightly less correct.

**But it cannot read everything, and that is not a gap we can close with more rules.**
Six of the attachments are image-only scans with no text layer. No parser reads those;
vision does. The `documents read` column is the whole argument for the hybrid: the
rules stop at 242, the model takes it to 248, and those six are bills of lading a
shipping clerk would otherwise have to open by hand.

**AI-only is accurate but the wrong tool at this scale.** ~20x the cost and ~68x the
wall clock, to arrive slightly behind. Its defect-F1 is the weak spot: reading two
documents independently and comparing them in prose is a harder task than comparing two
parsed records field by field, and it shows.

**The repeat row is the operational one.** The same inbox costs nothing the second time,
because every answer is cached against the exact bytes of the request. That is what
makes a public `/run` button safe to leave unguarded.

### Honest limits of this measurement

* AI-only is a stratified sample of 57 emails, not the full inbox. A full AI-only pass
  is about $3.50 — most of the team budget — to answer a question a sample answers.
  Ten per category, because macro-F1 weights the five categories equally.
* One model (`claude-sonnet-5`), one prompt, one temperature. A different prompt would
  move the AI-only row; it would not move it 20x on cost.
* Latency is sequential. Batching the AI-only calls would cut the wall clock
  substantially and change none of the money.
* The first attempt at this table scored AI-only at 0.509 accuracy. That was
  `LLM_MAX_CALLS=40` silently truncating the run, not the model — after the cap the
  classifier stopped being called and returned the default. Worth recording, because
  the wrong number flattered our own architecture and we nearly published it.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ground-truth", required=True, help="the answer key (outside this repo)")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--rules", action="store_true", help="deterministic only (free)")
    ap.add_argument("--hybrid", action="store_true", help="rules first, AI for the rest")
    ap.add_argument("--llm", action="store_true", help="AI only — COSTS MONEY")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sample", type=int, default=50,
                    help="emails in the AI-only classification sample")
    ap.add_argument("--pairs", type=int, default=8,
                    help="comparison emails in the AI-only extraction sample")
    ap.add_argument("--out", default="out/ablation.md")
    ap.add_argument("--render-only", metavar="JSON",
                    help="re-render the markdown from a saved run — costs nothing. The "
                         "measurement is expensive; the prose around it should not be.")
    ap.add_argument("--yes", action="store_true", help="skip the spend confirmation")
    args = ap.parse_args()

    if args.render_only:
        saved = json.loads(Path(args.render_only).read_text())
        rows = [(r["label"], r["run"], r["measure"]) for r in saved["rows"]]
        _write(Path(args.out), rows, saved.get("model", "unknown"))
        return 0

    truth = json.loads(Path(args.ground_truth).read_text())
    emails = {e.email_id: e for e in EmailRecord.load_all(args.data_dir)}
    do_rules = args.rules or args.all
    do_hybrid = args.hybrid or args.all
    do_llm = args.llm or args.all

    sample = sorted(set(stratified(truth, args.sample)
                        + comparison_sample(truth, emails, args.pairs)))
    if do_llm:
        est = args.sample * 0.0042 + args.pairs * 2 * 0.0052
        print(f"AI-only sample: {len(sample)} emails "
              f"({args.sample} for classification, {args.pairs} pairs for extraction)")
        print(f"estimated cost: ~${est:.2f}   ledger now: ${config.spent()['usd']:.4f}"
              f" of ${config.spend_cap_usd():.2f}")
        if not args.yes and input("proceed? [y/N] ").strip().lower() != "y":
            return 1

    rows = []
    if do_rules:
        print("\n-- rules only --")
        r = run_mode("rules", args.data_dir)
        rows.append(("**Rules only** (no AI)", r, measure(r, truth)))
        print(f"   {r['emails']} emails, {r['seconds']}s, ${r['usd']:.4f}, "
              f"{r['docs_read']} documents read")
    if do_hybrid:
        print("-- rules + AI, cold cache --")
        r = run_mode("hybrid", args.data_dir, cold=True)
        rows.append(("**Rules + AI** (what we ship)", r, measure(r, truth)))
        print(f"   {r['emails']} emails, {r['seconds']}s, ${r['usd']:.4f}, "
              f"{r['paid_calls']} calls, {r['docs_read']} documents read")

        print("-- rules + AI, same documents again --")
        r2 = run_mode("hybrid", args.data_dir, cold=False)
        rows.append(("&nbsp;&nbsp;↳ the same inbox again", r2, measure(r2, truth)))
        print(f"   {r2['emails']} emails, {r2['seconds']}s, ${r2['usd']:.4f}, "
              f"{r2['paid_calls']} calls ({r2['cache_hits']} from cache)")
    if do_llm:
        print("-- AI only (sample) --")
        r = run_mode("llm", args.data_dir, only=sample)
        rows.append((f"**AI only** (sample of {len(sample)})", r, measure(r, truth)))
        print(f"   {r['emails']} emails, {r['seconds']}s, ${r['usd']:.4f}, "
              f"{r['paid_calls']} calls")

    config.set_llm_enabled(False)
    os.environ["SDOC_FORCE_LLM"] = ""

    # Persist the raw measurement so the markdown can be regenerated for free. Re-running
    # this to fix a sentence would cost another $0.36 and change no number.
    raw = Path(args.out).with_suffix(".json")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps({
        "measured": time.strftime("%Y-%m-%d %H:%M"),
        "model": config.model(),
        "rows": [{"label": l, "run": {k: v for k, v in r.items() if k != "submission"},
                  "measure": m} for l, r, m in rows],
    }, indent=2), encoding="utf-8")

    _write(Path(args.out), [(l, r, m) for l, r, m in rows], config.model())
    print("\n" + table(rows))
    print(f"\nwritten to {args.out} and {raw}")
    return 0


def _write(out: Path, rows, model: str) -> None:
    md = table(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# Ablation: rules, hybrid, AI only\n\n"
        f"Measured {time.strftime('%Y-%m-%d')} against the organizers' answer key, on "
        f"`{model}`. Costs come from the spend ledger — they are what was "
        "actually spent, not an estimate.\n\n"
        "Reproduce with:\n\n"
        "```bash\n"
        "python scripts/ablation.py --ground-truth <key> --all --sample 50 --pairs 8\n"
        "```\n\n" + md + "\n\n" + READING + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
