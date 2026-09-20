"""
OWNER: Person A.  The Claude fallback for classification and extraction.

Used only where the deterministic path genuinely cannot answer, so most of the inbox
stays cheap and explainable:

  * extract_from_image() — a PDF page with no text layer (the scanned documents)
  * extract_from_text()  — rules recovered fewer than MIN_FIELDS_FOR_RULES of the 7
  * classify_email()     — no classification rule fired

EVERY function here degrades instead of raising. If `anthropic` is not installed, or
ANTHROPIC_API_KEY is unset, or the API errors or rate-limits, the function returns
None and the caller escalates the case to a human. That is deliberate: a hackathon
demo must survive a dead network, and an honest NEEDS_REVIEW is a correct answer while
a crash loses the other 519 emails.

A field the model does not find must come back null, never invented — an invented value
turns a NEEDS_REVIEW into a wrong answer and costs us on two scoring axes at once.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from pathlib import Path

from .. import config
from ..models import (COMPARED_FIELDS, NUMERIC_FIELDS, Category, DocType,
                      ExtractedDocument, ExtractedField, FieldSource)
from ..normalize import is_blank, parse_number

log = logging.getLogger(__name__)

# Rules that recover at least this many of the 7 fields are trusted without the LLM.
# Below it, _common.build_document hands the document text to Claude instead of
# declaring it unreadable — the path that matters when the layout is one we have never
# seen, which is exactly what a judge's own data would be.
MIN_FIELDS_FOR_RULES = 5

MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# Response cache
# ---------------------------------------------------------------------------
# Every call this module makes is a pure function of bytes that do not change: the six
# image-only PDFs are the same six files on every run, a document's text is the same
# text, an email's subject and body are fixed. So the answer is cached on disk, keyed by
# a hash of the model and the exact request.
#
# That is worth more than it looks. The prototype has to be publicly accessible, and
# POST /run is a button anyone can press; with the AI on, each press used to cost six
# vision calls. Cached, the first run pays and every run after it is free — so somebody
# hammering the button costs nothing, and we did not have to take the button away from
# them to achieve it.
#
# It also makes the demo honest: the run summary still reports the calls that were
# actually made, so a cached run shows zero rather than pretending to have worked.

_cache_hits = 0


def cache_dir() -> Path:
    d = Path(os.environ.get("SDOC_LLM_CACHE", config.PROJECT_ROOT / ".llm-cache"))
    return d


def _cache_key(content, max_tokens: int) -> str:
    """A stable hash of everything that could change the answer."""
    h = hashlib.sha256()
    h.update(config.model().encode())
    h.update(str(max_tokens).encode())
    if isinstance(content, str):
        h.update(content.encode())
    else:                                    # a list of content blocks, images included
        for block in content:
            h.update(json.dumps(block, sort_keys=True, default=str).encode())
    return h.hexdigest()


def _cache_get(key: str) -> str | None:
    path = cache_dir() / f"{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["text"]
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def _cache_put(key: str, text: str) -> None:
    try:
        d = cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{key}.json").write_text(json.dumps({"text": text}), encoding="utf-8")
    except OSError as exc:                   # a read-only cache is a slow day, not a bug
        log.debug("could not write the LLM cache: %s", exc)


def cache_hits() -> int:
    return _cache_hits


# Spend guard. Every call goes through _ask, which stops when the switch is off or the
# budget is gone. Token counts are kept so a run can report what it actually cost.
_calls_made = 0
_tokens_in = 0
_tokens_out = 0
_warned_over_budget = False

EXTRACTION_PROMPT = """You are reading one shipping document (a Shipping Instruction or a
draft Bill of Lading). Return ONLY a JSON object with exactly these keys:

  shipper, consignee, notify_party, port_of_loading, port_of_discharge,
  container_count, gross_weight_kg

Rules:
- Copy values verbatim from the document; do not normalise, translate or expand them.
- For shipper / consignee / notify_party return the COMPANY NAME only, not its address.
- container_count and gross_weight_kg must be numbers (no units, no thousands separators).
  container_count is the number of containers ("6 x 40'HC" -> 6).
  gross_weight_kg is the TOTAL for the shipment, not one container's line in a table.
- If the document does not state a field, or states a placeholder ("???", "TBA", "N/A",
  "_____"), use null. Never guess.
- The same field may be labelled differently ("Load Port" = port_of_loading,
  "To the Order of" = consignee). Match by meaning.
- "NET WEIGHT" is NOT gross_weight_kg.

Document:
---
{document_text}
---"""

CLASSIFICATION_PROMPT = """Classify this shipping-operations email into exactly one category.

BL_COMPARISON  - asks someone to check/confirm a draft Bill of Lading against a
                 Shipping Instruction, or to produce a draft BL for checking.
SI_REQUEST     - asks for a Shipping Instruction to be prepared or sent, or supplies
                 the SI details so a booking can be made.
INVOICE_QUERY  - about an invoice, billing, freight, local/detention charges, GR.
GENERAL        - operational notices: berthing reports, vessel update summaries, bot
                 notifications, SLA reminders, HR and office announcements.
SPAM           - marketing, phishing, prize or parcel-fee scams.

Answer with the category name and nothing else.

Subject: {subject}

Body:
{body}"""


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

_client = None
_client_failed = False


def calls_made() -> int:
    """How many Claude calls this process has made. Printed in the run summary so a
    run's cost is visible rather than discovered on the invoice."""
    return _calls_made


def usage() -> dict:
    """What has been spent: this process, and cumulatively across all of them.

    The estimate uses LLM_PRICE_IN / LLM_PRICE_OUT (see config.token_prices). It is a
    guide for deciding whether to leave the switch on, not an invoice.
    """
    price_in, price_out = config.token_prices()
    cost = (_tokens_in / 1_000_000) * price_in + (_tokens_out / 1_000_000) * price_out
    total = config.spent()
    return {"calls": _calls_made, "cache_hits": _cache_hits,
            "tokens_in": _tokens_in, "tokens_out": _tokens_out,
            "estimated_usd": round(cost, 4),
            "total_calls": total["calls"], "total_usd": total["usd"],
            "cap_usd": config.spend_cap_usd(),
            "cap_reached": config.cap_reached()}


def reset_budget() -> None:
    """Start the call budget over — used by long-lived processes like the API.
    The cache is deliberately NOT cleared: it is what makes a re-run free."""
    global _calls_made, _warned_over_budget, _cache_hits
    _calls_made = 0
    _cache_hits = 0
    _warned_over_budget = False


def _get_client():
    """The Anthropic client, or None when the LLM path is unavailable.

    Cached, including the failure: we must not retry an import or a missing key 520
    times in one run.
    """
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client

    if not config.llm_enabled():
        return None

    api_key = config.api_key()
    if not api_key:
        log.info("ANTHROPIC_API_KEY is not set — running rules-only; "
                 "anything the rules cannot decide escalates to a human.")
        _client_failed = True
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("the anthropic package is not installed — running rules-only.")
        _client_failed = True
        return None

    try:
        _client = anthropic.Anthropic(api_key=api_key)
    except Exception as exc:
        log.warning("could not create the Anthropic client (%s) — running rules-only.", exc)
        _client_failed = True
        return None
    return _client


def llm_available() -> bool:
    """True when a Claude call would actually be attempted. Reported in the run summary
    so a rules-only run is never silently mistaken for a hybrid one."""
    return _get_client() is not None


def llm_status() -> dict:
    """Everything the UI needs to show about the switch and what it has cost."""
    has_key = bool(config.api_key())
    enabled = config.llm_enabled()          # already false once the cap is reached
    return {
        "enabled": enabled,
        "has_key": has_key,
        "available": enabled and has_key and _get_client() is not None,
        "source": config.llm_setting_source(),
        "model": config.model(),
        "budget": config.max_llm_calls(),
        **usage(),
    }


def forget_client() -> None:
    """Drop the cached client so the next call re-reads the switch and the key.
    Called when the switch is flipped at runtime."""
    global _client, _client_failed
    _client = None
    _client_failed = False


def _ask(content, *, max_tokens: int = MAX_TOKENS) -> str | None:
    """One Claude call. Returns the text, or None on any failure or once the budget
    for this process is spent."""
    global _calls_made, _cache_hits

    # The cache is checked only when the AI is switched ON. "Off" has to mean no
    # AI-derived output at all, or two things break: the rules-only column of the
    # ablation table would quietly contain vision results while reporting zero calls,
    # and nobody could ever measure the deterministic path honestly again. The cache
    # exists to stop a second run costing money, not to smuggle answers past the switch.
    if not config.llm_enabled():
        log.info("the AI switch is off — running rules-only. Turn it on from the header "
                 "of the review screen, or set SDOC_LLM=on.")
        return None

    key = _cache_key(content, max_tokens)
    cached = _cache_get(key)
    if cached is not None:
        _cache_hits += 1
        return cached

    client = _get_client()
    if client is None:
        return None

    budget = config.max_llm_calls()
    if _calls_made >= budget:
        global _warned_over_budget
        if not _warned_over_budget:
            _warned_over_budget = True             # a refusal is not a call; say it once
            log.warning("LLM call budget of %d reached — the rest of this run stays on "
                        "the deterministic path and escalates what it cannot decide. "
                        "Raise LLM_MAX_CALLS if that is intended.", budget)
        return None
    _calls_made += 1

    try:
        message = client.messages.create(
            model=config.model(),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        global _tokens_in, _tokens_out
        usage_block = getattr(message, "usage", None)
        if usage_block is not None:
            tin = getattr(usage_block, "input_tokens", 0) or 0
            tout = getattr(usage_block, "output_tokens", 0) or 0
            _tokens_in += tin
            _tokens_out += tout
            # Write it to the persistent ledger immediately, not at the end of the run.
            # A process that is killed mid-run still spent the money, and a ledger that
            # only updates on a clean exit is a ledger that undercounts exactly when it
            # matters.
            price_in, price_out = config.token_prices()
            cost = (tin / 1_000_000) * price_in + (tout / 1_000_000) * price_out
            total = config.record_spend(1, cost)
            if total["usd"] >= config.spend_cap_usd():
                log.warning("cumulative spend cap of $%.2f reached ($%.2f over %d calls) "
                            "— the AI has switched itself off and will stay off until "
                            "somebody raises LLM_SPEND_CAP_USD or clears the ledger.",
                            config.spend_cap_usd(), total["usd"], total["calls"])
        text = "".join(block.text for block in message.content if block.type == "text")
        _cache_put(key, text)
        return text
    except Exception as exc:
        log.warning("Claude call failed (%s: %s) — falling back to escalation.",
                    type(exc).__name__, exc)
        return None


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _document_from_json(raw: str | None, email_id: str, doc_type: DocType,
                        source_path: str, source: FieldSource) -> ExtractedDocument | None:
    """Validate the model's JSON into an ExtractedDocument. None if unusable."""
    if not raw:
        return None
    match = _JSON_RE.search(raw)
    if not match:
        log.warning("Claude returned no JSON object for %s", source_path)
        return None
    try:
        payload = json.loads(match.group())
    except json.JSONDecodeError:
        log.warning("Claude returned invalid JSON for %s", source_path)
        return None
    if not isinstance(payload, dict):
        return None

    fields: dict[str, ExtractedField] = {}
    for name in COMPARED_FIELDS:
        value = payload.get(name)
        if value is None or is_blank(value):
            continue                       # absent stays absent — never invent one
        if name in NUMERIC_FIELDS:
            value = parse_number(value)
            if value is None:
                continue
        else:
            value = str(value).strip() or None
            if value is None:
                continue
        fields[name] = ExtractedField(value=value, confidence=0.8, source=source,
                                      raw_label=f"{source.value}:{name}")

    if not fields:
        return None
    return ExtractedDocument(email_id=email_id, doc_type=doc_type,
                             source_path=source_path, fields=fields,
                             notes=f"extracted by Claude ({source.value})")


def extract_from_text(text: str, email_id: str, doc_type: DocType,
                      source_path: str) -> ExtractedDocument | None:
    """Claude reads a document whose layout the rules could not parse."""
    raw = _ask(EXTRACTION_PROMPT.format(document_text=text[:20000]))
    return _document_from_json(raw, email_id, doc_type, source_path, FieldSource.LLM)


def extract_from_image(png_bytes: bytes, email_id: str, doc_type: DocType,
                       source_path: str) -> ExtractedDocument | None:
    """Claude reads a scanned page. The "Scanned documents" advanced challenge."""
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(png_bytes).decode()}},
        {"type": "text", "text": EXTRACTION_PROMPT.format(
            document_text="(the document is the attached image)")},
    ]
    raw = _ask(content)
    return _document_from_json(raw, email_id, doc_type, source_path, FieldSource.VISION)


def classify_email(subject: str, body: str) -> Category | None:
    """Claude picks one of the 5 categories. Used only when no rule fires.

    Returns None when the LLM is unavailable or answers with something that is not a
    category — the caller then falls back to a safe default rather than crashing.
    """
    raw = _ask(CLASSIFICATION_PROMPT.format(subject=subject[:500], body=body[:4000]),
               max_tokens=16)
    if not raw:
        return None
    answer = raw.strip().upper()
    for category in Category:
        if category.value in answer:
            return category
    log.warning("Claude returned an unknown category: %r", raw[:80])
    return None


__all__ = ["MIN_FIELDS_FOR_RULES", "EXTRACTION_PROMPT", "CLASSIFICATION_PROMPT",
           "COMPARED_FIELDS", "llm_available", "llm_status", "calls_made", "usage",
           "reset_budget", "forget_client", "cache_dir", "cache_hits",
           "extract_from_text", "extract_from_image",
           "classify_email"]
