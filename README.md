# DocMatch — Shipping Document Verification

**Team DURKA · Averis × Monash Hackathon 2026**

An operations inbox goes in. A discrepancy report comes out: every email classified, every
document-check request answered by comparing the draft **Bill of Lading** against the
**Shipping Instruction** it is supposed to match — naming exactly which shipment fields
disagree, or handing the case to a person, with the evidence, when the documents cannot be
read.

**Live: <https://docmatch.tech>** — the full product, running, with the supplied inbox
already processed. You can also upload your own documents and watch them go through the
same code.

```
520 emails  ->  classify  ->  extract SI + BL  ->  compare 7 fields  ->  report
                   |               |                      |
                 rules         txt/xlsx/docx/pdf     OK · MISMATCH · NEEDS_REVIEW
                 + Claude      + Claude vision       + the two documents side by side
```

---

## The Problem

A freight forwarder tells the carrier what to ship and where — that is the **Shipping
Instruction (SI)**. The carrier replies with a **draft Bill of Lading (BL)**, and that
document is what the cargo legally travels on and what everyone is paid against.

The two are supposed to agree. Often they do not: the consignee is wrong, or the discharge
port, or the container count. Caught while the BL is still a draft, the fix costs one
email. Missed, it costs re-issued documents, a delayed vessel and a cargo claim.

So today a shipping clerk opens both files side by side and compares seven fields by eye,
hundreds of times a week — inside an inbox that is also carrying invoice queries, requests
for new instructions, operational chatter and spam.

Three things make it harder than it sounds:

- **Finding the work.** The document requests are mixed in with everything else, and a
  request that is overlooked never reaches the checking step at all.
- **The same field, different words.** One document says *Port of Loading*, the other says
  *Load Port*. One says *Consignee*, the other says *To the Order of*. Matching has to be
  by meaning, never by header text.
- **Not knowing is not the same as a discrepancy.** A value the sender left as `TBA`, a
  scan nobody can read, an invoice sent in place of a BL — none of those are errors in the
  shipment. Reporting them as errors is the false alarm that makes a checking tool get
  switched off.

---

## What We Built

A complete pipeline and a working product around it.

For each of the 520 emails the system decides a **category** — `BL_COMPARISON`,
`SI_REQUEST`, `INVOICE_QUERY`, `GENERAL` or `SPAM` — and for document-check requests it
extracts and compares seven fields: `shipper`, `consignee`, `notify_party`,
`port_of_loading`, `port_of_discharge`, `container_count`, `gross_weight_kg`.

Each check ends in one of three verdicts: **`OK`** (all seven agree), **`MISMATCH`** (with
the exact fields that differ), or **`NEEDS_REVIEW`** (with the reason it stopped —
`wrong_doc_type`, `missing_attachment`, `unreadable` or `missing_value`).

Five screens:

| screen | what it is for |
|---|---|
| **Overview** | what arrived, what was found, what is waiting for a person |
| **Inbox** | all 520 emails, filterable by category and outcome, searchable |
| **Case** | one email beside the two documents, field by field, with the decision |
| **Report** | the discrepancy report, ready to send on, plus which fields go wrong most |
| **Upload new data** | bring your own SI and draft BL — or a whole inbox — and watch it run |

A case puts the email on the left and the seven compared fields on the right, with the
differing rows highlighted and **the label each value was read under** shown beneath them —
*"read as SI 'Consignee (Non-Negotiable)' vs BL 'To the Order of'"*. Both documents are
links, so the reviewer can open the source and check the system rather than trust it. Tick
the rows that really differ and press **Confirm discrepancy**, or **No mismatch** to clear
the case; the verdict, the counters and the report all update immediately.

Rows blank on one side are deliberately **not** pre-ticked. A missing value is why we
stopped, not a discrepancy, and the screen must not walk a reviewer into confusing the two.

---

## Getting Started

**Python 3.11 or newer.** Verified on 3.11 (the Docker image) and on 3.14 from a clean
clone.

```bash
git clone <this repository>
cd averis-hackaton

python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # optional — ANTHROPIC_API_KEY enables the AI fallbacks

pytest -q                     # 234 tests · offline · no API calls · no spend
python -m src.pipeline        # 520 emails -> submission.json + a run summary
uvicorn src.api.main:app --reload     # then open http://localhost:8000
```

The virtual environment is not ceremony: on a current macOS or Debian the system Python
refuses `pip install` outright, and that would make the very first command fail.

The service processes the inbox itself on startup — there is no command to run and nothing
to load.

Without an API key everything still works: the deterministic path handles the supplied
dataset end to end and the header says `AI no key`, so a missing key is never the reason
something is broken.

**No Python at all:**

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build   # then localhost
```

**Running against a different inbox** — one variable, no code change:

```bash
python -m src.pipeline --data-dir /path/to/new-inbox
DATA_DIR=/path/to/new-inbox uvicorn src.api.main:app
```

The folder needs `inbox/email_*.json` and an `attachments/` directory shaped like `data/`.

---

## Technical Architecture

**Deterministic where that is provably reliable, AI where it is not — and both halves
measured rather than asserted.**

That sentence is the whole design. Template rules carry the ordinary traffic in seconds
for nothing at all; Claude handles what no rule can reach — scanned pages with no text
layer, document layouts nobody has seen, emails outside our templates.

### The pipeline

```
EmailRecord
    |
    v
[1] CLASSIFIER  ── spam check → attachment check → subject templates
    |                → body templates → Claude fallback
    |  category, and which rule decided it
    v
[2] EXTRACTOR   ── one module per format, all producing (label, value) pairs
    |                txt · xlsx · docx · pdf(text) · pdf(scan → Claude vision)
    |                pairs → canonical fields via field_aliases
    |  ExtractedDocument × 2  (the SI and the BL)
    v
[3] COMPARATOR  ── six-step decision order
    |
    v
EmailResult → submission.json · discrepancy report · review queue · the screens
```

**Stage 1 — classification.** Checks run in a deliberate order. Spam first, because a
phishing mail often quotes a real subject line and would otherwise be classified by it.
Then the presence of an attachment, which is decisive — no other category ever carries
one. Then subject templates, then body templates. Only when nothing fires does the email
go to Claude, and the result records which rule decided it, so every verdict on screen
can show its own provenance.

**Stage 2 — extraction.** Four format modules, each with one job: turn its file into a
list of `(label, value)` pairs. Everything after that happens once, in shared code, so the
four cannot drift apart — resolving labels to canonical fields, telling a blank apart from
a value, parsing numbers, recognising a document that is not an SI or BL at all.

All label knowledge lives in a single module. That is what makes *Load Port* and *Port of
Loading* land in the same field, and it is the one place to extend when new paperwork
arrives.

**Stage 3 — comparison.** A fixed decision order, and the order itself carries meaning:

```
1. an attachment is absent          -> NEEDS_REVIEW / missing_attachment
2. a file cannot be read            -> NEEDS_REVIEW / unreadable
3. a file is a different document   -> NEEDS_REVIEW / wrong_doc_type
4. a needed value is not stated     -> NEEDS_REVIEW / missing_value
5. values came off a scan           -> NEEDS_REVIEW (read, but a person confirms)
6. otherwise compare all seven      -> OK, or MISMATCH + the exact fields
```

An invoice sent instead of a BL is missing six of the seven fields, so checking
*wrong_doc_type* before *missing_value* is what gives the human the useful reason rather
than a misleading one.

### Interfaces and dependencies

`src/models.py` is the contract every stage codes against — the categories, the verdicts,
`ExtractedDocument`, `ComparisonResult`. It made the two halves of the project buildable
in parallel: the comparator was written and tested against synthetic documents before a
single real extractor existed.

The service is **one container** on purpose. The pipeline processes the whole inbox in
seconds, so a queue and a database would be moving parts with nothing to move; results
live in memory and `src/db/schema.sql` records the shape a persistent deployment takes
when volume justifies one. Complexity that is not yet needed is complexity that can break
during a demo.

### Deployment

One container on **AWS EC2** (`ap-southeast-2`) behind **Caddy**, which obtains and
renews its Let's Encrypt certificate on its own. Pushing to `main` runs the tests, builds
the image, proves the container starts and publishes it; the server picks it up on its own
timer and the pipeline waits until `/health` reports the new commit. **No ssh anywhere in
the pipeline, and CI holds no server credentials.**

---

## Implementation Details

### The hybrid, concretely

Rules read **242 of the 248 attachments**. The remaining six are image-only PDFs — someone
put paper on a scanner, and the file contains pixels, not characters. No parser opens
those, no matter how many rules you write. The PDF module detects the absence of a text
layer (under 40 characters on the page), renders the page to PNG and hands the image to
**Claude vision**, which reads the fields off it the way a person would.

That is not the only AI path. When the rules recover fewer than five of the seven fields
from a document that *is* an SI or BL, the text goes to Claude before we give up on it —
because an unfamiliar layout is a reading problem, not a missing document, and the brief
asks us to tell those apart. And when no classification rule fires, Claude picks the
category.

Two guard rails on the model's answer, both deliberate:

- it is accepted **only if it recovers more fields than the rules did**, so a vague model
  answer can never replace a good deterministic parse;
- a field the rules read as an explicit blank (`???`, `TBA`, `____MT`) **keeps that
  blank**. The document says the sender does not know, and no amount of model confidence
  should turn that into a value we then compare.

### Everything degrades, nothing raises

No API key, no network, a corrupt file, a missing library — each produces an honest
`NEEDS_REVIEW`, never a crash, and one bad email can never lose the other 519. A live demo
has to survive a dead network and a rate limit.

### Cost control on a public URL

The site is public and `/run` is a button anyone can press, so spending is bounded by
design: every AI answer is **cached against the exact bytes of the request** (re-running
the same documents is free), a **cumulative $2.50 ceiling** survives restarts and overrides
the switch, a per-run call cap applies whatever the switch says, and `/run` has a cooldown.
The AI switch itself is off by default and flips from the header with one click, no
redeploy.

### What the pipeline handles

| | |
|---|---|
| **Label synonymy** | *Port of Loading* vs *Load Port*, *Consignee* vs *To the Order of*, and bilingual Word labels (`Gross Weight毛重(KGS)`) |
| **Four formats** | 192 `.txt`, 28 `.pdf`, 22 `.xlsx`, 8 `.docx` |
| **Scanned pages** | image-only PDFs go to Claude vision; the values are read and shown, and the case still goes to a person |
| **Collided glyphs** | three PDFs interleave a long label with its value; the label is subtracted back out |
| **Blanks vs defects** | `???`, `TBA`, `____MT` mean the sender does not know — `NEEDS_REVIEW`, never a mismatch |
| **Wrong documents** | a commercial invoice, packing list or certificate of origin sent instead of a BL, detected by the document's own title |
| **Numbers, not strings** | `6 x 40'HC` → 6, `131,058 KG` → 131058, and `NET WEIGHT` is never read as the gross |
| **Human in the loop** | everything undecided reaches the review queue with all seven rows and the label each value was read under |

### Engineering

**234 tests**, all offline, no API calls, no spend. Tests cover the contract, each format
extractor, the label aliases against every real label in the dataset, the comparator's
decision order, the API and the upload path. The container runs as a non-root user because
it reads documents that arrive from outside.

---

## Results and Validation

Measured with the organizers' own `score_cli.py`, on the deterministic path alone:

| axis | weight | score |
|---|---|---|
| stage 1 · classification macro-F1 | 30% | **1.0000** |
| stage 3 · defect F1 | 20% | **1.0000** |
| end-to-end · defects caught on the exact field set | 50% | **1.0000** (46/46) |
| **final score** | | **1.0000** |
| reliability · escalation recall / precision | diagnostic | **1.000 / 1.000** (20 flagged, 20 gold) |
| resolved deterministically, no AI call needed | diagnostic | 100% |

**And 1.0000 again on six inboxes it had never seen** — 1,590 emails, different generator
seeds, every defect caught on the exact field set. The first number could be overfitting;
the second cannot. `./scripts/check_robustness.sh` reproduces it.

**Twenty of the 520 were escalated, and they are exactly the twenty that genuinely cannot
be decided by machine.** No missed defect, no false alarm.

### Why hybrid, measured rather than argued

`scripts/ablation.py` runs three architectures against the answer key. Costs come from the
spend ledger — they are what was actually spent.

| configuration | accuracy | macro-F1 | defect-F1 | documents read | $ / 1000 | sec / 1000 |
|---|---|---|---|---|---|---|
| Rules only | 1.000 | 1.000 | 1.000 | 242 | $0.00 | 3s |
| **Rules + AI — what we ship** | 1.000 | 1.000 | 1.000 | **248** | $0.21 | 39s |
| ↳ the same inbox again | 1.000 | 1.000 | 1.000 | 248 | **$0.00** | 2s |
| AI only *(stratified sample of 57)* | 0.983 | 0.980 | 1.000 | 26 | $4.19 | 2882s |

Three things fall out of it. An all-LLM pipeline costs **about 20× more and runs about 69×
slower** to land slightly behind — comparing two parsed records field by field is simply an
easier problem than reasoning about two documents in prose. The `documents read` column is
the entire argument for the hybrid: rules stop at 242, vision takes it to 248. And the
all-LLM run **gave two different answers to identical input** (defect-F1 0.923, then
1.000, same sample, same prompt) while every deterministic row was byte-identical every
time. For a document check that is not a footnote: a discrepancy report that might read
differently tomorrow is one somebody has to verify again.

Full artifact with the caveats: [out/ablation.md](out/ablation.md).

### The honest frame for a perfect score

Six documents out of 248 makes the AI sound decorative. That is a fair reading and it is
wrong, because the rules were written by reading this dataset — of course they cover it.
The question worth asking is what happens to paperwork from someone who never saw our
aliases.

Five SI/BL pairs in five unrelated layouts — dotted leaders, a numbered form, running
prose, a pipe-delimited sheet, a bilingual form — each with known values and one planted
discrepancy:

| configuration | documents read | field values recovered | discrepancies found | cost |
|---|---|---|---|---|
| Rules only | 0/10 | **0/70** | 0/5 | $0.0000 |
| **Rules + AI** | **10/10** | **70/70** | **5/5** | $0.0464 |

Off the supplied data the rules recover *nothing* and escalate every document as unreadable
— correct behaviour, and useless to the clerk waiting for an answer. On the supplied inbox
the AI contributes six documents; on paperwork written by a stranger it contributes
everything. That is why this is a hybrid rather than a choice between the two.

[out/unseen-layouts.md](out/unseen-layouts.md)

---

## Challenges Faced

### Telling a false alarm from a real escalation

Ninety-four of the 220 document-check emails arrive with nothing attached, and they look
identical until you read them. Ninety-one say *"Please assist to send the draft BL for
checking"* — the sender is asking **us** for the document, nothing has gone wrong, there is
simply nothing to compare yet. Three say *"Please compare the SI and draft BL (attachments
appear to have been dropped)"* — the sender believes they attached the documents, and a
person has to go back to them.

Escalating all 94 would not have changed the final score by a single point, because the
scorer reads only category and defect fields. It would have dropped escalation precision
from 1.00 to 0.18 — a review queue where nineteen cases out of twenty are noise, which is
a queue that gets ignored by the second day. We wrote a separate test for the distinction
rather than letting the scoreboard decide what was correct.

### Glyph collisions in the PDF text layer

Three PDFs draw a long label that overruns its column, and the extracted text layer
interleaves the two character runs: `Notify Party/Intermediate Consignee` plus its value
comes out as `Notify Party/Intermediate ConsCigEnReIEeX`. Neither word-level extraction nor
filtering characters by x-coordinate separates them — the runs genuinely overlap in the
file. The fix subtracts the known label tail back out by case. Unglamorous, and without it
three documents silently lose their notify party.

### A column that looks like the answer and is not

The PDF container table has a `GROSS WEIGHT (KG)` column, and every row of it holds **one
container's** weight — 21,887 — while the shipment total sits on a separate line further
down at 131,322. A parser that trusts the column heading reports a weight that is wrong by
a factor of six and looks entirely plausible. Container rows are now skipped by the format
of their container id, not by a start/end state machine, because the table's own summary
line rotates between aliases and any single end-marker swallows the others.

### A measurement that flattered us

An early ablation run scored the AI-only configuration at 0.509 — a beautiful number for
our argument, and wrong. A call cap had silently truncated the run partway through, so the
model was being marked absent on emails it never got to see. It nearly went into our own
materials. We now report the AI-only column on a declared stratified sample with the
caveat attached, because a benchmark that favours the architecture you already chose is
the one that deserves the most suspicion.

### An install that worked for us and nobody else

The three dependencies with compiled wheels carried hard `==` pins. On a Python newer than
the pin no wheel exists, so `pip` fell back to building from source and stopped — meaning
the very first command in our setup instructions failed for anyone who was not us. Worse,
one of the three is not optional: the bilingual labels only resolve through its fuzzy pass,
so a failed install quietly takes real capability with it. The three now carry floors
rather than pins; the Docker image pins Python instead, which is where reproducibility
belongs.

### Five review cases that offered nothing to review

An email escalated *before* any document is read has no comparison rows, and the case
screen keyed both its table and its buttons off those rows. The result: five cases sitting
in the queue under a banner insisting a person was needed, footed with *"Nothing to decide
on this one."* A screen that asks for review and then presents nothing is a dead end, and
the queue never empties. Row-less escalations now get their own pane, naming the documents
we expected and what actually arrived, with their own two closures. Found by clicking
through the live site, not by any test — which is its own lesson.

---

## Future Roadmap

### Connect a real inbox

The sample data was generated from real Outlook `.msg` files, and the pipeline's input is
already a plain record — sender, subject, body, attachment paths. Only the ingest adapter
is new work: IMAP or Microsoft Graph for collection, `.msg` parsing for the attachments,
and a poller that feeds the identical pipeline. Nothing downstream changes, which is a
consequence of the contract in `src/models.py` rather than luck.

### Reply, not just detect

Given a `MISMATCH`, draft the email back to the carrier: the booking reference, the fields
that differ, the SI value each should be. A human presses send. This turns a detector into
a colleague, and it is the shortest path from "saves checking time" to "closes the loop".

### Learn from the reviewer

Every confirmation and correction in the review queue is a labelled example. An unfamiliar
label that a reviewer resolves by hand once is a label the alias table could learn
permanently — the system gets cheaper and more deterministic the longer it runs, rather
than more dependent on the model.

### Scale when volume asks for it

At today's volume a single container is the right answer, and the persistence shape is
already written down in `src/db/schema.sql`. At real volume the order is: results and the
review queue into Postgres, then a job queue in front of the extractors. The bottleneck
will be vision calls rather than parsing, and those parallelise cleanly — the deterministic
path is already CPU-bound and trivially horizontal.

### Beyond SI and BL

The comparison engine is not specific to these two documents. Packing list against
commercial invoice, booking confirmation against SI, final BL against draft — same seven
fields in most cases, same alias table, same escalation discipline.

### How we would measure success in production

Checks completed per reviewer-hour; share of document requests closed with no human touch;
discrepancies caught before the draft is signed off versus after; escalation precision
holding at or near 1.00 as the paperwork drifts; cost per thousand emails.

---

## Repository Layout

| path | what |
|---|---|
| `src/models.py` | the shared data contract |
| `src/pipeline.py` | classify → extract → compare → `submission.json` |
| `src/classifier.py` | template rules, Claude fallback, attachment expectation |
| `src/extractor/` | one module per format, plus label aliases and the Claude paths |
| `src/normalize.py`, `src/comparator.py` | value normalisation and the six-step comparison |
| `src/report.py` | the discrepancy report |
| `src/api/` | the service and the five screens |
| `scripts/` | scoring, run diffing, robustness, ablation, unseen layouts, smoke tests |
| `data/` | the supplied dataset: 520 emails, 250 attachments |
| `out/` | measurement artifacts referenced above |
| `tests/` | 234 tests |

### Further documentation

| | |
|---|---|
| **[CLAUDE.md](CLAUDE.md)** | engineering guide: the invariants, the data traps, the contract |
| **[docs/PLAN.md](docs/PLAN.md)** | the full build record — what was made, what broke, who did what |
| **[docs/OPERATIONS.md](docs/OPERATIONS.md)** | the server, the domain, CI/CD, the AI switch |
| **[docs/use-case.pdf](docs/use-case.pdf)** | the original problem statement |
