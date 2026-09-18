"""
OWNER: Person A.  STUB — email -> Category.

Stage 1 of the pipeline, worth 30% of the organizers' score on its own (macro-F1) and
a precondition for everything else: a BL_COMPARISON email that gets misfiled never
reaches the comparison step, so it also costs us on the 50% end-to-end axis.

Ground-truth distribution over the 520 emails, for calibration:
    BL_COMPARISON 220 | SI_REQUEST 125 | INVOICE_QUERY 75 | GENERAL 60 | SPAM 40

Hybrid by design (see docs/hackathon-plan.md):
    rules first  -> cheap, deterministic, explainable
    Claude after -> only for the ones no rule decides confidently

Return the category AND how it was decided; `decided_by` is tracked by the organizers'
scorer (`rule_pct`) and tells us how much of the inbox the rules actually cover.

Careful: subjects are deliberately misleading in part of the dataset ("REQUEST BL
DRAFT..." on an email whose body is an invoice question). Weigh the body, not only the
subject, and remember that the presence of both an SI and a BL attachment is a strong
BL_COMPARISON signal on its own.
"""

from __future__ import annotations

from .models import Category, DecidedBy, EmailRecord

# TODO(Person A): fill these from the real inbox. Start by reading a dozen emails per
# category: `python -c "import json,glob;..."` or just open data/inbox/email_0*.json.
RULES: dict[Category, tuple[str, ...]] = {
    Category.BL_COMPARISON: ("draft bl", "check the details", "si and draft"),
    Category.SI_REQUEST: ("please prepare", "shipping instruction request"),
    Category.INVOICE_QUERY: ("invoice", "payment", "outstanding"),
    Category.SPAM: ("unsubscribe", "congratulations", "limited offer"),
}


def classify(email: EmailRecord) -> tuple[Category, DecidedBy]:
    """TODO(Person A): rule pass, then LLM fallback.

    Returns (category, decided_by). Until implemented it returns GENERAL for
    everything, which keeps the pipeline runnable end to end.
    """
    return Category.GENERAL, DecidedBy.RULE


__all__ = ["RULES", "classify"]
