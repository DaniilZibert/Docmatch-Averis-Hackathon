"""
Regression tests for the label -> field mapping.

The labels below are every distinct label that appears in data/attachments/*.txt
(harvested with `grep -hoE "^[A-Za-z][^:]{1,45}:" *.txt | sort | uniq -c`). If a future
alias change starts mapping one of the NON_FIELD_LABELS, these tests catch it — that
kind of false positive silently corrupts a comparison instead of failing loudly.
"""

from __future__ import annotations

import pytest

from src.extractor.field_aliases import is_foreign_document, match_field

# Real labels from the dataset, grouped by the field they must resolve to.
REAL_LABELS: dict[str, list[str]] = {
    "shipper": ["Shipper", "SHIPPER", "Shipper (Principal or Seller)",
                "Shipper/Exporter", "Exporter", "Seller"],
    "consignee": ["Consignee", "CONSIGNEE", "Consignee (Non-Negotiable)",
                  "To the Order of"],
    "notify_party": ["Notify", "Notify Party", "NOTIFY PARTY",
                     "Notify Party/Intermediate Consignee"],
    "port_of_loading": ["Port of Loading", "PORT OF LOADING", "POL",
                        "Port of Loading (POL)", "Load Port"],
    "port_of_discharge": ["Port of Discharge", "PORT OF DISCHARGE", "POD",
                          "Port of Discharge (POD)", "Discharge Port"],
    "container_count": ["No. of Containers", "No. of Containers or Packages",
                        "Total Containers", "Container Count"],
    "gross_weight_kg": ["Gross Wt (kgs)", "GROSS WEIGHT", "Gross Weight (KG)"],
}

# Labels that exist in the documents but are NOT one of the seven compared fields.
NON_FIELD_LABELS: list[str] = [
    "Freight", "OC No.", "HS Code", "Description of Goods", "Booking Reference",
    "Booking Ref", "Vessel Name", "Voyage", "Commodity", "Voy. No", "Vessel", "Voy.",
    "BOOKING NO.", "Description", "Ocean Vessel", "Voyage No.",
    "Export Carrier (vessel, voyage)", "Kinds of Packages; Description of Goods",
    "Booking No.", "Bill of Lading No.", "BL No.", "B/L No.", "B/L NUMBER",
    "NET WEIGHT", "Issuing Authority", "Country of Origin", "Certificate No.",
    "Total Amount", "Payment Terms",
]


@pytest.mark.parametrize("field,labels", REAL_LABELS.items())
def test_every_real_label_resolves(field: str, labels: list[str]):
    for label in labels:
        assert match_field(label) == field, f"{label!r} should map to {field}"


@pytest.mark.parametrize("label", NON_FIELD_LABELS)
def test_non_field_labels_stay_unmapped(label: str):
    assert match_field(label) is None, f"{label!r} must not map to a compared field"


def test_net_weight_is_never_gross_weight():
    """The one that would quietly poison a weight comparison."""
    for spelling in ("NET WEIGHT", "Net Weight", "net wt", "Net Wt (kgs)"):
        assert match_field(spelling) is None


def test_labels_are_case_and_spacing_insensitive():
    assert match_field("  gross   wt (kgs) : ") == "gross_weight_kg"
    assert match_field("PORT OF LOADING") == match_field("port of loading")


def test_certificate_of_origin_is_recognised_as_foreign():
    assert is_foreign_document(["Certificate No.", "Issuing Authority",
                                "Country of Origin", "Exporter"]) is True


def test_a_real_shipping_instruction_is_not_foreign():
    assert is_foreign_document(["Shipper", "Consignee", "Notify", "Port of Loading (POL)",
                                "POD", "Total Containers", "Gross Wt (kgs)"]) is False
