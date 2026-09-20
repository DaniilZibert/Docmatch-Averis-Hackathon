# What happens to a layout nobody wrote rules for

Measured 2026-09-20 on five SI/BL pairs in five unrelated layouts — dotted leaders, a numbered form, running prose, a pipe-delimited sheet, a bilingual form. Known values, one planted discrepancy each. None of their labels appears in `field_aliases`, and none is close enough for the fuzzy pass.

```bash
python scripts/unseen_layouts.py --with-ai
```

| configuration | documents read | field values recovered | SI values correct | discrepancies found | AI calls | cost |
|---|---|---|---|---|---|---|
| **rules only** | 0/10 | 0/70 | 0/35 | 0/5 | 0 | $0.0000 |
| **rules + AI** | 10/10 | 70/70 | 35/35 | 5/5 | 10 | $0.0464 |

## Per case

| case | layout | planted | rules only | rules + AI |
|---|---|---|---|---|
| `bilingual` | bilingual form | notify_party | NEEDS_REVIEW | MISMATCH ✓ |
| `columnar` | pipe-delimited sheet | gross_weight_kg | NEEDS_REVIEW | MISMATCH ✓ |
| `dotted` | dotted leaders | port_of_discharge | NEEDS_REVIEW | MISMATCH ✓ |
| `numbered` | numbered form | container_count | NEEDS_REVIEW | MISMATCH ✓ |
| `prose` | running prose | consignee | NEEDS_REVIEW | MISMATCH ✓ |

## The point

The supplied inbox is the one dataset where the rules cannot lose: they were written by reading it. Off it, they recover nothing at all and every document is escalated as unreadable — which is the correct behaviour, and useless to the clerk waiting for an answer.

That is what the model is for, and it is why the architecture is a hybrid rather than a choice between the two. On the supplied data the AI contributes six documents out of 248; on paperwork written by somebody who never saw our aliases it contributes all of it.
