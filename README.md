# averis-hackaton — shipping document verification

From an operations inbox to a discrepancy report: classify every email, and for
document-check requests compare the draft **Bill of Lading** against the **Shipping
Instruction** it is supposed to match, flagging exactly which of the seven shipment
fields disagree — or escalating to a human, with the evidence, when the documents
cannot be read.

```
520 emails  ->  classify  ->  extract SI + BL  ->  compare 7 fields  ->  report
                   |               |                      |
                 rules          txt/xlsx/docx/pdf     OK · MISMATCH · NEEDS_REVIEW
                 + Claude       + Claude vision       + the SI/BL rows side by side
```

## Where it stands

Rules-only, no API calls, ~1 second for the whole inbox, measured with the organizers'
own `score_cli.py`:

| axis | weight | score |
|---|---|---|
| stage 1 · classification macro-F1 | 30% | **1.0000** |
| stage 3 · defect F1 | 20% | **1.0000** |
| end-to-end · defects caught with the exact fields | 50% | **1.0000** (46/46) |
| **final score** | | **1.0000** |
| reliability · escalation recall / precision | diagnostic | 1.000 / 1.000 (20 flagged, 20 gold) |
| resolved by rules, no LLM call | diagnostic | 100% |

The same 1.0000 holds on data the system has never seen: six freshly generated inboxes
(1,590 emails, different seeds) score 1.0000 each, with every defect caught on the exact
field set. `./scripts/check_robustness.sh <path to data_v2>` reproduces it.

Claude is wired in for the cases the rules cannot reach — scanned pages, unparseable
layouts, unrecognised emails — and every one of those paths degrades to an honest
`NEEDS_REVIEW` when there is no key, no network or no library. The demo cannot be
taken down by a rate limit.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # optional: add ANTHROPIC_API_KEY for the fallbacks

pytest -q                     # 176 tests — free, offline, no API calls
python -m src.pipeline        # 520 emails -> submission.json + a run summary
python -m src.pipeline --report out/report.md      # + the discrepancy report
```

## The product

```bash
uvicorn src.api.main:app --reload     # then open http://localhost:8000
```

That is the whole thing — it processes the inbox itself on startup, so there is no
command to run and nothing to load.

| screen | what it is for |
|---|---|
| **Overview** | what came in, what was found, what is waiting for a person |
| **Inbox** | all 520 emails, filterable by category and outcome, searchable |
| **Case** | one email beside the two documents, field by field, with the decision |
| **Report** | the discrepancy report, ready to send on |

A case shows the email on the left and the seven compared fields on the right, with the
differing rows highlighted and the label each value was read under ("read as SI
'Consignee (Non-Negotiable)' vs BL 'To the Order of'"). The SI and the BL are links —
the reviewer can open the source document and check us. Tick the rows that really
differ and press **Confirm discrepancy**, or **No mismatch** to clear the case; the
verdict, the counters and the report update immediately and the app moves to the next
case in the queue.

Rows that are blank on one side are deliberately *not* pre-ticked: a missing value is
why we stopped, not a discrepancy, and the screen should not walk a reviewer into
confusing the two.

### On a server

```bash
cp .env.example .env          # set SDOC_DOMAIN
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

One container behind Caddy, which gets a Let's Encrypt certificate on its own. The full
runbook — EC2 instance, security group, DNS, what the GitHub Student Pack covers — is in
**[docs/deploy-aws.md](docs/deploy-aws.md)**.

Measuring a change:

```bash
# the answer key is NOT in this repo — pass its path, or use the organizers' server
python scripts/evaluate.py --ground-truth /path/to/ground_truth.json
python scripts/evaluate.py --server http://localhost:8080

# keep runs and diff them email by email
python scripts/evaluate.py --ground-truth <key> --save out/runs/before.json
python scripts/evaluate.py --compare out/runs/before.json out/runs/after.json

# will it hold on data nobody has seen? (generates fresh inboxes, rules only, free)
./scripts/check_robustness.sh /path/to/data_v2

# are the Claude fallbacks alive? (~4 calls, a few cents)
python scripts/llm_smoke.py --vision
```

## What it handles

| | |
|---|---|
| **Label synonymy** | "Port of Loading" vs "Load Port", "Consignee" vs "To the Order of", and the bilingual Word labels ("Gross Weight毛重(KGS)"). All in `src/extractor/field_aliases.py`. |
| **Four formats** | 192 `.txt`, 28 `.pdf`, 22 `.xlsx`, 8 `.docx` — including the PDF container table whose `GROSS WEIGHT (KG)` column holds one container's weight, not the shipment's. |
| **Scanned pages** | Image-only PDFs go to Claude vision. The values are read and shown — and the case still goes to a person, because an OCR'd image is not enough to sign off a bill of lading. |
| **Collided glyphs** | Three PDFs interleave a long label with its value (`Notify Party/Intermediate ConsCigEnReIEeX`). The known label tail is subtracted back out. |
| **Blanks vs defects** | `???`, `TBA`, `____MT` mean the sender does not know. That is `NEEDS_REVIEW`, never a mismatch — the false alarm the brief warns about. |
| **Wrong documents** | An invoice, packing list or certificate of origin sent instead of a BL is detected by the document's own title, not by its labels. |
| **Human in the loop** | Everything undecided reaches `/review` with all seven rows and the label each value was read under. A correction updates the report immediately. |

## Layout

| path | what |
|---|---|
| `src/models.py` | the shared data contract between both work streams |
| `src/pipeline.py` | classify → extract → compare → `submission.json` |
| `src/classifier.py`, `src/extractor/` | email categorisation and field extraction |
| `src/normalize.py`, `src/comparator.py` | value normalisation and the SI/BL comparison |
| `src/report.py` | the discrepancy report |
| `src/api/`, `src/db/` | service layer, human-review screen |
| `scripts/evaluate.py` | score a run, save it, diff two runs, error analysis |
| `data/` | the participant dataset: 520 emails, 250 SI/BL attachments |
| `docs/use-case.pdf` | the original problem statement |

## Working on this

Read **[CLAUDE.md](CLAUDE.md)** first. It holds the contract rules, who owns which
files, what the score actually rewards (several things about it are not obvious), and
every dataset trap we have already hit — including the ones that look like bugs if you
"fix" them.
