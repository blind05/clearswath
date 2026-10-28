from types import SimpleNamespace

import pytest

from app import spend


def test_token_cost_from_chat_and_responses_usage():
    chat = {"prompt_tokens": 1_000_000, "completion_tokens": 100_000}
    assert spend.cost("muse-spark-1.3", chat) == pytest.approx(1.25 + 0.425)
    responses = SimpleNamespace(model_dump=lambda: {"input_tokens": 2_000_000, "output_tokens": 0})
    assert spend.cost("accounts/fireworks/models/muse-spark-open", responses) == pytest.approx(2.5)


def test_flat_and_unknown_models_cost_high():
    assert spend.cost("sam-3.1", None) == spend.CALL_PRICES["sam-3.1"]
    assert spend.cost("some-new-model", {"prompt_tokens": 1_000_000}) == spend.UNKNOWN[0]
    assert spend.cost("muse-spark-1.3", None) == spend.NO_USAGE  # no usage reported: never free
    assert spend.cost("muse-spark-1.3", {"prompt_tokens": 0, "completion_tokens": 0}) == spend.NO_USAGE


def test_record_adds_up_today_and_forgets_yesterday(monkeypatch):
    monkeypatch.setattr(spend, "_today", lambda: "2026-10-28")
    spend.record("sam-3.1", None)
    spend.record("muse-spark-1.3", {"prompt_tokens": 1_000_000})
    assert spend.today() == pytest.approx(spend.CALL_PRICES["sam-3.1"] + 1.25)
    monkeypatch.setattr(spend, "_today", lambda: "2026-10-29")
    assert spend.today() == 0
    spend.record("sam-3.1", None)
    assert spend.today() == pytest.approx(spend.CALL_PRICES["sam-3.1"])


def test_every_logged_model_call_is_costed(monkeypatch, tmp_path):
    from app import llm

    monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
    llm.log_call("muse-spark-1.3", "test", 0.1, {"prompt_tokens": 400_000, "completion_tokens": 0})
    assert spend.today() == pytest.approx(0.5)
