"""
Settings, loaded once from the environment (and from .env when present).

Nothing else in the codebase reads os.environ directly, so there is one place to look
when a key is "set but ignored". `.env` is gitignored and never shipped: with no key
the whole system stays on the deterministic path and says so.
"""

from __future__ import annotations

import json
import logging
import os
import threading
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


# ---------------------------------------------------------------------------
# The LLM switch
# ---------------------------------------------------------------------------
# Claude costs money and the sample inbox does not need it: the rules score 1.0000 on
# their own. So the LLM is OFF by default and stays off until somebody deliberately
# turns it on — from the header of the review screen, without a redeploy or an ssh
# session. A public URL with a live key behind it is a way to donate a budget to a
# crawler.
#
# Precedence, highest first:
#   1. the state file, which is what the toggle writes (survives a restart)
#   2. SDOC_LLM=on|off in the environment (what a deployment sets as its default)
#   3. off
#
# Turning it on still cannot spend without bound: LLM_MAX_CALLS caps the calls per run.

_state_lock = threading.Lock()


def state_file() -> Path:
    """Where the runtime toggle is persisted. Mount this path in Docker to keep the
    setting across container restarts."""
    return Path(os.environ.get("SDOC_STATE_FILE", PROJECT_ROOT / ".sdoc-state.json"))


def _read_state() -> dict:
    path = state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def llm_enabled() -> bool:
    """Is Claude allowed to be called at all right now?"""
    state = _read_state()
    if "llm_enabled" in state:
        return bool(state["llm_enabled"])
    return os.environ.get("SDOC_LLM", "off").strip().lower() in {"on", "1", "true", "yes"}


def llm_setting_source() -> str:
    """Where the current value came from — shown in the UI so nobody wonders."""
    if "llm_enabled" in _read_state():
        return "switched here"
    if os.environ.get("SDOC_LLM"):
        return "SDOC_LLM in the environment"
    return "default (off)"


def set_llm_enabled(enabled: bool) -> bool:
    """Flip the switch and remember it. Returns the new value."""
    with _state_lock:
        state = _read_state()
        state["llm_enabled"] = bool(enabled)
        path = state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError as exc:
            # A read-only or wrong-owned path is not a reason to fail the request, but
            # it MUST be loud: the switch then only lasts until the process restarts,
            # and silently forgetting that Claude was turned off is how a budget goes.
            logging.getLogger(__name__).warning(
                "could not persist the Claude switch to %s (%s). It will hold until "
                "this process restarts and then fall back to SDOC_LLM. In Docker this "
                "means the /state volume is not writable by the container user.",
                path, exc)
            os.environ["SDOC_LLM"] = "on" if enabled else "off"
    return bool(enabled)


# Rough per-million-token prices, used only to show what a run cost. Override when the
# model or the pricing changes — a wrong number here is worse than none.
def token_prices() -> tuple[float, float]:
    """(input $/MTok, output $/MTok)"""
    try:
        return (float(os.environ.get("LLM_PRICE_IN", "3.0")),
                float(os.environ.get("LLM_PRICE_OUT", "15.0")))
    except ValueError:
        return (3.0, 15.0)


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


def version() -> str:
    """The commit this build came from, baked in at image build time. Reported on
    /health so a deployment can be confirmed from outside — the server pulls its own
    updates, so "did my change land?" has to be answerable over HTTP."""
    return os.environ.get("SDOC_VERSION", "dev")


def data_dir() -> str:
    """Where the inbox lives: a folder holding inbox/ and attachments/.

    Point this at a different dataset to run against it — that is all it takes, and it
    is how the service is aimed at a new drop of emails without a code change:

        DATA_DIR=/srv/inbox-2026-02 uvicorn src.api.main:app
        python -m src.pipeline --data-dir /srv/inbox-2026-02

    DATA_SOURCE is accepted as an alias because .env.example used to spell it that way.
    """
    return (os.environ.get("DATA_DIR")
            or os.environ.get("DATA_SOURCE")
            or "data")


__all__ = ["PROJECT_ROOT", "api_key", "model", "max_llm_calls", "data_dir",
           "version", "state_file", "llm_enabled", "llm_setting_source", "set_llm_enabled",
           "token_prices"]
