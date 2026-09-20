"""
Settings, loaded once from the environment (and from .env when present).

Nothing else in the codebase reads os.environ directly, so there is one place to look
when a key is "set but ignored". `.env` is gitignored and never shipped: with no key
the whole system stays on the deterministic path and says so.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Read .env into the environment if python-dotenv is installed.

    Falls back to a tiny parser so a missing dev dependency cannot be the reason a key
    silently does nothing. Existing environment variables always win, so CI and Docker
    can override the file.
    """
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
        return
    except ImportError:
        pass
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return "" if key.startswith("sk-ant-...") else key       # the .env.example placeholder


def model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def max_llm_calls() -> int:
    """Hard cap on Claude calls per process. 0 disables the LLM entirely.

    The rules resolve the sample inbox on their own, so a run that reaches this cap is
    a run against unfamiliar data. The cap is what stops an accidental full-inbox LLM
    pass from spending a limited budget in one command.
    """
    try:
        return int(os.environ.get("LLM_MAX_CALLS", "40"))
    except ValueError:
        return 40


def data_source() -> str:
    return os.environ.get("DATA_SOURCE", "data")


__all__ = ["PROJECT_ROOT", "api_key", "model", "max_llm_calls", "data_source"]
