"""
Golden tests for the four format extractors, against real files in data/attachments.

One fixture per format, chosen for what it proves:

    email_004_SI.txt / _BL.txt   the label-synonym case from the use case
    email_055_SI.xlsx / _BL.docx an xlsx/docx pair that MUST compare equal
    email_059_SI.pdf             the PDF container-table trap
    email_208_SI.pdf             the collided-glyph label
    email_517_SI.txt             blank placeholders
    email_502_BL.txt             a Packing List sent instead of a BL
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.extractor import extract
from src.models import COMPARED_FIELDS, DocType

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def read(name: str, doc_type: DocType = DocType.SI):
    return extract(f"attachments/{name}", DATA_DIR, name.split("_SI")[0].split("_BL")[0],
                   doc_type)


# --- plain text ------------------------------------------------------------

def test_txt_si_reads_all_seven_fields():
    document = read("email_004_SI.txt")
    assert document.present_field_count == 7
    assert document.value_of("shipper") == "APRIL FAR EAST (M) SDN BHD"
    assert document.value_of("consignee") == "EAST BRIGHT FZ-LLC"
    assert document.value_of("container_count") == 6
    assert document.value_of("gross_weight_kg") == 131058


def test_the_same_field_under_a_different_label():
    """The whole point of the use case: the BL says 'To the Order of' where the SI
    says 'Consignee (Non-Negotiable)', and 'Container Count' for 'Total Containers'."""
    si = read("email_004_SI.txt", DocType.SI)
    bl = read("email_004_BL.txt", DocType.BL)
    assert si.fields["consignee"].raw_label == "Consignee (Non-Negotiable)"
    assert bl.fields["consignee"].raw_label == "To the Order of"
    assert si.fields["container_count"].raw_label == "Total Containers"
    assert bl.fields["container_count"].raw_label == "Container Count"
    assert si.value_of("container_count") == bl.value_of("container_count") == 6


def test_the_address_line_is_not_mistaken_for_a_field():
    """The generator mutates the consignee NAME but copies the address verbatim, so an
    extractor that read addresses would mask the defect."""
    bl = read("email_004_BL.txt", DocType.BL)
    assert bl.value_of("consignee") == "UAB NOVAKOPA"          # not the address below it


def test_blank_placeholders_become_missing_not_wrong():
    document = read("email_517_SI.txt")
    assert document.value_of("port_of_loading") is None        # was "____MT"
    assert document.value_of("port_of_discharge") is None      # was "TBA"
    assert "port_of_loading" in document.missing_fields
    assert document.value_of("container_count") == 15          # the rest still read


def test_net_weight_never_lands_in_gross_weight():
    """Every missing_value SI carries 'NET WEIGHT: _______ MTS'."""
    document = read("email_519_SI.txt")
    assert document.value_of("gross_weight_kg") == 70572


# --- excel and word --------------------------------------------------------

def test_xlsx_and_docx_pair_agrees_field_for_field():
    """The xlsx SI packs 'NAME | ADDR; ADDR' and the docx BL 'NAME | ADDR | ADDR'.
    Without dropping the address both would differ on all three party fields."""
    si = read("email_055_SI.xlsx", DocType.SI)
    bl = read("email_055_BL.docx", DocType.BL)
    assert si.present_field_count == bl.present_field_count == 7
    for field in COMPARED_FIELDS:
        assert si.value_of(field) == bl.value_of(field), field


def test_bilingual_word_labels_resolve():
    bl = read("email_055_BL.docx", DocType.BL)
    assert bl.fields["gross_weight_kg"].raw_label == "Gross Wt (kgs) (毛重 KGS)"
    assert bl.fields["port_of_loading"].raw_label == "PORT OF LOADING (装货港)"


# --- pdf -------------------------------------------------------------------

def test_pdf_reads_the_total_weight_not_a_container_row():
    """The container table has a 'GROSS WEIGHT (KG)' column whose rows hold ONE
    container's weight (21,887). The shipment total is 131,322."""
    document = read("email_059_BL.pdf", DocType.BL)
    assert document.value_of("gross_weight_kg") == 131322
    assert document.value_of("container_count") == 6


def test_pdf_colon_less_labels_are_split():
    document = read("email_059_SI.pdf")
    assert document.present_field_count == 7
    assert document.value_of("port_of_loading") == "BUATAN, INDONESIA"


def test_pdf_collided_label_is_recovered():
    """A long label overruns the value column and the text layer interleaves them:
    'Notify Party/Intermediate ConsCigEnReIEeX'. Case separates the two runs."""
    document = read("email_208_SI.pdf")
    assert document.value_of("notify_party") == "CERIEX"


@pytest.mark.parametrize("line,expected", [
    ("Notify Party/Intermediate ConsCigEnReIEeX", "CERIEX"),
    ("Notify Party/Intermediate ConsKiTgPne CeO., LTD", "KTP CO., LTD"),
    ("Notify Party/Intermediate ConsNigAnGeAePPA EXPORTS", "NAGAPPA EXPORTS"),
    # found by running against a freshly generated dataset: subtracting the label tail
    # greedily breaks here, because ORIENT contains i/e/n itself and the greedy pass
    # spends the tail on the value's own letters. Case is the reliable separator.
    ("Notify Party/Intermediate ConsOigRnIEeNeT LINKS CO (LLC)", "ORIENT LINKS CO (LLC)"),
])
def test_every_known_glyph_collision_recovers(line: str, expected: str):
    from src.extractor.field_aliases import match_label_prefix
    assert match_label_prefix(line) == ("Notify Party/Intermediate Consignee", expected)


@pytest.mark.parametrize("line,label,value", [
    ("Notify Party PACIFIC OFFICE (M) SDN BHD", "Notify Party", "PACIFIC OFFICE (M) SDN BHD"),
    ("Notify CERIEX", "Notify", "CERIEX"),
    ("To the Order of EAST BRIGHT FZ-LLC", "To the Order of", "EAST BRIGHT FZ-LLC"),
    ("POL BUATAN, INDONESIA", "POL", "BUATAN, INDONESIA"),
])
def test_uncollided_lines_still_split_normally(line: str, label: str, value: str):
    """The recovery must never fire on a line that was never collided."""
    from src.extractor.field_aliases import match_label_prefix
    assert match_label_prefix(line) == (label, value)


@pytest.mark.parametrize("name", ["email_512_SI.pdf", "email_511_BL.pdf"])
def test_unreadable_pdfs_escalate_rather_than_crash(name: str):
    document = read(name, DocType.BL)
    assert document.unreadable is True
    assert document.present_field_count == 0


# --- wrong document type ---------------------------------------------------

@pytest.mark.parametrize("name", ["email_501_BL.txt", "email_502_BL.txt",
                                  "email_503_BL.txt", "email_504_BL.txt",
                                  "email_505_BL.txt"])
def test_a_substituted_document_is_flagged(name: str):
    """Invoice, Packing List and Certificate of Origin. The Packing List is the one a
    label-only heuristic misses — its labels are Shipper / Consignee / Booking Ref."""
    assert read(name, DocType.BL).wrong_doc_type is True


def test_a_real_si_is_not_flagged_as_foreign():
    assert read("email_501_SI.txt").wrong_doc_type is False


def test_a_missing_file_never_raises():
    document = extract("attachments/does_not_exist.txt", DATA_DIR, "email_x", DocType.SI)
    assert document.unreadable is True
