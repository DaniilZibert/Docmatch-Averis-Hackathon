# CLAUDE.md — read this first

Instructions for any Claude session working in this repository. Two people work here in
parallel, each with their own Claude, so this file is the shared brain: what the project
is, what is already done, who owns which files, and the rules.

Hackathon runs **18–22 September**. Team repo: `gitlab.com/daniilz2018/averis-hackaton`.

---

## 1. What we are building

A shipping operations team gets everything in one inbox: requests to check documents,
requests to prepare new shipping instructions, invoice questions, general chatter, spam.
For a document-check request, a human today compares a **Shipping Instruction (SI)** —
the reference — against a **draft Bill of Lading (BL)**, to catch wrong details before
the BL is finalized.

We automate that. For each of the 520 emails in `data/inbox/` the pipeline decides:

1. **category** — `BL_COMPARISON` | `SI_REQUEST` | `INVOICE_QUERY` | `GENERAL` | `SPAM`
2. for `BL_COMPARISON` only, compare SI against BL on **7 fields**:
   `shipper`, `consignee`, `notify_party`, `port_of_loading`, `port_of_discharge`,
   `container_count`, `gross_weight_kg`
3. **status** — `OK` (all 7 match) | `MISMATCH` (+ `defect_fields`) | `NEEDS_REVIEW`
   (+ `review_reason`: `wrong_doc_type` | `missing_attachment` | `unreadable` | `missing_value`)

The catch the use case is built around: **the SI and the BL label the same field
differently** — "Port of Loading" vs "Load Port", "Consignee" vs "To the Order of".
Align by meaning, never by header text. All label knowledge lives in
`src/extractor/field_aliases.py` — add to that file, never hardcode labels elsewhere.

Output goes to `submission.json`, keyed by `email_id`, in the shape of
`data/sample_submission.json`.

---

## 2. Hard rules

- **`src/models.py` is the contract between the two work streams.** Changing it can
  silently break the other person's code. Change it only when necessary, and say so in
  the commit message plus a message to the other person.
- **Never invent a field value.** If a document does not state something, the value is
  `None` and the case escalates to `NEEDS_REVIEW`. A guessed value turns an honest
  escalation into a wrong answer and costs points on two scoring axes at once.
- **Never commit `ground_truth.json`.** The organizers' answer key is not part of this
  repo (it is gitignored). Pass its path to `scripts/evaluate.py`, or measure through
  the self-eval server.
- **Never commit `.env` or API keys.** Copy `.env.example` to `.env` locally.
- **Everything degrades, nothing raises.** No API key, no network, a corrupt file, a
  missing library — each of those produces an honest `NEEDS_REVIEW`, never a crash. A
  demo has to survive a dead network, and one bad email must never lose the other 519.
- **Rules key on TEMPLATES, never on instance values.** The dataset comes out of a
  deterministic generator; a different `--seed` changes every company name, port and
  defect placement but not the shape of a subject line or a document layout. Never
  match on a specific email_id, customer name or booking number.

---

## 3. Current state — the pipeline is complete and scores 1.0000

```bash
pip install -r requirements.txt
cp .env.example .env            # optional; see below
pytest -q                       # 176 tests, no network, no spend
python -m src.pipeline          # 520 emails -> submission.json, ~1s, no LLM calls
```

Against the organizers' scorer (`score_cli.py`), rules-only, zero API calls:

```
stage1 macro-F1      1.0000    (30% of the final score)
stage3 defect-F1     1.0000    (20%)
end-to-end           1.0000    (50%)   46/46 defect emails caught
escalation           recall 1.000 / precision 1.000   (flagged 20, gold 20)
resolved by rules    100%
FINAL SCORE          1.0000
```

**And 1.0000 on data it has never seen.** The judges may score us on a different draw,
so the same pipeline was run against six freshly generated inboxes (`--seed` 3, 7, 42,
1234, 20260920, 99999 — 1,590 emails in total): 1.0000 on every one, every defect caught
with the exact field set, 20/20 escalations with no false alarms. Reproduce it with
`./scripts/check_robustness.sh <path to data_v2>`. That exercise is what found the
case-collision bug fixed in field_aliases — run it after any change to the rules.

### The API key

`.env` holds the team key and is gitignored — it stays on our machines, and judges
running this repo get the deterministic path. `src/config.py` loads it; nothing else
reads `os.environ`.

  * `LLM_MAX_CALLS` (default 40) caps Claude calls per process. The rules resolve the
    sample inbox alone, so a run that reaches the cap is a run against unfamiliar data;
    the cap is what stops an accidental full-inbox LLM pass from spending the budget.
    `python -m src.pipeline` prints the calls it made.
  * `pytest` never spends anything — `tests/conftest.py` switches the LLM off for the
    whole session. Keep it that way; tests must stay free, offline and deterministic.
  * `python scripts/llm_smoke.py` proves the three Claude paths work, on invented input
    the rules cannot handle. ~4 calls, a few cents. Run it before a demo.

```
CLAUDE.md                  this file
README.md
data/                      the participant bundle (520 emails, 250 attachments)
docs/use-case.pdf          the original problem statement
src/
  models.py                ✅ THE CONTRACT
  pipeline.py              ✅ classify -> extract -> compare -> submission.json
  submission.py            ✅ assembly + shape AND value validation
  classifier.py            ✅ template rules + Claude fallback + expects_attachments()
  normalize.py             ✅ blanks, numbers, conservative text matching
  comparator.py            ✅ the 5-step decision order
  report.py                ✅ the discrepancy report (the use case's deliverable)
  config.py                ✅ .env loading, model, call budget — the only env reader
  extractor/
    __init__.py            ✅ dispatcher by file extension
    _common.py             ✅ pairs -> ExtractedDocument + the rules->Claude handoff
    field_aliases.py       ✅ labels, doc-type detection, glyph-collision recovery
    txt_extractor.py       ✅ 192 files
    xlsx_extractor.py      ✅ 22 files
    docx_extractor.py      ✅ 8 files
    pdf_extractor.py       ✅ 28 files: text layer, container table, vision fallback
    llm_extract.py         ✅ Claude text/vision/classify — returns None, never raises
  db/schema.sql            ✅ the shape a real deployment persists
  api/main.py              ✅ routes: 4 screens + the JSON API
  api/store.py             ✅ state + the run, started automatically on boot
  api/ui.py                ✅ the screens (server-rendered, no build step)
scripts/
  run_self_eval.py         ✅ POST submission.json to the organizers' server
  evaluate.py              ✅ score, save a run, diff two runs, error analysis
  llm_smoke.py             ✅ prove the Claude paths work (costs a few cents)
  check_robustness.sh      ✅ score against freshly generated, never-seen inboxes
docs/deploy-aws.md         ✅ runbook: EC2 + domain + HTTPS
deploy/                    ✅ Dockerfile, local compose, prod compose + Caddy
tests/                     ✅ 176 tests, contract + every stage + API + end-to-end
```

Remaining work is judge-facing, not pipeline: see §8.

---

## 4. What the score actually rewards

Two separate scoring systems. Do not confuse them.

### The organizers' self-eval (a development instrument)

```
final = 0.30·stage1_macro_F1 + 0.20·stage3_defect_F1 + 0.50·end_to_end
```

Four things about this are not obvious and change how you work:

- **`status` and `review_reason` are not read by any scored axis.** The scorer reads
  `category`, `has_defect` and `defect_fields`, nothing else. `status` is read once, in
  the reliability block, and **reliability is not part of `final_score`** — it is
  printed separately. That is not permission to get it wrong: it is the axis a human
  judge reads, and "without creating false alarms" is the brief's own wording.
- **End-to-end demands the EXACT set of defect fields.** 26 of the 46 defect emails
  have two; flagging one of the two scores zero there. No partial credit. (`field_f1`
  gives partial credit but is diagnostic only, not part of the final.)
- **A missed defect costs ~6x a false alarm.** On this dataset: a missed defect
  ≈ −1.31% of the final (stage-3 recall *and* the 50% axis), a false alarm ≈ −0.22%
  (stage-3 precision only). When a field is readable on both sides and the values
  differ, flag it.
- **macro-F1 weighs the five categories equally.** The 40 SPAM emails are worth as much
  as the 220 comparison ones. Do not optimise the big class at the small ones' expense.

`decided_by` is an optional sixth key in each submission entry; the scorer reads it and
reports `rule_pct` ("resolved by rules"). We send it — it is the evidence for the
rules-first design.

### The judges' rubric (100 points, what actually decides the hackathon)

Technical 70 — Working Core Prototype **25**, System Design & Architecture 15,
Technology Integration 15, Technical Feasibility & Validation 15.
Product & Impact 30 — Problem Statement Understanding 10, Innovation & Solution
Approach 10, Practical Value & Potential 10.

**The self-eval score is not a differentiator.** It is saturable with rules alone, in
hours, and we have saturated it. Everything from here earns points on the rubric, not
on the scoreboard.

---

## 5. Dataset facts worth knowing

- 520 emails. BL_COMPARISON 220, SI_REQUEST 125, INVOICE_QUERY 75, GENERAL 60, SPAM 40.
- Of the 220 comparison emails: 154 clean, 46 with a real defect, 20 genuinely
  undecidable (5 each of `wrong_doc_type`, `missing_attachment`, `unreadable`,
  `missing_value`). If the pipeline escalates far more than 20, the logic is too
  cautious — `python -m src.pipeline` prints the count on every run.
- Attachments: 192 `.txt`, 28 `.pdf`, 22 `.xlsx`, 8 `.docx`.
- **An attachment is a decisive signal.** All 126 emails that carry one are
  BL_COMPARISON, and no other category ever attaches a file.
- **94 comparison emails arrive with no attachment, and 91 of them are fine.**
  "Please assist to send the draft BL … for checking asap" is a request *to* us —
  status OK, no escalation. Only the 3 that say "please compare … (attachments appear
  to have been dropped)" are `missing_attachment`. `classifier.expects_attachments()`
  draws the line. Escalating all 94 does not change the final score but drops
  escalation precision from 1.00 to 0.18.
- **Subjects are not adversarial**, contrary to what an earlier draft of this file
  said — the generator never gives one category's subject style to another. The
  difficulty is lexical overlap: "BL" appears in 64 BL_COMPARISON, 12 SI_REQUEST and 9
  GENERAL subjects; "invoice|billing" in 60 INVOICE_QUERY, 9 GENERAL and 2 SPAM. The
  worst case is `_RPA_ India HSS SD Billing Process Completed`, a GENERAL bot notice.
  Match whole templates and evaluate GENERAL before INVOICE_QUERY.
- `NET WEIGHT` appears in the documents and is **not** `gross_weight_kg`.
- The substituted attachments are a **Commercial Invoice (1), a Packing List (2) and a
  Certificate of Origin (2)** — not only certificates. The Packing List carries only
  Shipper / Consignee / Booking Ref, so a label-set heuristic misses it; detect the
  document **title** instead (`field_aliases.detect_document_kind`).
- Blank values are written as `???`, `_______`, `TBA`, `TBC`, `N/A`, `____MT` or an
  empty string. A blank is uncertainty, never a discrepancy — `normalize.is_blank()`.
- Worked example, `email_004`: SI says consignee/notify `EAST BRIGHT FZ-LLC`, BL says
  `UAB NOVAKOPA`, everything else agrees → `MISMATCH` on `consignee` and `notify_party`.
  Note the BL keeps EAST BRIGHT's *address* under the changed name: compare names only.

### Format traps, all handled — do not undo them

- **xlsx/docx**: both pack `NAME | ADDRESS` into one cell, with different separators.
  `_common.build_document` keeps the part before the pipe. Without it every xlsx/docx
  pair mismatches on shipper, consignee and notify_party.
- **PDF labels have no colon.** The renderer draws the label at x=20mm and the value at
  x=60mm, so the text layer reads `POL BUATAN, INDONESIA`. A `Label: Value` regex finds
  nothing. `field_aliases.match_label_prefix()` splits on the longest matching alias.
- **The PDF container table has a `GROSS WEIGHT (KG)` column** whose rows hold ONE
  container's weight (21,887) while the shipment total is on a separate
  `TOTAL Gross Wt (kgs):` line (131,322). Container rows are skipped by their
  `AAAA1234567` id format — not by a start/end state machine, because the table's own
  summary line uses a rotating alias and any single end-marker swallows the others.
- **Three PDFs have collided glyphs.** `Notify Party/Intermediate Consignee` overruns
  the value column and the text layer interleaves the two runs:
  `Notify Party/Intermediate ConsCigEnReIEeX`. Neither `extract_words()` nor an
  x-coordinate filter on chars separates them. `field_aliases._recover_collision()`
  subtracts the known label tail back out.
- **Six PDFs are image-only scans.** They go to Claude vision; the values are read and
  shown, and the case still goes to a human (`needs_confirmation`), because an OCR'd
  image is not evidence enough to sign off a bill of lading.

---

## 6. Who owns what

Work in your own files. The only shared files are `src/models.py`, `src/pipeline.py`
and this one — touch those deliberately, not incidentally.

**Person A — "the brains"**: `src/classifier.py`, `src/extractor/*`
**Person B — "the body"**: `src/normalize.py`, `src/comparator.py`, `src/submission.py`,
`src/report.py`, `src/db/*`, `src/api/*`, `deploy/*`, `scripts/evaluate.py`

Both sides are implemented. Either of you can test without the other:

```python
from src.models import ExtractedDocument, DocType
from src.comparator import compare
si = ExtractedDocument.fake("email_1", DocType.SI, container_count=3)
bl = ExtractedDocument.fake("email_1", DocType.BL, container_count=4)
compare(si, bl)   # MISMATCH, defect_fields == ["container_count"]
```

---

## 7. Commands

```bash
pip install -r requirements.txt

pytest -q                             # 153 tests — keep green
python -m src.pipeline                # full run -> submission.json + summary
python -m src.pipeline --limit 20     # quick pass while developing
python -m src.pipeline --report out/report.md    # + the discrepancy report
python -m src.pipeline --plain-submission        # drop decided_by, exact sample shape

uvicorn src.api.main:app --reload     # then open http://localhost:8000
                                      # it processes the inbox itself — no command needed

docker compose -f deploy/docker-compose.prod.yml up -d --build   # on a server, with HTTPS

# measurement — the answer key lives OUTSIDE this repo
python scripts/evaluate.py --ground-truth /path/to/ground_truth.json
python scripts/evaluate.py --server http://localhost:8080       # organizers' docker
python scripts/evaluate.py --ground-truth <key> --save out/runs/today.json
python scripts/evaluate.py --compare out/runs/a.json out/runs/b.json

# will it hold on data we have never seen? (rules only, free)
./scripts/check_robustness.sh /path/to/data_v2

# are the Claude paths alive? (~4 calls, a few cents)
python scripts/llm_smoke.py
python scripts/llm_smoke.py --vision      # + one scanned page
```

---

## 8. What is left, in priority order

The pipeline is done. These are rubric lines, not accuracy:

1. **Technical Feasibility & Validation (15).** `evaluate.py` saves and diffs runs and
   `check_robustness.sh` proves the six-seed result above. Still to do is the ablation
   table — rules-only vs rules+LLM vs LLM-only across accuracy, cost and latency. That
   table is the argument for the design; the rules-only column is already measured.
2. **Technology Integration (15).** All three Claude paths are verified working with a
   real key: classification of emails outside our templates, extraction from a layout
   with no aliases at all (7/7 fields, and it took the gross weight rather than the net
   one), and vision on the image-only scans. What is missing is the cost and latency
   numbers next to them.
3. **Innovation (10).** What is distinctive here and should be said out loud:
   confidence-gated escalation, the glyph de-interleaving, provenance on every value
   (`raw_label` + `source` + `confidence`), and the review screen feeding corrections
   back. Still unbuilt: mining a human's correction into a new alias so the system
   learns, and auto-drafting the reply to the carrier.
4. **Practical Value (10).** The service is deployable (`docs/deploy-aws.md`) — put it
   on a real URL before judging and walk it on a phone. Still to sketch: the real inbox
   is Outlook `.msg`, so show the ingest path (IMAP / Graph API + `.msg` parsing) and
   put throughput and cost per 1000 emails on a slide.
5. **Demo.** Three-minute script, and rehearse it with `ANTHROPIC_API_KEY` unset — the
   whole system runs rules-only and says so on `/health`. Never demo something that
   needs the network to work.

---

## 9. Git workflow

Branch per work stream, merge into `main` at the end of each day.

```bash
git checkout -b feature/pipeline-core     # Person A
git checkout -b feature/service-infra     # Person B
```

Commit in small pieces with a message that says what changed and why. If you touched
`src/models.py`, say so in the first line — that is the one change the other person
must know about immediately.
