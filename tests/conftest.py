import pytest


@pytest.fixture(autouse=True)
def default_provider(monkeypatch):
    """Tests use the Meta provider whatever LLM_PROVIDER says in the real .env (load_dotenv won't override)."""
    monkeypatch.setenv("LLM_PROVIDER", "meta")


@pytest.fixture(autouse=True)
def open_live_endpoints(monkeypatch):
    """Tests run as local development: no access code, not on Render, fresh rate-limit counters."""
    from app import api

    for var in ("ACCESS_CODE", "RENDER", "RATE_LIMIT_PER_HOUR", "DAILY_RUN_CAP", "CLEARSWATH_LIVE_MODE"):
        monkeypatch.delenv(var, raising=False)
    api.reset_limits()
    # no background clean-up during tests: it would sweep the real data/cache (tests call clean_up directly)
    monkeypatch.setattr(api, "_cleaned", {"at": float("inf")})
