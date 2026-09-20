"""
The Claude on/off switch.

Claude costs money and the rules do not need it — they score 1.0000 on the sample inbox
alone. So the switch is off unless somebody deliberately turns it on, and turning it on
happens from the header of the running service rather than through a redeploy.

These tests are about the money: a key sitting in .env must not be enough to spend it.
"""

from __future__ import annotations

import json

import pytest

from src import config


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point the switch at a throwaway state file so a test never writes the real one."""
    monkeypatch.setenv("SDOC_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.delenv("SDOC_LLM", raising=False)
    yield


def test_off_by_default_even_with_a_key_present(monkeypatch):
    """The expensive default must be the one you have to ask for."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-pretend")
    assert config.llm_enabled() is False
    assert config.llm_setting_source() == "default (off)"


def test_the_switch_persists(tmp_path):
    config.set_llm_enabled(True)
    assert config.llm_enabled() is True
    assert config.llm_setting_source() == "switched here"
    assert json.loads(config.state_file().read_text())["llm_enabled"] is True

    config.set_llm_enabled(False)
    assert config.llm_enabled() is False


def test_the_environment_sets_the_default_and_the_switch_overrides_it(monkeypatch):
    monkeypatch.setenv("SDOC_LLM", "on")
    assert config.llm_enabled() is True
    assert "SDOC_LLM" in config.llm_setting_source()

    config.set_llm_enabled(False)              # a person said no; that wins
    assert config.llm_enabled() is False


@pytest.mark.parametrize("value,expected", [
    ("on", True), ("ON", True), ("1", True), ("true", True), ("yes", True),
    ("off", False), ("0", False), ("no", False), ("", False), ("maybe", False),
])
def test_environment_spellings(monkeypatch, value: str, expected: bool):
    monkeypatch.setenv("SDOC_LLM", value)
    assert config.llm_enabled() is expected


def test_a_corrupt_state_file_falls_back_instead_of_crashing():
    config.state_file().write_text("{ not json")
    assert config.llm_enabled() is False       # the safe side, and no exception


def test_no_call_is_attempted_while_the_switch_is_off(monkeypatch):
    """The real guard: with the switch off there is no client, so nothing can spend."""
    from src.extractor import llm_extract

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-pretend")
    llm_extract.forget_client()

    config.set_llm_enabled(False)
    assert llm_extract.llm_available() is False
    assert llm_extract.classify_email("subject", "body") is None
    assert llm_extract.extract_from_text("doc", "e", None, "p") is None
    assert llm_extract.calls_made() == 0


def test_status_reports_what_the_header_shows(monkeypatch):
    from src.extractor import llm_extract

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-pretend")
    llm_extract.forget_client()
    config.set_llm_enabled(True)

    status = llm_extract.llm_status()
    assert status["enabled"] is True
    assert status["has_key"] is True
    assert status["budget"] == config.max_llm_calls()
    assert status["estimated_usd"] == 0.0        # nothing spent yet
    assert "model" in status


def test_spend_is_estimated_from_the_configured_prices(monkeypatch):
    from src.extractor import llm_extract

    monkeypatch.setenv("LLM_PRICE_IN", "3.0")
    monkeypatch.setenv("LLM_PRICE_OUT", "15.0")
    monkeypatch.setattr(llm_extract, "_tokens_in", 1_000_000)
    monkeypatch.setattr(llm_extract, "_tokens_out", 100_000)
    assert llm_extract.usage()["estimated_usd"] == pytest.approx(3.0 + 1.5)
