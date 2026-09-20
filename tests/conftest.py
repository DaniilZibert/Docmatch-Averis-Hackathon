"""
Test-session setup.

The suite must be free, offline and deterministic. With a real key in .env the
pipeline's fallbacks would fire during `test_pipeline` — six vision calls on the
scanned PDFs, on every run — which costs money, needs a network, and makes the
assertions depend on a model's output.

So the LLM is switched off for the whole session, before src is imported. The
deterministic path is what these tests are about; the LLM paths are exercised
separately by `scripts/llm_smoke.py`, which is explicit about spending.
"""

from __future__ import annotations

import os

# Must happen before `src.config` reads the environment.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_MAX_CALLS"] = "0"
os.environ["SDOC_LLM"] = "off"
# Never let the suite read the working cache. A cached vision answer would make a
# scanned PDF look readable and quietly turn a deliberate NEEDS_REVIEW into a pass,
# depending on whether somebody had run the pipeline with the AI on beforehand.
os.environ["SDOC_LLM_CACHE"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".cache-never-written")


def pytest_report_header(config):
    return "sdoc: LLM disabled for this session (rules-only, no network, no spend)"
