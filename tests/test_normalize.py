"""
Value normalisation: blanks, numbers, and how strictly two values have to agree.

The blank cases are the expensive ones. A document that writes "???" or "TBA" is
telling us it does not know, and reporting that as a MISMATCH is the false alarm the
use case explicitly warns about.
"""

from __future__ import annotations

import pytest

from src.normalize import is_blank, normalize_text, parse_number, values_match

# Every placeholder that appears in the dataset where a value should be.
BLANKS = ["???", "_______", "TBA", "TBC", "N/A", "____MT", "", "   ", "-", "n/a", "nil"]


@pytest.mark.parametrize("value", BLANKS)
def test_placeholders_are_blank(value: str):
    assert is_blank(value) is True


@pytest.mark.parametrize("value", ["SINGAPORE", "0", 0, "12", "MOORIM SP CO., LTD", 243588])
def test_real_values_are_not_blank(value):
    assert is_blank(value) is False


def test_zero_is_a_number_not_a_blank():
    """0 containers is a statement; None is the absence of one. Never conflate them."""
    assert is_blank(0) is False
    assert parse_number(0) == 0
    assert parse_number("???") is None


@pytest.mark.parametrize("raw,expected", [
    ("131,058 KG", 131058),
    ("6 x 40'HC", 6),                 # the count, never the container size
    ("12 x 20'FCL", 12),
    ("243,588", 243588),
    (243588, 243588),
    ("340,770 KG", 340770),
    ("22000", 22000),
    ("???", None),
    ("____MT", None),
    (None, None),
])
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


def test_locode_is_decoration():
    assert normalize_text("NANTONG, CHINA (CNNTG)") == normalize_text("NANTONG, CHINA")


def test_case_and_punctuation_do_not_matter():
    assert normalize_text("  east bright  fz-llc ") == normalize_text("EAST BRIGHT FZ-LLC")


def test_address_after_the_pipe_is_dropped():
    """xlsx writes 'NAME | ADDR; ADDR' and docx writes 'NAME | ADDR | ADDR' for the
    same party. Comparing the packed strings would flag every xlsx/docx pair."""
    assert (normalize_text("AL GURG STATIONERY LLC | P.O. BOX 5069; DUBAI, UAE")
            == normalize_text("AL GURG STATIONERY LLC | P.O. BOX 5069 | DUBAI, UAE"))


def test_different_companies_never_match():
    """The planted defects are real other companies, not typos. Normalisation that
    'forgives' these would cost the 50% end-to-end axis."""
    assert values_match("consignee", "EAST BRIGHT FZ-LLC", "UAB NOVAKOPA") is False
    assert values_match("shipper", "APRIL FINE PAPER TRADING",
                        "APRIL FINE PAPER TRADING (MIDDLE EAST) FZE") is False
    assert values_match("consignee", "KTP CO., LTD", "MOORIM SP CO., LTD") is False


def test_numbers_compare_as_numbers():
    assert values_match("gross_weight_kg", "131,058 KG", 131058) is True
    assert values_match("container_count", "6 x 40'HC", "6 x 20'GP") is True
    assert values_match("container_count", 3, 4) is False


def test_a_blank_never_matches_anything():
    assert values_match("port_of_loading", "TBA", "SINGAPORE") is False
    assert values_match("port_of_loading", "???", "???") is False
