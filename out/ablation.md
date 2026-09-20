# Ablation: rules, hybrid, AI only

Measured 2026-09-20 against the organizers' answer key. Costs are read from the spend ledger, not estimated.

| configuration | emails | accuracy | macro-F1 | defect-F1 | end-to-end | documents read | AI calls | cost | wall clock |
|---|---|---|---|---|---|---|---|---|---|
| **Rules only** (no AI) | 520 | 1.000 | 1.000 | 1.000 | 1.000 | 242 | 0 | $0.0000 | 1.4s |
| **Rules + AI** (what we ship) | 520 | 1.000 | 1.000 | 1.000 | 1.000 | 248 | 6 | $0.1078 | 21.7s |
| &nbsp;&nbsp;↳ the same inbox again | 520 | 1.000 | 1.000 | 1.000 | 1.000 | 248 | 0 | $0.0000 | 1.0s |
| **AI only** (sample of 57) | 57 | 0.983 | 0.980 | 1.000 | 1.000 | 26 | 82 | $0.2390 | 164.3s |

| configuration | cost per 1000 emails | seconds per 1000 emails |
|---|---|---|
| **Rules only** (no AI) | $0.00 | 3s |
| **Rules + AI** (what we ship) | $0.21 | 42s |
| &nbsp;&nbsp;↳ the same inbox again | $0.00 | 2s |
| **AI only** (sample of 57) | $4.19 | 2882s |

Reproduce with:

```bash
python scripts/ablation.py --ground-truth <key> --all --sample 50 --pairs 8
```

## What the table says

**The deterministic path is not a shortcut — it is the better instrument for this
inbox.** It matches the model on every scored axis and does it for nothing in about a
second. Comparing two parsed records field by field is simply an easier problem than
reading two documents and reasoning about them in prose. Anyone arguing for an all-LLM
pipeline here is arguing to pay $4.19 per thousand emails to be slightly less accurate.

**But it cannot read everything, and no amount of extra rules would fix that.** Six of
the 248 attachments are image-only scans with no text layer. No parser opens those;
vision does. The `documents read` column is the whole argument for the hybrid — the
rules stop at 242, the model takes it to 248, and those six are bills of lading that a
clerk would otherwise have to open by hand.

**AI-only is accurate but the wrong tool at this scale:** ~20x the cost and ~69x the
wall clock, to land slightly behind.

**The repeat row is the operational one.** The same inbox costs nothing the second time,
because every answer is cached against the exact bytes of the request. That is what
makes a public `/run` button safe to leave unguarded.

### One thing the single run hides

The AI-only row was measured twice on the same sample with the same prompt:

| run | accuracy | macro-F1 | defect-F1 | cost | wall clock |
|---|---|---|---|---|---|
| first | 0.983 | 0.980 | **0.923** | $0.2485 | 150.9s |
| second | 0.983 | 0.980 | **1.000** | $0.2390 | 164.3s |

Same input, different answer. Every deterministic row was byte-identical across every
run. For a document-checking system that is not a footnote: a discrepancy report that
might say something different tomorrow is a report somebody has to re-check, and the
audit trail of *why* a field was flagged is a label the rules can name and a model can
only paraphrase.

### Honest limits of this measurement

* AI-only is a stratified sample of 57 emails, not the full inbox — ten per category,
  because macro-F1 weights the five categories equally. A full AI-only pass is about
  $3.50, most of the team budget, to answer a question a sample answers.
* One model (`claude-sonnet-5`), one prompt. A different prompt would move the AI-only
  row; it would not move it 20x on cost.
* Latency is sequential. Batching would cut the AI-only wall clock substantially and
  change none of the money.
* The first attempt at this table scored AI-only at 0.509 accuracy. That was
  `LLM_MAX_CALLS=40` silently truncating the run — after the cap the classifier stopped
  being called and returned its default. Recorded because the wrong number flattered
  our own architecture and we came close to publishing it.
