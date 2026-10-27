import pytest


@pytest.fixture(autouse=True)
def default_provider(monkeypatch):
    """Tests use the Meta provider whatever LLM_PROVIDER says in the real .env (load_dotenv won't override)."""
    monkeypatch.setenv("LLM_PROVIDER", "meta")
