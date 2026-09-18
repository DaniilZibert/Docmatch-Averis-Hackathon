"""
OWNER: Person A.  STUB — the Claude fallback for classification and extraction.

Use it only when the rules fall short, so most documents stay on the cheap
deterministic path:
  * extract_from_text()  — rules found fewer than MIN_FIELDS_FOR_RULES of the 7 fields
  * extract_from_image() — a PDF page with no text layer (scanned)
  * classify_email()     — the classifier has no confident rule hit

Ask for strict JSON with exactly the 7 keys of COMPARED_FIELDS, values or null; then
validate into ExtractedField(source=FieldSource.LLM or VISION). A field the model does
not find must come back null, never invented — an invented value turns a
NEEDS_REVIEW into a wrong answer and costs us on two scoring axes at once.

The API key comes from ANTHROPIC_API_KEY (.env, see .env.example).
"""

from __future__ import annotations

import os

from ..models import (COMPARED_FIELDS, Category, DocType, ExtractedDocument)

# Rules that recover at least this many of the 7 fields are trusted without the LLM.
MIN_FIELDS_FOR_RULES = 5

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

EXTRACTION_PROMPT = """You are reading one shipping document (a Shipping Instruction or a
draft Bill of Lading). Return ONLY a JSON object with exactly these keys:

  shipper, consignee, notify_party, port_of_loading, port_of_discharge,
  container_count, gross_weight_kg

Rules:
- Copy values verbatim from the document; do not normalise, translate or expand them.
- container_count and gross_weight_kg must be numbers (no units, no thousands separators).
- If the document does not state a field, use null. Never guess.
- The same field may be labelled differently ("Load Port" = port_of_loading,
  "To the Order of" = consignee). Match by meaning.
- "NET WEIGHT" is NOT gross_weight_kg.

Document:
---
{document_text}
---"""


def extract_from_text(text: str, email_id: str, doc_type: DocType,
                      source_path: str) -> ExtractedDocument:
    """TODO(Person A): one Claude call with EXTRACTION_PROMPT, parse strict JSON."""
    raise NotImplementedError("llm_extract.extract_from_text")


def extract_from_image(png_bytes: bytes, email_id: str, doc_type: DocType,
                       source_path: str) -> ExtractedDocument:
    """TODO(Person A): same prompt, image content block instead of text (vision)."""
    raise NotImplementedError("llm_extract.extract_from_image")


def classify_email(subject: str, body: str) -> Category:
    """TODO(Person A): Claude picks one of the 5 categories. Used only when no rule fires."""
    raise NotImplementedError("llm_extract.classify_email")


__all__ = ["MIN_FIELDS_FOR_RULES", "EXTRACTION_PROMPT", "COMPARED_FIELDS",
           "extract_from_text", "extract_from_image", "classify_email"]
