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
| Upload new data | a judge brings their own SI and draft BL, or a whole inbox, and watches it run |

Every row in every list opens its case on a click anywhere in the row, not just on the
id — the small link alone did not read as "you can open this".

A case shows which label each value was read from — *"read as SI 'Consignee
(Non-Negotiable)' vs BL 'To the Order of'"* — which is the brief's "the same
information can look different", shown rather than claimed. The SI and BL are links, so
a reviewer can check us against the source. Confirm or clear a case and the verdict,
the counters and the report update immediately.

Rows blank on one side are deliberately **not** pre-ticked as defects: a missing value
is why we stopped, not a discrepancy, and the screen must not walk a reviewer into
confusing the two.

### Judges can bring their own data

**Upload new data** (`/upload`) takes an SI and a draft BL in any of the four formats
and runs them through the same code path the bundled inbox takes — no special case, no
second implementation to keep in step. It also takes a `.zip` shaped like `data/` to
swap the whole working dataset, with one button to put the bundled one back. Nothing is
written into `data/`.

This is where the hybrid stops being a claim. An uploaded document is by definition a
layout nothing has seen, so the rules parse the labels they recognise and the AI reads
the rest. Tested on a booking note written entirely in unfamiliar wording — "Party
sending the goods", "Taking on board at", "Boxes in this lot":

* all seven fields came back from both documents
* `seven x 40'HC` was read as 7
* the gross weight was taken, not the net figure sitting on the next line
* the planted discrepancy was found — PIRAEUS against THESSALONIKI
* two real API calls, $0.0104

Nineteen of the tests cover this, weighted towards the hostile cases: an upload form on
a public URL is the one place a stranger hands us bytes. A zip member that escapes the
extraction root is refused, as are non-archives, archives with no `inbox/`, unreadable
file types and oversized anything.

### The AI switch

Off by default, one click in the header, shows what it has spent, survives restarts.

**The organizers ruled that we may not gate the paid actions** — the prototype has to be
publicly accessible in full — so the budget is defended without locking anybody out:

* every AI answer is cached on disk against the exact bytes of the request. The first
  pass over anything new is a genuine call; the same documents again are free. Somebody
  pressing `/run` in a loop therefore costs nothing after the first press.
* a cumulative $2.50 ceiling, written to disk on every call, which switches the AI off
  by itself and survives restarts.
* a 20-second cooldown on `/run`, which throttles rather than denies.

The cache is consulted **only while the AI is on**. Serving cached answers with the
switch off would put vision results into the rules-only column of the ablation table
while reporting zero calls — see A1. Details in
[OPERATIONS.md](OPERATIONS.md#3-the-ai-switch-and-what-stops-it-emptying-the-budget).

### Infrastructure

AWS EC2 in ap-southeast-2, `docmatch.tech` on HTTPS via Caddy (certificate renews
itself), and CI/CD that tests every push and deploys `main` — with no ssh anywhere in
the pipeline and no credentials held by CI. [OPERATIONS.md](OPERATIONS.md).

### Validation

228 tests, free and offline. `scripts/evaluate.py` saves each run and diffs two of them
email by email with an error breakdown per scoring axis. `scripts/check_robustness.sh`
scores against freshly generated inboxes. `scripts/llm_smoke.py` proves the three
Claude paths work on input the rules cannot handle.

---

## The rules, and what they change

Source: [Rules & Regulations](https://docs.google.com/document/d/10PZgxtw4qvDg19NESDZPXt2oc6pSYsj9DKoKOY8PvdI/edit)
· [Preliminary judging criteria](https://docs.google.com/document/d/1EiI_mqJYeMN0D-dtZ_npCavVGXVcePFmcZ7O4d4ygQI/edit)
· [Final judging criteria](https://docs.google.com/document/d/1S-bLf45JOabMl1QUDgl4F6NTwuwD7UKbhPKh74sqaRo/edit)

**Deadline: 22 September, 12:00 p.m.** — noon, not end of day.

### The one that changes our strategy

> "The submitted solution must incorporate **Artificial Intelligence (AI) Technology as
> a key component**."
> "All submissions must incorporate AI and utilize cloud infrastructure… Solutions that
> do not meaningfully integrate cloud infrastructure may receive significantly reduced
> scores."

We have been selling the opposite. The README opens with "Rules only, no API calls", the
live header says **`no LLM calls`** and **`AI no key`**, and our headline achievement is
a perfect score with zero AI. A judge checking a mandatory requirement against that page
has everything they need to mark us down.

The engineering is not wrong — deterministic where it is reliable, AI where it is not,
is the right design and we can defend it. What is wrong is that our materials actively
hide the AI, and that on the demo box the AI is switched off with no key.

Be honest about the size of it: on this dataset the rules resolve all 520 emails and
vision fires on exactly 6 — the image-only scans, which nothing deterministic can read.
That is real and irreplaceable, but it is 6 of 520, and "key component" needs to be
visible and measured rather than asserted. **A1 and A2 below stop being nice-to-have.**

### Hard requirements we must satisfy

| requirement | state |
|---|---|
| AI as a key component | ⚠️ **at risk** — see above |
| Cloud infrastructure, meaningfully integrated | ✅ AWS EC2, Caddy, CI/CD, registry |
| Repository link, **public**, clear README with setup | ✅ public — and it must stay that way |
| Live prototype link, **publicly accessible** to judges | ✅ <https://docmatch.tech> |
| Demo video, ≤ 5 min, YouTube unlisted or public | ❌ **not started** |
| Slide deck, public link | ❌ **not started** |
| Project description | ❌ not started |
| All work done during the hackathon | ✅ |

The repo and the demo **must be public** — that is a submission requirement, so closing
either is not available to us. It also means the video is worth real marks on its own:
**one mark is deducted for every 30 seconds over five minutes.**

The video has a required shape: Intro (team + project) → the Problem (who it affects
and why) → Tech Stack → Live Demo of the working prototype → Impact (metrics, results).

### Where the marks are

Preliminary, 100 points. Our standing, honestly assessed:

| criterion | max | us |
|---|---|---|
| Working Core Prototype | **25** | strong — the core flow works end to end, deployed |
| System Design & Architecture | 15 | strong — needs an architecture diagram in the deck |
| Technology Integration | 15 | **the AI risk lands here** |
| Technical Feasibility & Validation | 15 | strong — 228 tests, six unseen datasets, error analysis |
| Problem Statement Understanding | 10 | strong — needs saying out loud in the deck |
| Innovation & Solution Approach | 10 | thin — nothing distinctive is *explained* yet |
| Practical Value & Potential | 10 | needs the real-inbox path and cost numbers |

"Do not reward the same evidence twice" is in the judges' instructions, so the deck
should point different evidence at different criteria rather than repeating the score.

---

## Left — two days, and it is all presentation and proof

The pipeline is finished. **P0 first, then P1. P2 is what gets dropped.**

### Person A — Daniil: make the AI visible and measured

**A0 · Turn the AI on — P0, but NOT until the submission is in** *(one command)*

```bash
./scripts/enable_ai.sh          # key in place, AI on, admin token printed
```

The demo box says `AI no key`, which on a public page argues against a mandatory
requirement — so this has to happen before judging. It must **not** happen early: `/run`
costs six vision calls and anyone can press it.

We asked the organizers whether the paid actions could sit behind a token. **They said
no** — the prototype must be publicly accessible in full. So the protection is not a
lock on the door: every AI answer is cached on disk, which makes the second and every
later run free (measured: 6 paid calls then 0), backed by a cumulative $2.50 ceiling
and a 20-second cooldown. Turning it on is a single safe command.
See [OPERATIONS.md](OPERATIONS.md#3-the-ai-switch-and-what-stops-it-emptying-the-budget).

**A1 · Ablation table — P0** *(was P1; the rules promoted it)* *(Technology Integration 15,
Technical Feasibility 15)*
Rules-only vs rules+AI vs AI-only, across accuracy, cost and latency. This is what turns
"AI is a key component" from a claim into a measurement, and it is the same table that
justifies the architecture. The rules-only column is already measured; the other two need
the switch on. ~30 calls, under $0.50.
*Done when:* a three-row table with real numbers, in the deck and the README.

**A2 · What only AI can do — P0** *(Technology Integration, 15)*
Quantify the part no rule can replace: six image-only scans read by vision, and the
unfamiliar-layout rescue (`scripts/llm_smoke.py` already proves it reads 7/7 fields from
a document with no known labels, and correctly takes gross weight over net). Record the
per-call cost and latency. This is the honest answer to "is the AI load-bearing".

**A3 · Reframe our own materials — P0** *(30 minutes)*
README and the header currently lead with the absence of AI. Change the story to what it
actually is: *deterministic where it is provably reliable, AI where it is not, and we
measured both.* Do not delete the rules-only number — it is a genuine strength — but stop
leading with it.

**A4 · Housekeeping — P1**
- Delete the four dead CI variables.
- **Mirror the repo to GitHub.** The form says "GitHub Repository Link" and we are on
  GitLab. Probably fine, plausibly not; a mirror costs ten minutes and removes the
  question.
- Tell the organizers on Discord that the dataset they supplied contains real staff
  names, work emails and phone numbers, and that a public repo is mandatory. Their data,
  their call — but ours to raise, not to quietly decide. See "Data" below.

**A5 · Learning from corrections — P2** *(Innovation, 10)*
Mine a reviewer's accepted correction into `field_aliases` so the system improves on the
layouts this customer actually sends. The review loop and provenance already exist.

### Person B — Nikita: the submission itself

Three of the four mandatory components are yours, and none of them exists yet.

**B0 · Demo video — P0** *(mandatory; marks deducted for length)*
Five minutes maximum, YouTube unlisted or public. Required shape: intro → problem →
tech stack → live demo → impact. Script it, rehearse it twice, then record.
The demo spine that works: inbox arrives → 520 triaged in a second → open a flagged case
→ the two documents side by side with the differing labels → **a scanned BL being read by
AI vision** → a case we refused to decide, and why → settle it and watch the report change.
That vision moment is what makes AI visibly a key component. Do not cut it.
*Done when:* uploaded, link works in an incognito window, under 5:00.

**B1 · Slide deck — P0** *(mandatory; Product & Impact is 30 points)*
Required sections, named in the rules: **Technical Architecture, Implementation Details,
Challenges Faced, Future Roadmap.** Numbers come from A1/A2 — ask early, do not wait.
Include the reliability story: 20 of 520 escalated, zero false alarms, and why refusing
to answer is a feature rather than a gap.

**B2 · Project description — P1** *(mandatory, short)*
Name, purpose, problem statement. A paragraph, but it is the first thing a judge reads.

**B3 · The real inbox — P1** *(Practical Value, 10)*
The sample data is generated from real Outlook `.msg` files. Show the path to a live
inbox: IMAP or Microsoft Graph, `.msg` parsing, what changes and what does not. A working
`src/ingest/msg.py` would be strong; a clear slide is enough.
*Self-contained — new files only.*

**B4 · Fresh-eyes review — P1**
Include `/upload`: upload two documents of your own invention and see whether the result
is understandable to someone who did not build it.
Read `CLAUDE.md` first: several things in the extractors look like bugs and are
deliberate, and that section says which. Then try to break <https://docmatch.tech>.
Anything confusing to you is confusing to a judge.

**B5 · Auto-drafted reply — P2** *(Innovation, 10)*
Given a MISMATCH, draft the email back to the carrier. Turns a detector into a colleague.

### Together, before noon on the 22nd

- Submit early. The form is [here](https://forms.gle/nnam5eXrf5cjXdf3) and late means not
  considered.
- One full rehearsal against <https://docmatch.tech> on a phone, on venue wifi.
- `./scripts/check_robustness.sh` once more after any rule change.
- Confirm the video link opens in an incognito window — private videos are not accepted.

---

## Data: something to raise, not to decide alone

The rules say nothing about the supplied dataset — the Data Protection section covers
participants' own information and resumes, and there is no NDA or confidentiality clause.
So no rule is being broken.

But the dataset the organizers gave us contains, by their generator's own comment, "real
names & email patterns": **12 named individuals' corporate email addresses**, 99 direct
phone numbers, an office address and 20 real customer companies. The domains resolve and
carry live enterprise mail. All of that is now in a public repository and served by a
public website — both of which the submission rules **require** to be public.

We cannot fix this by closing either one. Every other team is in the same position with
the same data, so this is the organizers' decision propagating, not ours. The right move
is to say so on Discord and let them decide — anonymising is possible (the scoring only
uses email ids and field names, so fake names would not change a single number) but it
is their data and their call.

## Coordination

The only real dependency is **A1/A2 → B1**: Nikita needs the measured numbers for the
deck and the video. Get them to him on the morning of the 21st, not the night before.

Both P0 lists have to be done by the evening of the 21st, because the 22nd is a half
day — the deadline is noon.

File ownership, to avoid collisions:

| | files |
|---|---|
| A | `scripts/*`, `src/extractor/*`, `deploy/*`, `README.md`, CI, AWS |
| B | `src/ingest/*` (new), `src/draft.py` (new), the deck, the video, the description |
| shared — say so before you touch | `src/models.py`, `src/pipeline.py`, `CLAUDE.md` |

Branch per person, merge to `main` at the end of each day. Pushing to `main` deploys —
the tests gate it, but it does go live.
