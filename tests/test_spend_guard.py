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
    # a shared cache would make a spend test pass for the wrong reason: the second run
    # of the suite would answer from disk and record nothing
    monkeypatch.setenv("SDOC_LLM_CACHE", str(tmp_path / "cache"))
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
    config.set_llm_enabled(True)          # conftest pins the switch off for the suite
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


# --- the cache, which is what makes a public /run button safe ------------

def test_a_repeated_question_is_free(monkeypatch, tmp_path):
    """The whole defence. POST /run is public and cannot be gated, so the second press
    must not cost anything — otherwise a loop against it empties the budget."""
    from src.extractor import llm_extract

    monkeypatch.setenv("SDOC_LLM_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("LLM_MAX_CALLS", "10")
    calls = {"n": 0}

    class FakeUsage:
        input_tokens, output_tokens = 1000, 100

    class FakeBlock:
        type, text = "text", "answer"

    class FakeMessage:
        usage, content = FakeUsage(), [FakeBlock()]

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                calls["n"] += 1
                return FakeMessage()

    monkeypatch.setattr(llm_extract, "_get_client", lambda: FakeClient())
    config.set_llm_enabled(True)
    llm_extract.reset_budget()

    assert llm_extract._ask("read this document") == "answer"
    assert calls["n"] == 1
    spent_once = config.spent()["usd"]

    for _ in range(50):                      # somebody hammering the button
        assert llm_extract._ask("read this document") == "answer"

    assert calls["n"] == 1, "51 identical requests must cost exactly one API call"
    assert config.spent()["usd"] == spent_once, "a cached answer must not be billed"
    assert llm_extract.cache_hits() == 50


def test_a_different_question_still_costs(monkeypatch, tmp_path):
    """The cache must key on the request, not just exist."""
    from src.extractor import llm_extract

    monkeypatch.setenv("SDOC_LLM_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("LLM_MAX_CALLS", "10")
    calls = {"n": 0}

    class FakeBlock:
        type, text = "text", "answer"

    class FakeMessage:
        usage, content = None, [FakeBlock()]

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                calls["n"] += 1
                return FakeMessage()

    monkeypatch.setattr(llm_extract, "_get_client", lambda: FakeClient())
    config.set_llm_enabled(True)
    llm_extract.reset_budget()

    llm_extract._ask("document one")
    llm_extract._ask("document two")
    assert calls["n"] == 2


def test_the_switch_off_means_no_ai_output_at_all_even_from_cache(monkeypatch, tmp_path):
    """"Off" has to mean off, cache included.

    It is tempting to serve a cached answer when the switch is off — it costs nothing
    and the data is real. But then the rules-only column of the ablation table quietly
    contains vision results while reporting zero calls, and the deterministic path can
    never be measured honestly again. It also silently turns a scanned document that
    SHOULD escalate into one that passes.
    """
    from src.extractor import llm_extract

    monkeypatch.setenv("LLM_MAX_CALLS", "10")

    class FakeBlock:
        type, text = "text", "cached answer"

    class FakeMessage:
        usage, content = None, [FakeBlock()]

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                return FakeMessage()

    monkeypatch.setattr(llm_extract, "_get_client", lambda: FakeClient())
    config.set_llm_enabled(True)
    llm_extract.reset_budget()
    assert llm_extract._ask("a scanned page") == "cached answer"   # paid for, now cached

    config.set_llm_enabled(False)
    assert llm_extract._ask("a scanned page") is None, \
        "a cached answer must not leak past the switch"
    assert llm_extract.cache_hits() == 0


def test_the_cache_survives_a_new_process(monkeypatch, tmp_path):
    """It is on disk, so a container restart does not re-buy the same six scans."""
    from src.extractor import llm_extract

    monkeypatch.setenv("SDOC_LLM_CACHE", str(tmp_path / "cache"))
    key = llm_extract._cache_key("a document", 1024)
    llm_extract._cache_put(key, "stored")

    import importlib
    importlib.reload(llm_extract)
    monkeypatch.setenv("SDOC_LLM_CACHE", str(tmp_path / "cache"))
    assert llm_extract._cache_get(key) == "stored"
