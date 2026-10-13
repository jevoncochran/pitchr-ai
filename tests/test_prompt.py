"""Tests for how lead data is laid out for Claude."""

import datetime as dt

from app.prompts.lead_snapshot import MAX_TOUCHPOINTS, build_prompt, format_date
from app.schemas.lead_snapshot import LeadSnapshotRequest
from app.services.snapshot_facts import compute_facts

TODAY = dt.date(2026, 10, 13)


def test_format_date_past_today_and_future():
    assert format_date(dt.date(2026, 5, 7)) == "5/7/26"
    assert format_date(dt.date(2026, 10, 6), TODAY) == "10/6/26 (7 days ago)"
    assert format_date(TODAY, TODAY) == "10/13/26 (today)"
    assert format_date(dt.date(2026, 10, 20), TODAY) == "10/20/26 (in 7 days)"


def test_prompt_keeps_only_the_most_recent_touchpoints():
    # 30 touchpoints, one per day; the summary says which day it was
    touchpoints = [
        {
            "date": (dt.datetime(2026, 4, 1, 15) + dt.timedelta(days=i)).isoformat()
            + "Z",
            "type": "EMAIL",
            "summary": f"touchpoint number {i}",
        }
        for i in range(30)
    ]
    request = LeadSnapshotRequest.model_validate(
        {
            "today": TODAY.isoformat(),
            "lead": {"business": "Example", "pipelineStage": "NEW"},
            "touchpoints": touchpoints,
        }
    )

    prompt = build_prompt(request, compute_facts(request))

    assert "touchpoint number 29" in prompt  # newest kept
    assert "touchpoint number 4\n" not in prompt  # oldest dropped
    assert f"({30 - MAX_TOUCHPOINTS} older touchpoints not shown)" in prompt


def test_prompt_says_none_for_empty_sections():
    request = LeadSnapshotRequest.model_validate(
        {
            "today": TODAY.isoformat(),
            "lead": {"business": "Example", "pipelineStage": "NEW"},
        }
    )

    prompt = build_prompt(request, compute_facts(request))

    assert "<contacts>\nNone saved.\n</contacts>" in prompt
    assert "Last contact: none, we have never reached out" in prompt
