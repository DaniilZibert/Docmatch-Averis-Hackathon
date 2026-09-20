"""
Stage 1. Worth 30% of the score on macro-F1, which weighs all five categories equally.

The tests below encode the two things that are easy to get wrong: the rule ORDER
(GENERAL templates contain "Billing", "SI" and "BL") and the attachment-expectation
split that the reliability axis turns on.
"""

from __future__ import annotations

import pytest

from src.classifier import classify, classify_with_evidence, expects_attachments
from src.models import Category, EmailRecord


def email(subject: str = "", body: str = "", sender: str = "a@b.com",
          attachments: list[str] | None = None) -> EmailRecord:
    return EmailRecord(email_id="email_x", sender=sender, subject=subject, body=body,
                       attachments=attachments or [])


@pytest.mark.parametrize("subject,expected", [
    ("TO CONFIRM DOCS _ 5RSG-00133 _ CALLAO_PERU _ MOORIM SP CO., LTD _ MEDUUD104332",
     Category.BL_COMPARISON),
    ("REQUEST BL DRAFT _ PO 26067_ COATED IVORY BOARD__138MT", Category.BL_COMPARISON),
    ("RE_ Draft BL INDO SUKSES 65 V.51NW1 SINGAPORE - amend BL 057", Category.BL_COMPARISON),
    ("AIE - JEBEL ALI_UAE - MSC(MEDUUD104332) - 5RSG-00133 - 5250070084 - ROXCEL TRADING GMBH - OA",
     Category.BL_COMPARISON),
    ("REQUEST SI _ 5RFR-37631 _ GDANSK_POLAND _ AL GURG STATIONERY LLC _ SIJ1051834",
     Category.SI_REQUEST),
    ("RE_ SI - SIN706562729 - DIRECT(PIL) - 5RCY-72046 - MERSIN_TURKEY - SURR BL - AFPTME - 19-Jan-26",
     Category.SI_REQUEST),
    ("CUST SI _ MEA _ 5RCY-60883 __ PO_25_4821", Category.SI_REQUEST),
    ("REQUEST TO CANCEL INVOICE -5250070084 - PACIFIC OFFICE (M) SDN BHD - 5RSG-40824",
     Category.INVOICE_QUERY),
    ("2145 RAK BILLING 5070146312 MISSING GR", Category.INVOICE_QUERY),
    ("Mill D & D charges - 6437419879", Category.INVOICE_QUERY),
    ("15_01_2026 - UPDATE SUMMARY LE HAVRE V.QI540A", Category.GENERAL),
    ("daily Berthing Report - 07 JAN 2026", Category.GENERAL),
    ("Congratulations! You have WON a $1,000 Gift Card - CLAIM NOW", Category.SPAM),
])
def test_subject_templates(subject: str, expected: Category):
    assert classify(email(subject=subject))[0] is expected


@pytest.mark.parametrize("subject", [
    "_RPA_ India HSS SD Billing Process Completed - LE HAVRE V.QI540A",   # "Billing"
    "_Reminder_Paper - Submit SI & AED_26-01-2026",                       # "SI"
    "APRIL PAPER - List of Outstanding BL (BDP SG) as of 2026-01-14",     # "BL"
    "Pending BL Release 09_01_2026",                                      # "BL"
])
def test_general_templates_win_over_stray_keywords(subject: str):
    """These are the lexical traps. A keyword rule alone files every one of them wrong,
    and GENERAL is 1/5 of macro-F1 whatever its size."""
    assert classify(email(subject=subject))[0] is Category.GENERAL


def test_an_attachment_decides_on_its_own():
    """All 126 emails in the inbox that carry an attachment are BL_COMPARISON, and no
    other category ever attaches a file."""
    record = email(subject="anything at all",
                   attachments=["attachments/email_x_SI.txt", "attachments/email_x_BL.txt"])
    category, _decided_by, rule = classify_with_evidence(record)
    assert category is Category.BL_COMPARISON
    assert rule == "bl:has-attachment"


def test_spam_is_caught_by_sender_even_with_a_plausible_subject():
    record = email(subject="Re: Invoice payment - kindly confirm your bank details",
                   sender="winner@prize-claims.info")
    assert classify(record)[0] is Category.SPAM


def test_everything_is_decided_by_a_rule_not_the_llm():
    """A run that needs the LLM for a template we already know is a run that costs
    money for nothing. `decided_by` is reported by the organizers' scorer."""
    record = email(subject="TO CONFIRM DOCS _ 5RSG-00133 _ CALLAO_PERU")
    assert classify(record)[1].value == "rule"


# --- the attachment-expectation split --------------------------------------

def test_asking_us_to_send_a_bl_is_not_a_missing_attachment():
    """91 of the 94 comparison emails with no attachment look like this. Escalating
    them would drop escalation precision from 1.00 to 0.18."""
    record = email(subject="TO CONFIRM DOCS _ 5RSG-00133",
                   body="Dear Hari,\n\nPlease assist to send the draft BL for "
                        "SIN832764835 for checking asap.\n\nThank you.")
    assert expects_attachments(record) is False


def test_documents_promised_but_absent_is_a_missing_attachment():
    """The other 3. The sender believes they attached them; a human has to chase."""
    record = email(subject="TO CONFIRM DOCS _ 5RSG-00133",
                   body="Dear Team,\n\nPlease compare the SI and draft BL for "
                        "070500263211 and confirm (attachments appear to have been "
                        "dropped). Thank you.")
    assert expects_attachments(record) is True
