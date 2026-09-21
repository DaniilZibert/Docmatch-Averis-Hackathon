# CLAUDE.md — read this first

> **Joining the project to work on the submission (video, deck, description) rather than
> on the code? Read [docs/HANDOFF.md](docs/HANDOFF.md) instead — it is self-contained and
> has every number you need.** This file is for changing code.


Instructions for anyone, human or Claude, working on this code. **What the project is,
the rules, and every trap in the data.**

Three other documents, and they do not overlap with this one:

| | |
|---|---|
| [README.md](README.md) | what the thing is and how to run it |
| [docs/PLAN.md](docs/PLAN.md) | what is done, what is left, who does which |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | the server, the domain, CI/CD, the AI switch |

Hackathon **18–22 September**. Repo: `gitlab.com/daniilz2018/averis-hackaton`.
Live: <https://docmatch.tech>.

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

## 3. Before you change anything

The pipeline is complete and scores 1.0000. Nothing is waiting to be implemented, so do
not start by building something that exists — run it first.

```bash
pip install -r requirements.txt
pytest -q                       # 236 tests, no network, no spend
python -m src.pipeline          # 520 emails -> submission.json, ~1.3s, no LLM calls
uvicorn src.api.main:app --reload    # then open http://localhost:8000
```

1. **`pytest -q`.** 236 tests. If your change reddens one, the test is usually right.
2. **`./scripts/check_robustness.sh <path to data_v2>`** after any change to the rules.
   The sample inbox is one draw from a generator; this scores you on fresh ones. It is
   what caught a bug that a code review had missed.
3. **Read §5 before "fixing" anything in the extractors.** Several things there look
   like bugs and are deliberate: the address lines that are ignored, the PDF container
   table that is skipped, the blank tokens that are not values.
4. **Every open case must offer a decision.** If the pipeline escalated it, a person
   has been asked to act, so the case screen owes them something to act on — including
   the escalations that have no documents and therefore no comparison rows. Keying the
   buttons off `result.comparisons` alone is how five cases came to sit in the queue
   showing "Nothing to decide on this one". And anything labelled "leave open" must not
   call `store.resolve()`: recording a resolution is what takes a case *out* of the
   queue.

### Layout

```
src/
  models.py                THE CONTRACT — changing it affects both work streams
  pipeline.py              classify -> extract -> compare -> submission.json
  config.py                .env, the AI switch, the call budget — the only env reader
  classifier.py            template rules + Claude fallback + expects_attachments()
  normalize.py             blanks, numbers, conservative text matching
  comparator.py            the five-step decision order
  report.py                the discrepancy report
  submission.py            assembly + shape and value validation
  extractor/
    _common.py             pairs -> ExtractedDocument, and the rules->Claude handoff
    field_aliases.py       labels, document-type detection, glyph-collision recovery
    txt/xlsx/docx/pdf_extractor.py     one per format
    llm_extract.py         Claude text/vision/classify — returns None, never raises
  api/
    main.py                routes: five screens + the JSON API
    store.py               state + the run, started automatically on boot
    ui.py                  the screens, server-rendered, no build step
    uploads.py             /upload — one SI/BL pair, or a whole inbox as a zip
scripts/
  evaluate.py              score a run, save it, diff two runs, error analysis
  check_robustness.sh      score against freshly generated, never-seen inboxes
  llm_smoke.py             prove the Claude paths work (costs a few cents)
  run_self_eval.py         POST submission.json to the organizers' server
tests/                     236 tests
```

### Testing one half without the other

```python
from src.models import ExtractedDocument, DocType
from src.comparator import compare
si = ExtractedDocument.fake("email_1", DocType.SI, container_count=3)
bl = ExtractedDocument.fake("email_1", DocType.BL, container_count=4)
compare(si, bl)   # MISMATCH, defect_fields == ["container_count"]
```

### Running against a different inbox

One variable, no code change:

```bash
python -m src.pipeline --data-dir /path/to/new-inbox
DATA_DIR=/path/to/new-inbox uvicorn src.api.main:app
```

The folder needs `inbox/email_*.json` and `attachments/` shaped like `data/`.

### The API key is not in the repo

`.env` is gitignored and stays that way. Ask the other person for the key and put it in
your own `.env` (copy `.env.example`). Without it everything still runs — rules only,
with `AI no key` in the header — so a missing key is never why something is broken.

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

## 6. Who does what

See **[docs/PLAN.md](docs/PLAN.md)** — it has the current split, the priorities and the
file ownership. In short: Person A is Daniil, Person B is Nikita, the remaining work is
all rubric work rather than pipeline work.

---

## 7. Git workflow

Branch per person, merge into `main` at the end of each day. **Pushing to `main`
deploys to <https://docmatch.tech>** — the tests gate it, but it does go live.

```bash
git checkout -b feature/<what-you-are-doing>
```

Commit in small pieces with a message that says what changed and why. If you touched
`src/models.py`, say so in the first line — that is the one change the other person
must know about immediately.
