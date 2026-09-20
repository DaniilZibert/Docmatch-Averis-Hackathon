"""
OWNER: Person A.  Stage 1 — email -> Category.

Worth 30% of the organizers' score on its own (macro-F1) and a precondition for
everything else: a BL_COMPARISON email that gets misfiled never reaches the comparison
step, so it also costs us on the 50% end-to-end axis.

Ground-truth distribution over the 520 emails:
    BL_COMPARISON 220 | SI_REQUEST 125 | INVOICE_QUERY 75 | GENERAL 60 | SPAM 40

Macro-F1 averages the five categories EQUALLY, so the 40 SPAM emails are worth as much
as the 220 comparison ones. Do not optimise the big class at the small ones' expense.

Hybrid by design: rules first (cheap, deterministic, explainable), Claude only for what
no rule decides. `decided_by` rides along to the submission so the organizers' scorer
reports `rule_pct` — that number is the evidence for "we did not need an LLM for this".

WHY THE ORDER OF THE RULES MATTERS
    Categories overlap lexically, so a keyword alone decides nothing:
      "BL"               appears in 64 BL_COMPARISON, 12 SI_REQUEST and 9 GENERAL subjects
      "invoice|billing"  appears in 60 INVOICE_QUERY, 9 GENERAL and 2 SPAM subjects
      "SI"               appears in 125 SI_REQUEST and 11 GENERAL subjects
    The worst offender is "_RPA_ India HSS SD Billing Process Completed", a GENERAL bot
    notice that contains "Billing". GENERAL is therefore matched BEFORE INVOICE_QUERY.
    Match on the whole subject TEMPLATE, never on a single word.

WHAT IS AND IS NOT A SIGNAL
    * An attachment is decisive: all 126 emails that carry one are BL_COMPARISON, and
      no other category ever attaches a file. 100% precision, checked on the inbox.
    * The subject is not "deliberately misleading" in this dataset — the overlap above
      is lexical, not adversarial. Do not build defences against a trap that is not
      there; do weigh the body when the subject template is ambiguous.
"""

from __future__ import annotations

import re

from .models import Category, DecidedBy, EmailRecord

# ---------------------------------------------------------------------------
# Rules, in the order they are evaluated. Each entry is (name, category, pattern)
# and the pattern is matched against the subject unless the name says `body:`.
# ---------------------------------------------------------------------------

SPAM_SENDER = re.compile(
    r"@(prize-claims|parcel-track|webmail-verify|logistics-deals|crypto-invest"
    r"|secure-mailbox|.*-winner|free-\w+)\.", re.IGNORECASE)

SPAM_CONTENT = re.compile(
    r"you have won|congratulations!|claim your|gift card|unpaid customs|"
    r"storage limit|mailbox has exceeded|avoid deactivation|avoid suspension|"
    r"bitcoin|guaranteed \d+% return|hot singles|weird trick|"
    r"confirm your bank details|undelivered messages|90% off|click here to claim",
    re.IGNORECASE)

# Subject templates, per category. Matched with re.search on the subject line.
SUBJECT_RULES: tuple[tuple[str, Category, re.Pattern[str]], ...] = (
    # --- GENERAL first: its bot/report templates contain "Billing", "SI" and "BL" ---
    ("general:update-summary",  Category.GENERAL, re.compile(r"\bUPDATE SUMMARY\b", re.I)),
    ("general:berthing",        Category.GENERAL, re.compile(r"\bBERTHING REPORT\b", re.I)),
    ("general:rpa-bot",         Category.GENERAL, re.compile(r"^_RPA_|\bRPA\b.*PROCESS COMPLETED", re.I)),
    ("general:sla-reminder",    Category.GENERAL, re.compile(r"^_REMINDER_|\bSUBMIT SI & AED\b", re.I)),
    ("general:outstanding-bl",  Category.GENERAL, re.compile(r"LIST OF OUTSTANDING BL|PENDING BL RELEASE", re.I)),
    ("general:hr-admin",        Category.GENERAL, re.compile(
        r"TIME OFF REQUEST|WELCOMING THE NEW YEAR|MISS CONNECTION|DELIVERY PLANNING|"
        r"^_APPROVAL REQUIRED_", re.I)),

    # --- BL_COMPARISON ---
    ("bl:confirm-docs",         Category.BL_COMPARISON, re.compile(r"\bTO CONFIRM DOCS\b", re.I)),
    ("bl:request-draft",        Category.BL_COMPARISON, re.compile(r"\bREQUEST BL DRAFT\b", re.I)),
    ("bl:draft-amend",          Category.BL_COMPARISON, re.compile(r"\bDRAFT BL\b|\bAMEND BL\b", re.I)),
    # coded desk subject: "AIE - JEBEL ALI_UAE - MSC(MEDUUD104332) - 5RSG-00133 - ..."
    ("bl:coded-desk",           Category.BL_COMPARISON, re.compile(
        r"^(RE_\s*)?(AIE|AFPTME|AFRT|AFEMY)\s*-\s*.+-\s*\w+\(", re.I)),

    # --- SI_REQUEST ---
    ("si:request",              Category.SI_REQUEST, re.compile(
        r"\bREQUEST SI\b|\bCUST SI\b|\bSI NEEDED\b|\bLATEST SI\b", re.I)),
    # coded SI subject: "SI - SIN706562729 - DIRECT(PIL) - 5RCY-72046 - ..."
    ("si:coded",                Category.SI_REQUEST, re.compile(r"^(RE_\s*)?SI\s*-\s*\S+\s*-\s*DIRECT\(", re.I)),

    # --- INVOICE_QUERY (after GENERAL, see the note above) ---
    ("invoice:cancel",          Category.INVOICE_QUERY, re.compile(r"CANCEL INVOICE", re.I)),
    ("invoice:billing-gr",      Category.INVOICE_QUERY, re.compile(r"\bBILLING\b.*\bMISSING GR\b", re.I)),
    ("invoice:charges",         Category.INVOICE_QUERY, re.compile(
        r"LOCAL CHARGES|TELEX RELEASE CHARGES|D ?& ?D CHARGES|DETENTION|TOTAL FREIGHT", re.I)),
    ("invoice:generic",         Category.INVOICE_QUERY, re.compile(r"\bINVOICE\b|\bBILLING\b", re.I)),
)

# Body templates, used when the subject decides nothing.
BODY_RULES: tuple[tuple[str, Category, re.Pattern[str]], ...] = (
    ("body:si-instruction",     Category.SI_REQUEST, re.compile(
        r"PLEASE FIND SHIPPING INSTRUCTION|DOCUMENTS REQUIRED:", re.I)),
    ("body:bl-check",           Category.BL_COMPARISON, re.compile(
        r"DRAFT BILL OF LADING|DRAFT BL|CHECK THE DRAFT BL|SI AND (THE )?DRAFT BL|"
        r"VERIFY THE BL MATCHES THE SI", re.I)),
    ("body:invoice",            Category.INVOICE_QUERY, re.compile(
        r"GR IS STILL MISSING|CANCEL INVOICE|QUERY ON INVOICE|D&D|DETENTION CHARGES|"
        r"LOCAL CHARGE|THC", re.I)),
    ("body:general-bot",        Category.GENERAL, re.compile(
        r"AUTOMATED NOTIFICATION|RPA BOT|BERTHING REPORT|UPDATE SUMMARY|"
        r"OUTSTANDING BL|NO ACTION REQUIRED", re.I)),
)

# Kept for backwards compatibility with anything that imported RULES.
RULES: dict[Category, tuple[str, ...]] = {
    category: tuple(pattern.pattern for _name, cat, pattern in SUBJECT_RULES if cat is category)
    for category in Category
}


def classify_with_evidence(email: EmailRecord) -> tuple[Category, DecidedBy, str]:
    """Classify and say which rule decided it — the review screen shows the reason.

    Returns (category, decided_by, rule_name). `rule_name` is "llm" when no rule fired
    and Claude was asked, or "default" when even that was unavailable.
    """
    subject = email.subject or ""
    body = email.body or ""
    sender = email.sender or ""

    # 1. Spam, before anything else: a phishing mail may quote a real subject line.
    if SPAM_SENDER.search(sender):
        return Category.SPAM, DecidedBy.RULE, "spam:sender-domain"
    if SPAM_CONTENT.search(subject) or SPAM_CONTENT.search(body):
        return Category.SPAM, DecidedBy.RULE, "spam:content"

    # 2. An attachment is decisive — no other category ever carries one.
    if email.attachments:
        return Category.BL_COMPARISON, DecidedBy.RULE, "bl:has-attachment"

    # 3. Subject templates, in the order defined above.
    for name, category, pattern in SUBJECT_RULES:
        if pattern.search(subject):
            return category, DecidedBy.RULE, name

    # 4. Body templates, when the subject was not conclusive.
    for name, category, pattern in BODY_RULES:
        if pattern.search(body):
            return category, DecidedBy.RULE, name

    # 5. Nothing fired — ask Claude. Falls back to GENERAL (the largest residual
    #    class) if the LLM is unavailable, so the pipeline never stalls on a key.
    from .extractor.llm_extract import classify_email

    category = classify_email(subject, body)
    if category is not None:
        return category, DecidedBy.LLM, "llm"
    return Category.GENERAL, DecidedBy.RULE, "default"


def classify(email: EmailRecord) -> tuple[Category, DecidedBy]:
    """Stage 1 contract: (category, how it was decided)."""
    category, decided_by, _rule = classify_with_evidence(email)
    return category, decided_by


# ---------------------------------------------------------------------------
# Attachment expectation — read by the pipeline, not by stage 1
# ---------------------------------------------------------------------------

# "Please compare the SI and draft BL ... (attachments appear to have been dropped)"
_CLAIMS_ATTACHMENTS = re.compile(
    r"PLEASE (FIND )?ATTACHED|ATTACHED (ARE|IS|HEREWITH)|PLEASE COMPARE THE SI|"
    r"ATTACHMENTS? (APPEAR|HAVE BEEN|WAS|WERE)|STILL MISSING|HAVE BEEN DROPPED|"
    r"KINDLY (CHECK|CONFIRM) THE (ATTACHED|DOCUMENTS)", re.IGNORECASE)

# "Please assist to send the draft BL for <booking> for checking asap." — nothing is
# attached and nothing is supposed to be: the sender is asking US for the document.
_REQUESTS_DOCUMENT = re.compile(
    r"ASSIST TO SEND|PLEASE SEND THE DRAFT|REVERT WITH (THE )?DRAFT|ONCE AVAILABLE|"
    r"KINDLY (SEND|PROVIDE|ARRANGE)", re.IGNORECASE)


def expects_attachments(email: EmailRecord) -> bool:
    """Does this comparison email claim documents that are not there?

    The distinction the reliability axis turns on. 94 BL_COMPARISON emails arrive with
    no attachment, and only 3 of them are a genuine `missing_attachment` escalation:

        91x  "Please assist to send the draft BL for <booking> for checking asap."
             -> nothing to compare YET. Not an error, not an escalation.
         3x  "Please compare the SI and draft BL for <booking> and confirm
              (attachments appear to have been dropped)."
             -> the sender believes they attached documents. A human must chase them.

    Escalating all 94 costs nothing on the final score (the scorer reads only
    category / has_defect / defect_fields) but drops escalation precision from 1.00 to
    0.18 on the reliability axis the judges read, and it is the "false alarm" the use
    case explicitly asks us not to create.
    """
    body = email.body or ""
    if _CLAIMS_ATTACHMENTS.search(body):
        return True
    return bool(email.attachments) and not _REQUESTS_DOCUMENT.search(body)


__all__ = ["RULES", "SUBJECT_RULES", "BODY_RULES", "classify",
           "classify_with_evidence", "expects_attachments"]
