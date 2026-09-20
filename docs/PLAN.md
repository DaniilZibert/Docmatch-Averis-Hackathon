# Where we are, and who does what next

Hackathon 18–22 September. Written 20 September, end of day 3.

**Person A — Daniil** · **Person B — Nikita**

---

## The short version

The product is finished and deployed. It scores a perfect 1.0000 on the organizers'
own scorer, and 1.0000 again on six inboxes it has never seen. Nothing on the list
below is about making it work — it all exists to make the case for it.

> **Nikita: run it before you read any of this.** `pytest -q`, then
> `uvicorn src.api.main:app --reload`, then open <http://localhost:8000>. Half of what
> follows only makes sense once you have clicked through a case. The live one is
> <https://docmatch.tech>.

---

## Done

### The pipeline — scores 1.0000

Against the organizers' `score_cli.py`, rules only, zero API calls, 520 emails in ~1.3s:

| axis | weight | score |
|---|---|---|
| stage 1 · classification macro-F1 | 30% | **1.0000** |
| stage 3 · defect F1 | 20% | **1.0000** |
| end-to-end · defects caught with the exact field set | 50% | **1.0000** (46/46) |
| **final** | | **1.0000** |
| reliability · escalation recall / precision | diagnostic | 1.000 / 1.000 (20 flagged, 20 gold) |
| resolved by rules, no LLM call | diagnostic | 100% |

And **1.0000 on six freshly generated inboxes** (seeds 3, 7, 42, 1234, 20260920, 99999
— 1,590 emails it had never seen). `./scripts/check_robustness.sh` reproduces it. That
exercise is what found the glyph-collision bug a code review had missed.

- **Classify** — subject/body templates, ordered so GENERAL is matched before
  INVOICE_QUERY (the `_RPA_ … Billing` bot notice is a GENERAL email containing
  "Billing"). Claude only if no rule fires.
- **Extract** — all four formats: 192 `.txt`, 28 `.pdf`, 22 `.xlsx`, 8 `.docx`, plus
  Claude vision on the six image-only scans. Every trap handled: the PDF container
  table whose `GROSS WEIGHT (KG)` column holds one container's weight, the three PDFs
  whose long labels collide with their values in the text layer, the `NAME | ADDRESS`
  packing that differs between Excel and Word, blank placeholders (`???`, `TBA`,
  `____MT`) that are uncertainty and not discrepancies.
- **Compare** — a five-step decision order that gives a human the *useful* reason: an
  invoice sent instead of a BL is missing six fields, but "wrong document" is what they
  need to hear, not "missing value".
- **Escalate** — 20 of 520 genuinely cannot be decided, and we escalate exactly those
  20, with no false alarms. Including the distinction that costs the most: 94 comparison
  emails arrive with no attachment and only 3 of them are an error.
- **Report** — the discrepancy report the brief asks for, "No mismatch detected." and all.

### The product

Four screens at <https://docmatch.tech>, no command to start anything:

| screen | for |
|---|---|
| Overview | what came in, what was found, what is waiting for a person |
| Inbox | all 520 emails, filterable and searchable |
| Case | the email beside the two documents, field by field, with the decision |
| Report | the discrepancy report, ready to send on |

A case shows which label each value was read from — *"read as SI 'Consignee
(Non-Negotiable)' vs BL 'To the Order of'"* — which is the brief's "the same
information can look different", shown rather than claimed. The SI and BL are links, so
a reviewer can check us against the source. Confirm or clear a case and the verdict,
the counters and the report update immediately.

Rows blank on one side are deliberately **not** pre-ticked as defects: a missing value
is why we stopped, not a discrepancy, and the screen must not walk a reviewer into
confusing the two.

### The AI switch

Off by default, one click in the header, shows what it has spent, survives restarts.
Four independent layers stop an accidental spend. Details in
[OPERATIONS.md](OPERATIONS.md#3-the-ai-switch).

### Infrastructure

AWS EC2 in ap-southeast-2, `docmatch.tech` on HTTPS via Caddy (certificate renews
itself), and CI/CD that tests every push and deploys `main` — with no ssh anywhere in
the pipeline and no credentials held by CI. [OPERATIONS.md](OPERATIONS.md).

### Validation

197 tests, free and offline. `scripts/evaluate.py` saves each run and diffs two of them
email by email with an error breakdown per scoring axis. `scripts/check_robustness.sh`
scores against freshly generated inboxes. `scripts/llm_smoke.py` proves the three
Claude paths work on input the rules cannot handle.

---

## Left — and it is all rubric work

Two days. The score is finished; these earn points on the judges' 100, not on the
scoreboard. **P1 first. If time runs out, P2 is what gets dropped.**

### Person A — Daniil: the evidence

You have the harness, the API key and the infrastructure context.

**A1 · Ablation table — P1** *(Technical Feasibility & Validation, 15)*
Rules-only vs rules+LLM vs LLM-only, across accuracy, cost and latency. The rules-only
column is already measured; the other two need the switch on. ~30 calls, under $0.50.
`scripts/evaluate.py --save` then `--compare` produces the diff.
*Done when:* a three-row table with real numbers, in the slides and in the README.
*Why it matters:* it is the argument for the whole design. Right now "we did not need
an LLM" is a claim; this makes it a measurement.

**A2 · Measured LLM run — P1** *(Technology Integration, 15)*
Turn the switch on once, run the full inbox, record `rule_pct`, wall-clock and dollars.
All three paths are verified working; what is missing is the numbers beside them.
*Done when:* the figures are in A1's table and the cost per 1000 emails is on a slide.

**A3 · Housekeeping — P1** *(15 minutes, do it first)*
- Delete the four dead CI variables (`SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`,
  `DEPLOY_USER`, `DEPLOY_PATH`).
- Decide on repository visibility. **It is public right now** — an anonymous clone
  succeeded. Competitors can read everything. Deliberate or not, decide it on purpose.
- Put the API key on the server if the demo will show vision.

**A4 · Learning from corrections — P2** *(Innovation, 10)*
When a reviewer corrects a field, mine the label they accepted into `field_aliases`, so
the system gets better at the layouts this customer actually sends. The review loop and
the provenance data already exist; this closes it. A counter of "aliases learned" makes
it visible in the demo.

### Person B — Nikita: the story

Nothing here needs the internals. It needs someone who can look at this the way a judge
will — which is easier for you than for us right now.

**B1 · Demo script — P1** *(affects every rubric line)*
Three minutes, written down, rehearsed twice. The spine that works:
inbox arrives → 520 triaged in a second → open a flagged case → the two documents side
by side with the labels that differ → the case that we *refused* to decide and why →
settle it and watch the report change.
**Rehearse it with the AI switch off.** The whole system runs rules-only and says so.
Never demo something that needs the network to work.
*Done when:* you can deliver it start to finish without touching a terminal.

**B2 · Slides — P1** *(Product & Impact, 30 — the largest single block)*
The problem, the approach, the numbers, the honest limits. Numbers come from A1/A2 —
ask for them, do not wait. Include the reliability story: 20 of 520 escalated, zero
false alarms, and why refusing to answer is a feature.

**B3 · The real inbox — P1** *(Practical Value, 10)*
The sample data is generated from real Outlook `.msg` files (see `pools.py` in the
organizers' bundle: real carriers, real ports, real customers). Show the path from here
to a live inbox: IMAP or Microsoft Graph, `.msg` parsing, what changes and what does
not. A working `src/ingest/msg.py` that reads one real `.msg` into our `EmailRecord`
would be strong; a clear slide is enough.
*Self-contained — new files only, touches nothing that exists.*

**B4 · Fresh-eyes review — P1** *(cheap, high value)*
You have not seen this code. Read `CLAUDE.md` first — several things in the extractors
look like bugs and are deliberate, and that section says which. Then poke at
<https://docmatch.tech> and try to break it. Anything confusing to you is confusing to
a judge.

**B5 · Auto-drafted reply — P2** *(Innovation, 10)*
Given a MISMATCH, draft the email back to the carrier listing the fields to fix. Turns
the system from a detector into a colleague. New module plus one button on the case
screen; nothing existing changes.

### Together, at the end

- Run `./scripts/check_robustness.sh` once more after any rule change.
- One full rehearsal against <https://docmatch.tech>, on a phone, on venue wifi.
- Confirm `submission.json` from a clean run is what gets handed in.

---

## Coordination

The only real dependency is **A1/A2 → B2**: Nikita needs the numbers for the slides.
Get them early on day 4 rather than the night before.

File ownership, to avoid collisions:

| | files |
|---|---|
| A | `scripts/*`, `src/extractor/*`, `deploy/*`, CI, AWS |
| B | `src/ingest/*` (new), `src/draft.py` (new), slides, demo notes |
| shared — say so before you touch | `src/models.py`, `src/pipeline.py`, `CLAUDE.md` |

Branch per person, merge to `main` at the end of each day. Pushing to `main` deploys —
the tests gate it, but it does go live.
