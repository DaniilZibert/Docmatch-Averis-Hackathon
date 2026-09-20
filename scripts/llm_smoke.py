#!/usr/bin/env python3
"""
Prove the Claude fallbacks work — on made-up data that the rules cannot handle.

This is the rehearsal for "the judges run us on their own inbox". The rules cover the
sample data completely, so nothing in a normal run ever reaches Claude; the only way to
know those paths are alive is to feed them input the rules were never written for.

    python scripts/llm_smoke.py            # ~4 calls, a few cents
    python scripts/llm_smoke.py --vision   # + one scanned page (~1 more call)

Explicit about spending on purpose: the team key has a small budget, and `pytest` is
wired to never touch it (see tests/conftest.py).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                        # noqa: E402  loads .env
from src.extractor import llm_extract                          # noqa: E402
from src.models import DocType                                 # noqa: E402

# An email in none of the shapes our subject templates know: no coded desk prefix, no
# "TO CONFIRM DOCS", no "REQUEST SI". A rule pass returns GENERAL and shrugs.
UNSEEN_EMAILS = [
    ("Kindly cross-check the enclosed carrier draft before we release",
     "Morning team, the carrier finally sent their draft. Can someone put it next to "
     "what we instructed and tell me if anything moved? Booking 070500263211.",
     "BL_COMPARISON"),
    ("Chasing the paperwork for next week's sailing",
     "Hi, we still need you to raise the instruction for the Busan box so the line can "
     "cut the bill. Details to follow from the customer.",
     "SI_REQUEST"),
]

# A document with labels we have no alias for, in a layout the parser cannot see.
UNSEEN_DOCUMENT = """\
CARRIER BOOKING CONFIRMATION / SHIPPING NOTE
Ref 5RAE-00543

Party sending the goods ....... ASIA PACIFIC PAPERBOARD TRADING PTE LTD
                                80 RAFFLES PLACE, SINGAPORE 048624
Goods are for .................. ROXCEL TRADING GMBH
Advise on arrival .............. ROXCEL TRADING GMBH
Taking on board at ............. PORT KLANG (WESTPORT), MALAYSIA
Final sea leg ends at .......... KOPER, SLOVENIA
Boxes in this lot .............. four x 40'HC
Weight of goods and boxes ...... 88,412 kilos
Weight of goods alone .......... 81,000 kilos
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vision", action="store_true", help="also test a scanned page")
    args = ap.parse_args()

    if not llm_extract.llm_available():
        print("No API key — nothing to test. The pipeline still runs rules-only.",
              file=sys.stderr)
        return 1
    print(f"model {config.model()} · budget {config.max_llm_calls()} calls\n")

    failures = 0

    print("1. classification of emails our templates do not cover")
    for subject, body, expected in UNSEEN_EMAILS:
        got = llm_extract.classify_email(subject, body)
        ok = got is not None and got.value == expected
        failures += not ok
        print(f"   [{'ok ' if ok else 'FAIL'}] {subject[:52]:<52} -> "
              f"{got.value if got else None} (want {expected})")

    print("\n2. extraction from a layout with no aliases and no 'Label: value' lines")
    document = llm_extract.extract_from_text(UNSEEN_DOCUMENT, "email_smoke", DocType.SI,
                                             "smoke/unseen.txt")
    if document is None:
        print("   [FAIL] Claude returned nothing")
        failures += 1
    else:
        expected = {
            "shipper": "ASIA PACIFIC PAPERBOARD TRADING PTE LTD",
            "consignee": "ROXCEL TRADING GMBH",
            "notify_party": "ROXCEL TRADING GMBH",
            "container_count": 4,
            "gross_weight_kg": 88412,          # NOT the 81,000 net weight
        }
        for name, want in expected.items():
            got = document.value_of(name)
            ok = str(got).upper() == str(want).upper()
            failures += not ok
            print(f"   [{'ok ' if ok else 'FAIL'}] {name:<18} {got!r} (want {want!r})")
        print(f"   read {document.present_field_count}/7 fields")

    if args.vision:
        print("\n3. vision on a scanned page with no text layer")
        from src.extractor import extract
        scanned = extract("attachments/email_513_SI.pdf", "data", "email_513", DocType.SI)
        ok = scanned.present_field_count >= 5 and scanned.needs_confirmation
        failures += not ok
        print(f"   [{'ok ' if ok else 'FAIL'}] {scanned.present_field_count}/7 fields, "
              f"needs_confirmation={scanned.needs_confirmation}")
        print(f"          shipper={scanned.value_of('shipper')!r}")

    print(f"\n{llm_extract.calls_made()} Claude calls made. "
          f"{'all paths alive' if not failures else f'{failures} check(s) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
