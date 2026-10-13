"""Tests for POST /leads/snapshot, with Claude faked so they're free and fast."""

import pytest

import app.features.lead_snapshot.service as lead_snapshot_service
from app.core.claude import ClaudeError
from app.features.lead_snapshot.schemas import SnapshotAnalysis

VALID_BODY = {
    "today": "2026-10-13",
    "lead": {"business": "Example Roofing", "pipelineStage": "NEW"},
    "touchpoints": [
        {"date": "2026-05-06T15:00:00Z", "type": "INSTAGRAM_DM", "summary": "cold DM"}
    ],
    "signals": [
        {"date": "2026-10-06T12:00:00Z", "type": "FOLLOW", "platform": "INSTAGRAM"}
    ],
}

FAKE_ANALYSIS = SnapshotAnalysis(
    headline="Fake headline",
    decision_maker="Unknown",
    key_facts=["Fake fact"],
    odds="medium",
    odds_reason="Fake reason",
    goal="Fake goal",
    suggested_approach="Fake approach",
)


@pytest.fixture
def fake_claude(monkeypatch):
    """Replace the real Claude call with one that returns FAKE_ANALYSIS.

    Returns a list that records the arguments of each call, so tests can check
    what would have been sent to Claude.
    """
    calls = []

    def fake_generate_structured(**kwargs):
        calls.append(kwargs)
        return FAKE_ANALYSIS

    monkeypatch.setattr(
        lead_snapshot_service, "generate_structured", fake_generate_structured
    )
    return calls


def test_returns_facts_and_analysis_as_camel_case_json(client, fake_claude):
    response = client.post("/leads/snapshot", json=VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["lastContact"] == {
        "date": "2026-05-06",
        "daysAgo": 160,
        "type": "INSTAGRAM_DM",
    }
    assert body["lastActivity"]["description"] == "Followed us on Instagram"
    assert body["effort"]["dms"] == 1
    assert body["analysis"]["decisionMaker"] == "Unknown"
    assert body["analysis"]["odds"] == "medium"


def test_sends_the_lead_data_to_claude_under_the_right_feature_name(
    client, fake_claude
):
    client.post("/leads/snapshot", json=VALID_BODY)

    assert len(fake_claude) == 1
    call = fake_claude[0]
    assert call["feature"] == "lead_snapshot"
    assert call["output_model"] is SnapshotAnalysis
    assert "Example Roofing" in call["prompt"]
    assert "cold DM" in call["prompt"]


def test_returns_502_when_claude_fails(client, monkeypatch):
    def failing_generate_structured(**kwargs):
        raise ClaudeError("pretend Claude is down")

    monkeypatch.setattr(
        lead_snapshot_service, "generate_structured", failing_generate_structured
    )

    response = client.post("/leads/snapshot", json=VALID_BODY)

    assert response.status_code == 502
    assert response.json() == {"detail": "Couldn't generate the snapshot. Try again."}


def test_rejects_a_request_missing_the_lead(client, fake_claude):
    response = client.post("/leads/snapshot", json={"today": "2026-10-13"})

    assert response.status_code == 422
    assert fake_claude == []  # Claude was never called
