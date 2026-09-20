# Shipping document verification

From an operations inbox to a discrepancy report: classify every email, and for
document-check requests compare the draft **Bill of Lading** against the **Shipping
Instruction** it is supposed to match — flagging exactly which of the seven shipment
fields disagree, or escalating to a person, with the evidence, when the documents
cannot be read.

### **Live: <https://docmatch.tech>**

```
520 emails  ->  classify  ->  extract SI + BL  ->  compare 7 fields  ->  report
                   |               |                      |
                 rules         txt/xlsx/docx/pdf     OK · MISMATCH · NEEDS_REVIEW
                 + Claude      + Claude vision       + the SI/BL rows side by side
```

## Where it stands

Rules only, no API calls, the whole inbox in ~1.3 seconds, measured with the
organizers' own `score_cli.py`:

| axis | weight | score |
|---|---|---|
| stage 1 · classification macro-F1 | 30% | **1.0000** |
| stage 3 · defect F1 | 20% | **1.0000** |
| end-to-end · defects caught with the exact field set | 50% | **1.0000** (46/46) |
| **final score** | | **1.0000** |
| reliability · escalation recall / precision | diagnostic | 1.000 / 1.000 (20 flagged, 20 gold) |
| resolved by rules, no LLM call | diagnostic | 100% |

**And 1.0000 on data it has never seen** — six freshly generated inboxes, 1,590 emails,
different seeds, every defect caught on the exact field set.
`./scripts/check_robustness.sh` reproduces it.

Claude is wired in for what the rules cannot reach — scanned pages, unfamiliar layouts,
emails outside our templates — and every one of those paths degrades to an honest
`NEEDS_REVIEW` with no key, no network or no library. The demo cannot be taken down by
a rate limit.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # optional: ANTHROPIC_API_KEY for the fallbacks

pytest -q                     # 197 tests — free, offline, no API calls
python -m src.pipeline        # 520 emails -> submission.json + a run summary
uvicorn src.api.main:app --reload    # then open http://localhost:8000
```

The service processes the inbox itself on startup. There is no command to run and
nothing to load.

## The product

| screen | what it is for |
|---|---|
| **Overview** | what came in, what was found, what is waiting for a person |
| **Inbox** | all 520 emails, filterable by category and outcome, searchable |
| **Case** | one email beside the two documents, field by field, with the decision |
| **Report** | the discrepancy report, ready to send on |

A case shows the email on the left and the seven compared fields on the right, with the
differing rows highlighted and the label each value was read under — *"read as SI
'Consignee (Non-Negotiable)' vs BL 'To the Order of'"*. The SI and the BL are links, so
the reviewer can open the source and check us. Tick the rows that really differ and
press **Confirm discrepancy**, or **No mismatch** to clear the case; the verdict, the
counters and the report update immediately and the app moves to the next case.

Rows blank on one side are deliberately *not* pre-ticked: a missing value is why we
stopped, not a discrepancy, and the screen should not walk a reviewer into confusing
the two.

### The AI switch

Claude costs money and the rules do not need it, so it is **off** until somebody turns
it on — from the header, one click, no redeploy:

```
●  520 emails in 1.3s · no LLM calls    [ ○──  AI off ]    Re-run
```

On, it goes green and shows the calls made and the running cost. The setting survives a
restart. `LLM_MAX_CALLS` caps calls per run whatever the switch says, CI pins it off,
and the test suite disables it independently.

## What it handles

| | |
|---|---|
| **Label synonymy** | "Port of Loading" vs "Load Port", "Consignee" vs "To the Order of", and the bilingual Word labels ("Gross Weight毛重(KGS)") |
| **Four formats** | 192 `.txt`, 28 `.pdf`, 22 `.xlsx`, 8 `.docx` — including the PDF container table whose `GROSS WEIGHT (KG)` column holds one container's weight, not the shipment's |
| **Scanned pages** | Image-only PDFs go to Claude vision. The values are read and shown — and the case still goes to a person, because an OCR'd image is not enough to sign off a bill of lading |
| **Collided glyphs** | Three PDFs interleave a long label with its value (`Notify Party/Intermediate ConsCigEnReIEeX`); the label is subtracted back out by case |
| **Blanks vs defects** | `???`, `TBA`, `____MT` mean the sender does not know. That is `NEEDS_REVIEW`, never a mismatch — the false alarm the brief warns about |
| **Wrong documents** | An invoice, packing list or certificate of origin sent instead of a BL, detected by the document's own title |
| **Human in the loop** | Everything undecided reaches the review queue with all seven rows and the label each value was read under |

## Deployment

One container behind Caddy, which gets a Let's Encrypt certificate on its own. Pushing
to `main` runs the tests, builds the image, proves the container starts and publishes
it; the server picks it up within a minute on its own timer and the pipeline waits
until `/health` reports the new commit. No ssh, and CI holds no credentials.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d
```

## Layout

| path | what |
|---|---|
| `src/models.py` | the shared data contract |
| `src/pipeline.py` | classify → extract → compare → `submission.json` |
| `src/classifier.py`, `src/extractor/` | categorisation and field extraction |
| `src/normalize.py`, `src/comparator.py` | value normalisation and the SI/BL comparison |
| `src/report.py` | the discrepancy report |
| `src/api/` | the service and the four screens |
| `scripts/` | scoring, run diffing, robustness, LLM smoke test |
| `data/` | the participant dataset: 520 emails, 250 attachments |

## The documents

| | |
|---|---|
| **[CLAUDE.md](CLAUDE.md)** | read first if you are going to change code: the rules, what the score rewards, and every trap in the data |
| **[docs/PLAN.md](docs/PLAN.md)** | what is done, what is left, and who does which |
| **[docs/OPERATIONS.md](docs/OPERATIONS.md)** | the server, the domain, CI/CD, the AI switch, teardown |
| **[docs/use-case.pdf](docs/use-case.pdf)** | the original problem statement |
