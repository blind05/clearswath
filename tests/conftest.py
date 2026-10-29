import pytest


@pytest.fixture(autouse=True)
def default_provider(monkeypatch):
    """Tests use the Meta provider whatever LLM_PROVIDER says in the real .env (load_dotenv won't override)."""
    monkeypatch.setenv("LLM_PROVIDER", "meta")
    monkeypatch.setenv("AGENT_FALLBACK_PROVIDER", "")  # empty, not unset: load_dotenv won't fill it from .env


@pytest.fixture(autouse=True)
def open_live_endpoints(monkeypatch, tmp_path):
    """Tests run as local development: no access code, not on Render, fresh rate-limit counters, and spend
    written to a temporary file, never the real data/logs."""
    from app import api, spend

    monkeypatch.setattr(spend, "PATH", tmp_path / "spend.json")
    for var in ("ACCESS_CODE", "RENDER", "RUNS_PER_IP_PER_DAY", "DAILY_RUN_CAP", "DAILY_BUDGET_USD",
                "CLEARSWATH_LIVE_MODE"):
        monkeypatch.delenv(var, raising=False)
    api.reset_limits()
    # no background clean-up during tests: it would sweep the real data/cache (tests call clean_up directly)
    monkeypatch.setattr(api, "_cleaned", {"at": float("inf")})
