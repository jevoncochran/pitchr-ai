"""Tests for the shared-secret check that protects every route."""

from app.main import app
from app.security import PUBLIC_PATHS

SNAPSHOT_BODY = {
    "today": "2026-10-13",
    "lead": {"business": "Example Roofing", "pipelineStage": "NEW"},
}


def test_rejects_a_request_without_the_api_key(anonymous_client):
    response = anonymous_client.post("/leads/snapshot", json=SNAPSHOT_BODY)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}


def test_rejects_a_request_with_the_wrong_api_key(client):
    response = client.post(
        "/leads/snapshot",
        json=SNAPSHOT_BODY,
        headers={"X-Internal-Api-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_health_check_is_public(anonymous_client):
    response = anonymous_client.get("/health")

    assert response.status_code == 200


def test_only_health_is_public():
    # If this fails, someone opened a new route; make sure that was intended
    assert PUBLIC_PATHS == {"/health"}


def test_routes_added_later_are_protected_automatically(client, anonymous_client):
    # A brand-new route that does nothing about security itself
    @app.get("/test-only-new-route")
    def new_route():
        return {"ok": True}

    try:
        assert anonymous_client.get("/test-only-new-route").status_code == 401
        assert client.get("/test-only-new-route").status_code == 200
    finally:
        app.router.routes.pop()  # remove the test route again


def test_docs_page_offers_an_authorize_button(anonymous_client):
    schema = anonymous_client.get("/openapi.json").json()

    assert schema["components"]["securitySchemes"]["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Internal-Api-Key",
    }
