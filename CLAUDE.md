# CLAUDE.md — read this first

Instructions for any Claude session working in this repository. Two people work here in
parallel, each with their own Claude, so this file is the shared brain: it says what the
project is, what is already done, who owns which files, and what the rules are.

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
  repo (it is gitignored). Measure with the self-eval server, not the key.
- **Never commit `.env` or API keys.** Copy `.env.example` to `.env` locally.
- Stubs return safe defaults rather than raising, so the pipeline always runs end to end.
  Keep that property — a crash in one email must never lose the other 519.

---

## 3. Current state

Step 0 is done: structure, contract, runnable glue, dataset, tests.

```
CLAUDE.md                  this file
README.md
data/                      the participant bundle (520 emails, 250 attachments)
  inbox/email_XXX.json     email records
  attachments/             SI + BL files: 192 .txt, 28 .pdf, 22 .xlsx, 8 .docx
  sample_submission.json   the required output shape
  loader.py                organizers' helper (local folder or their HTTP server)
docs/use-case.pdf          the original problem statement
src/
  models.py                ✅ THE CONTRACT — done, do not casually change
  pipeline.py              ✅ glue: classify -> extract -> compare -> submission.json
  submission.py            ✅ assembly + shape validation
  classifier.py            🔲 Person A — returns GENERAL for everything today
  extractor/
    __init__.py            ✅ dispatcher by file extension
    field_aliases.py       ✅ real label aliases harvested from the dataset
    txt_extractor.py       🔲 Person A — do this first, 192 files
    xlsx_extractor.py      🔲 Person A
    docx_extractor.py      🔲 Person A
    pdf_extractor.py       🔲 Person A — text layer, then vision for scans
    llm_extract.py         🔲 Person A — Claude fallback + vision
  normalize.py             🔲 Person B — value normalisation, number parsing
  comparator.py            🔲 Person B — escalates everything today
  db/schema.sql            ✅ starting schema (emails, extracted_documents, results, review_queue)
  api/main.py              🔲 Person B — only /health exists
tests/test_contract.py     ✅ 10 tests, must stay green for both of you
```

Baseline right now: `python -m src.pipeline` processes all 520 emails and writes a
shape-valid `submission.json` where everything is `GENERAL`. That is the floor we build up from.

---

## 4. Who owns what

Work in your own files. The only shared files are `src/models.py`, `src/pipeline.py`
and this one — touch those deliberately, not incidentally.

**Person A — "the brains": classification and extraction**
`src/classifier.py`, `src/extractor/*`
Turns an email into a category, and an attachment into an `ExtractedDocument` with the
7 fields. Owns the label aliases and all Claude prompts.

**Person B — "the body": comparison, service, infrastructure**
`src/normalize.py`, `src/comparator.py`, `src/submission.py`, `src/db/*`, `src/api/*`, `deploy/*`
Turns two `ExtractedDocument`s into a verdict, stores everything, exposes the API and the
human-review screen, and deploys to AWS.

**Neither of you has to wait for the other.** Person B tests the comparator against
hand-made documents:

```python
from src.models import ExtractedDocument, DocType
si = ExtractedDocument.fake("email_1", DocType.SI, container_count=3)
bl = ExtractedDocument.fake("email_1", DocType.BL, container_count=4)
compare(si, bl)   # expect MISMATCH, defect_fields == ["container_count"]
```

Person A tests extractors against the real files in `data/attachments/` without needing
the comparator at all.

---

## 5. Commands

```bash
pip install -r requirements.txt

pytest -q                       # contract tests — keep green
python -m src.pipeline          # full run -> submission.json + a category breakdown
python -m src.pipeline --limit 20   # quick pass while developing

# self-eval: run the organizers' docker bundle (sdoc-hackathon-docker.zip), then
python scripts/run_self_eval.py         # POSTs submission.json, prints the scoreboard
```

---

## 6. What the score rewards

Two separate scoring systems. Do not confuse them.

**Organizers' self-eval** (a development instrument, tells us if the pipeline is right):
50% end-to-end (a planted defect only counts if the email was routed to `BL_COMPARISON`
*and* the exact `defect_fields` were flagged) + 30% classification macro-F1 + 20% defect-F1.
`NEEDS_REVIEW` handling is reported separately as a reliability axis: escalating the cases
we genuinely cannot decide scores well, escalating everything does not.

**Judges' rubric** (100 points, what actually decides the hackathon):
Technical 70 — Working Core Prototype **25**, System Design & Architecture 15,
Technology Integration 15, Technical Feasibility & Validation 15.
Product & Impact 30 — Problem Statement Understanding 10, Innovation & Solution Approach 10,
Practical Value & Potential 10.

The single biggest line is a **working prototype**, so prefer a complete rough pipeline
over a perfect half of one. Depth (LLM fallback, vision OCR, human review, AWS deploy)
is what earns Technology Integration and Feasibility on top of that.

---

## 7. Dataset facts worth knowing

- 520 emails. True distribution: BL_COMPARISON 220, SI_REQUEST 125, INVOICE_QUERY 75,
  GENERAL 60, SPAM 40.
- Of the 220 comparison emails: 154 clean, 46 with a real defect, 20 genuinely
  undecidable (5 each of `wrong_doc_type`, `missing_attachment`, `unreadable`,
  `missing_value`). If the pipeline escalates far more than ~20, the logic is too cautious.
- Some email subjects are deliberately misleading — weigh the body too, and note that
  having both an SI and a BL attachment is itself a strong `BL_COMPARISON` signal.
- `NET WEIGHT` appears in the documents and is **not** `gross_weight_kg`.
- A few attachments are a certificate of origin rather than an SI/BL — those are the
  `wrong_doc_type` cases. See `field_aliases.is_foreign_document()`.
- Worked example, `email_004`: SI says consignee/notify `EAST BRIGHT FZ-LLC`, BL says
  `UAB NOVAKOPA`, everything else agrees → `MISMATCH` on `consignee` and `notify_party`.

---

## 8. Git workflow

Two people, short hackathon, small repo: branch per work stream, merge into `main` at the
end of each day.

```bash
git checkout -b feature/pipeline-core     # Person A
git checkout -b feature/service-infra     # Person B
```

Commit in small pieces with a message that says what changed and why. If you touched
`src/models.py`, say so in the first line — that is the one change the other person must
know about immediately.

The fuller plan (architecture reasoning, AWS deployment steps, day-by-day schedule) lives
in the Claude project "hackaton" as `hackathon-plan.md` and `hackathon-tasks.md`.
