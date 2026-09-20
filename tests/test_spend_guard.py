"""
Everything that stands between a public URL and an empty API budget.

The demo is required to be publicly accessible, and it will eventually run with a funded
key behind it. These tests are the arithmetic of why that is safe.
"""

from __future__ import annotations

import pytest

from src import config


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SDOC_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.delenv("SDOC_LLM", raising=False)
    monkeypatch.delenv("SDOC_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("LLM_SPEND_CAP_USD", "2.50")
    yield


# --- the cumulative ceiling ------------------------------------------------

def test_spend_accumulates_across_calls():
    assert config.spent() == {"calls": 0, "usd": 0.0}
    config.record_spend(1, 0.011)
    config.record_spend(1, 0.011)
    assert config.spent()["calls"] == 2
    assert config.spent()["usd"] == pytest.approx(0.022)


def test_the_ceiling_overrides_a_human_switching_it_on():
    """A budget is a budget whatever anybody clicked."""
    config.set_llm_enabled(True)
    assert config.llm_enabled() is True

    config.record_spend(200, 2.60)
    assert config.cap_reached() is True
    assert config.llm_enabled() is False, "the cap must win over the switch"
    assert "cap" in config.llm_setting_source()


def test_the_ceiling_survives_a_restart():
    """The ledger is on disk, not in the process — a crash-loop must not reset it."""
    config.set_llm_enabled(True)
    config.record_spend(100, 3.00)
    assert config.llm_enabled() is False

    import importlib
    importlib.reload(config)              # a brand new process reading the same file
    assert config.cap_reached() is True
    assert config.llm_enabled() is False


def test_spend_is_recorded_per_call_not_per_run(monkeypatch):
    """A process killed mid-run still spent the money. A ledger that only writes on a
    clean exit undercounts exactly when it matters."""
    from src.extractor import llm_extract

    class FakeUsage:
        input_tokens, output_tokens = 1_000_000, 0

    class FakeMessage:
        usage = FakeUsage()
        content = []

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                return FakeMessage()

    monkeypatch.setenv("LLM_PRICE_IN", "3.0")
    monkeypatch.setenv("LLM_PRICE_OUT", "15.0")
    # conftest pins LLM_MAX_CALLS=0 for the whole session so nothing can spend by
    # accident; this test drives a fake client, so lift it for this one call.
    monkeypatch.setenv("LLM_MAX_CALLS", "10")
    monkeypatch.setattr(llm_extract, "_get_client", lambda: FakeClient())
    llm_extract.reset_budget()

    llm_extract._ask("anything")
    assert config.spent()["usd"] == pytest.approx(3.0)   # 1M input tokens at $3/MTok
    assert config.cap_reached() is True                  # and it tripped the ceiling


def test_raising_the_ceiling_re_enables_it(monkeypatch):
    config.set_llm_enabled(True)
    config.record_spend(1, 2.60)
    assert config.llm_enabled() is False

    monkeypatch.setenv("LLM_SPEND_CAP_USD", "10.0")
    assert config.llm_enabled() is True


def test_clearing_the_ledger_is_possible_but_explicit():
    config.record_spend(50, 5.0)
    assert config.cap_reached() is True
    config.reset_spend()
    assert config.spent() == {"calls": 0, "usd": 0.0}


# --- the admin token -------------------------------------------------------

def test_no_token_configured_means_the_controls_are_open():
    """A laptop should not need a password to press its own buttons."""
    from src.api.main import require_admin
    assert config.admin_token() == ""
    require_admin(None)                   # must not raise


def test_a_configured_token_is_required(monkeypatch):
    from fastapi import HTTPException
    from src.api.main import require_admin

    monkeypatch.setenv("SDOC_ADMIN_TOKEN", "letmein")
    require_admin("letmein")              # correct: fine

    for wrong in (None, "", "nope", "letmein "):
        with pytest.raises(HTTPException) as exc:
            require_admin(wrong)
        assert exc.value.status_code == 401
