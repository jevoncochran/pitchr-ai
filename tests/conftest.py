"""Shared test setup. pytest loads this file automatically for every test."""

import pytest
from fastapi.testclient import TestClient

import app.core.claude as claude_service
from app.core.config import Settings, get_settings
from app.main import app

TEST_API_KEY = "test-api-key"


@pytest.fixture(autouse=True)
def test_settings():
    """Use known test settings instead of the real .env file, in every test."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        anthropic_api_key="not-a-real-key",
        pitchr_ai_api_key=TEST_API_KEY,
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def block_real_claude_calls(monkeypatch):
    """Tests must never call the real Claude API (it costs money and is slow).

    Tests that need Claude replace generate_structured with a fake; if anything
    slips past that, this makes it fail loudly instead of spending money.
    """

    def no_real_client():
        raise RuntimeError("Tests must not call the real Claude API; use a fake.")

    monkeypatch.setattr(claude_service, "get_client", no_real_client)


@pytest.fixture
def client():
    """A client that sends the right API key, like NestJS does."""
    return TestClient(app, headers={"X-Internal-Api-Key": TEST_API_KEY})


@pytest.fixture
def anonymous_client():
    """A client that sends no API key, like anyone else on the network."""
    return TestClient(app)
