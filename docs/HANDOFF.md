# Nikita, start here

One document, everything in it. You should not need to open another file to know what
this project is, what already works, what is yours, and what the numbers are.

**Averis × Monash Hackathon 2026 — shipping document verification.**
Deadline **noon, 22 September**. Submission form: <https://forms.gle/nnam5eXrf5cjXdf3>.
Live: <https://docmatch.tech> · Repo: GitLab `daniilz2018/averis-hackaton`, mirrored to
GitHub for the form.

---

## The one thing to understand before you touch anything

**The product is finished, deployed, and scores a perfect 1.0000.** Nothing on your list
is about making it work. Everything left is about making the case for it — video, deck,
description. If your first instinct is to build a feature, that instinct is wrong here;
the marks that are still on the table are presentation marks.

> **Run it before you read the rest.** Half of this only makes sense after you have
> clicked through a case.
>
> ```bash
> pip install -r requirements.txt
> pytest -q                             # 235 tests, offline, free
> python -m src.pipeline                # 520 emails -> submission.json, ~1.3s
> uvicorn src.api.main:app --reload     # then http://localhost:8000
> ```

---

## What the thing does

An operations inbox arrives. For every email: decide what kind of request it is. For the
document-check requests, pull the **draft Bill of Lading** and the **Shipping
Instruction** out of the attachments, compare seven shipment fields, and say which ones
disagree — or refuse to answer and escalate to a person, with the evidence.

* **5 categories:** `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, `SPAM`
* **7 compared fields:** shipper, consignee, notify_party, port_of_loading,
  port_of_discharge, container_count, gross_weight_kg
* **4 attachment formats:** `.txt`, `.xlsx`, `.docx`, `.pdf` — plus image-only PDFs,
  which go to Claude vision
* **3 verdicts:** `OK`, `MISMATCH`, `NEEDS_REVIEW`

**The architecture in one sentence:** deterministic where that is provably reliable, AI
where it is not, and we measured both instead of asserting either.

Five screens at <https://docmatch.tech>: Overview, Inbox, Case, Report, Upload new data.
A judge can upload their own SI and BL — or a whole inbox as a zip — and watch it run
through the identical code path.

---

## Every number you need, in one place

Copy these into the deck. They are all measured, all reproducible, none estimated.

### The score

Against the organizers' own `score_cli.py`:

| axis | weight | score |
|---|---|---|
| stage 1 · classification macro-F1 | 30% | **1.0000** |
| stage 3 · defect F1 | 20% | **1.0000** |
| end-to-end · defects caught on the exact field set | 50% | **1.0000** (46/46) |
| **final** | | **1.0000** |

**And 1.0000 again on six inboxes it had never seen** — 1,590 emails, different seeds.
That is the number that matters: the first one could be overfitting, the second cannot.

### Reliability — the story judges remember

* 520 emails triaged in **1.3 seconds**
* 220 document checks, 46 discrepancies found
* **20 escalated to a human — recall 1.000, precision 1.000.** Twenty needed a person;
  we flagged exactly those twenty. No missed defect, no false alarm.
* **Refusing to answer is a feature.** A missing value is not a discrepancy, and the
  screen will not let a reviewer confuse the two.

### Ablation — why hybrid, measured (`out/ablation.md`)

| configuration | accuracy | macro-F1 | documents read | $ / 1000 emails | sec / 1000 |
|---|---|---|---|---|---|
| **Rules only** | 1.000 | 1.000 | 242 | $0.00 | 3s |
| **Rules + AI** (shipped) | 1.000 | 1.000 | **248** | $0.21 | 42s |
| ↳ same inbox again | 1.000 | 1.000 | 248 | **$0.00** | 2s |
| **AI only** (sample of 57) | 0.983 | 0.980 | 26 | $4.19 | 2882s |

Three things to say out loud about this table:

1. **AI-only costs ~20× more and ~69× longer to land slightly behind.** Comparing two
   parsed records is simply an easier problem than reasoning about two documents in prose.
2. **The `documents read` column is the whole argument for the hybrid.** Six of the 248
   attachments are image-only scans with no text layer. No parser opens those. Vision
   does. The rules stop at 242; the model takes it to 248.
3. **AI-only gave two different answers to identical input** — defect-F1 0.923 then
   1.000, same sample, same prompt. Every deterministic row was byte-identical every
   run. For a document-checking system that is not a footnote.

### The unseen-layout test — the strongest slide we have (`out/unseen-layouts.md`)

Five SI/BL pairs in five layouts nothing in the code has ever seen: dotted leaders, a
numbered form, running prose, a pipe-delimited sheet, a bilingual form.

| | documents read | field values recovered | discrepancies found | cost |
|---|---|---|---|---|
| **rules only** | 0/10 | **0/70** | 0/5 | $0.00 |
| **rules + AI** | 10/10 | **70/70** | **5/5** | $0.046 |

This is the honest frame for the perfect score: the supplied inbox is the one dataset
where the rules cannot lose, because they were written by reading it. Off it they
recover *nothing* — and the AI recovers all of it. On the supplied data AI contributes 6
documents out of 248; on paperwork written by someone who never saw our aliases, it
contributes everything.

### Engineering

* **235 tests**, offline, no API calls, no spend
* **AWS EC2** `ap-southeast-2`, Docker, Caddy with automatic Let's Encrypt
* **CI/CD:** GitLab CI → container registry → pull-based deploy on a systemd timer
* **Spend guards:** every AI answer cached against the exact bytes of the request, a
  cumulative $2.50 ceiling, and a 20-second cooldown on `/run`

---

## Hard rules — these matter more than anything below

1. **Never commit `ground_truth.json`.** The answer key lives outside the repo. The
   repository is public.
2. **Never add a `Co-Authored-By:` trailer to a commit.** A hook strips it; install it
   with `./tools/install-hooks.sh` right after you clone.
3. **Do not turn the AI on.** `./scripts/enable_ai.sh` is Daniil's, and it runs *after*
   the submission is in. The site is public — `/run` costs six vision calls and anyone
   can press it. Today the server has no key at all, on purpose.
4. **Read §5 of `CLAUDE.md` before "fixing" anything in the extractors.** Several things
   in there look like bugs and are deliberate — ignored address lines, a skipped PDF
   container table, blank tokens that are not values. Undoing one costs real score.
5. **`pytest -q` before every push.** If your change reddens a test, the test is usually
   right.
6. **The repo stays public and so does the site.** The rules require both.

---

## Your work

Three of the four mandatory submission components are yours and none of them exists yet.
**P0 first. P2 is what gets dropped.**

### B0 · Demo video — P0, mandatory
Five minutes maximum — one mark comes off per 30 seconds over. YouTube, public or
unlisted; **check it opens in an incognito window**, private videos are not accepted.

Required shape, from the rules: **intro → problem → tech stack → live demo → impact.**

The demo spine that works:

> inbox arrives → 520 triaged in a second → open a flagged case → the two documents side
> by side with the differing labels named → **a scanned BL being read by AI vision** → a
> case we refused to decide, and why → settle it and watch the report change

That vision moment is what makes AI visibly a key component, which is a mandatory
requirement rather than a nice-to-have. **Do not cut it for time.** Script it, rehearse
twice, then record.

### B1 · Slide deck — P0, mandatory
Four sections, named in the rules and marked against: **Technical Architecture,
Implementation Details, Challenges Faced, Future Roadmap.**

Every number you need is in "Every number you need" above — you should not have to ask
for a single one. For *Challenges Faced*, the good material is real and already written
down in `docs/PLAN.md`: the 91-email escalation trap, PDF glyph collisions, and the
ablation run that scored 0.509 because a call cap silently truncated it — a wrong number
that flattered our own architecture and nearly got published.

Lead with the hybrid, not with the perfect score. The perfect score invites "your rules
just memorised the sample"; the unseen-layout table answers that before it is asked.

### B2 · Project description — P1, mandatory
Name, purpose, problem statement. One paragraph — but it is the first thing a judge reads.

### B3 · The real inbox — P1 *(Practical Value, 10)*
The sample data was generated from real Outlook `.msg` files. Show the path to a live
inbox: IMAP or Microsoft Graph, `.msg` parsing, what changes and what does not. A working
`src/ingest/msg.py` would be strong; a clear slide is enough. **Self-contained — new
files only, nothing existing needs editing.**

### B4 · Fresh-eyes review — P1
You are the only person who has not been staring at this. Use `/upload`: invent two
documents and see whether the result makes sense to someone who did not build it. Then
try to break <https://docmatch.tech>. **Anything confusing to you is confusing to a
judge** — say so, that feedback is worth more than another feature.

### B5 · Auto-drafted reply — P2 *(Innovation, 10)*
Given a MISMATCH, draft the email back to the carrier. Turns a detector into a colleague.
Only if everything above is done.

---

## Together, before noon on the 22nd

* **Submit early.** Late is not considered.
* One full rehearsal against the live site, on a phone, on venue wifi.
* Daniil runs `./scripts/enable_ai.sh` last, once the submission is in.
* Confirm the video link opens incognito.

---

## Where everything is

```
src/
  models.py                THE CONTRACT — changing it affects everything
  pipeline.py              classify -> extract -> compare -> submission.json
  config.py                .env, the AI switch, the call budget — the only env reader
  classifier.py            template rules + Claude fallback
  normalize.py             blanks, numbers, conservative text matching
  comparator.py            the five-step decision order
  report.py / submission.py
  extractor/               one module per format, plus field_aliases and llm_extract
  api/                     main.py routes · store.py state · ui.py screens · uploads.py
scripts/
  evaluate.py              score a run, diff two runs, error analysis
  check_robustness.sh      score against freshly generated, never-seen inboxes
  ablation.py              the three-architecture table
  unseen_layouts.py        the unseen-layout table
  enable_ai.sh             Daniil's, after submission
out/
  ablation.md              numbers for the deck
  unseen-layouts.md        numbers for the deck
tests/                     235 tests
```

| document | when to open it |
|---|---|
| **this file** | first, and mostly the only one you need |
| `README.md` | what the product is, for a judge rather than for us |
| `CLAUDE.md` | before changing code — the traps, the invariants, the contract |
| `docs/PLAN.md` | the full record: what was built, what broke, who did what |
| `docs/OPERATIONS.md` | deploy, the AI switch, what to do if the site is down |
