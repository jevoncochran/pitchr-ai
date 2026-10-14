"""Tests for how lead data is laid out for Claude."""

import datetime as dt

from app.features.lead_snapshot.facts import compute_facts
from app.features.lead_snapshot.prompt import MAX_TOUCHPOINTS, build_prompt, format_date
from app.features.lead_snapshot.schemas import LeadSnapshotRequest

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


def test_prompt_dates_an_evening_touchpoint_in_tampa_time():
    # 9pm in Tampa on 10/13 is stored as 1am UTC on 10/14
    request = LeadSnapshotRequest.model_validate(
        {
            "today": TODAY.isoformat(),
            "lead": {"business": "Example", "pipelineStage": "NEW"},
            "touchpoints": [
                {
                    "date": "2026-10-14T01:00:00Z",
                    "type": "IN_PERSON",
                    "summary": "visited after dinner",
                }
            ],
        }
    )

    prompt = build_prompt(request, compute_facts(request))

    assert "10/13/26 (today) IN_PERSON" in prompt
    assert "in 1 days" not in prompt


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


def test_prompt_shows_where_each_reply_stands_and_their_words():
    request = LeadSnapshotRequest.model_validate(
        {
            "today": TODAY.isoformat(),
            "lead": {"business": "Example", "pipelineStage": "CONTACTED"},
            "touchpoints": [
                {
                    "date": "2026-09-01T15:00:00Z",
                    "type": "EMAIL",
                    "response": "NO_RESPONSE",
                },
                {
                    "date": "2026-10-01T15:00:00Z",
                    "type": "INSTAGRAM_DM",
                    "response": "REPLIED",
                    "responseText": "  Sounds great, what do you charge?  ",
                    "respondedOn": "2026-10-10",
                },
                {"date": "2026-10-12T15:00:00Z", "type": "TEXT", "response": "PENDING"},
                {
                    "date": "2026-08-01T15:00:00Z",
                    "type": "EMAIL",
                    "receivedResponse": True,
                },
            ],
        }
    )

    prompt = build_prompt(request, compute_facts(request))

    assert "EMAIL (no response)" in prompt
    assert "INSTAGRAM_DM (they replied 10/10/26 (3 days ago))" in prompt
    assert "Their reply: <reply>Sounds great, what do you charge?</reply>" in prompt
    assert "TEXT (no reply yet)" in prompt
    assert (
        "8/1/26 (73 days ago) EMAIL (they responded)" in prompt
    )  # logged before tracking


def test_prompt_says_how_the_lead_started_with_its_group():
    def prompt_for(lead_fields):
        request = LeadSnapshotRequest.model_validate(
            {
                "today": TODAY.isoformat(),
                "lead": {"business": "Example", "pipelineStage": "NEW", **lead_fields},
            }
        )
        return build_prompt(request, compute_facts(request))

    assert "How this lead started: DM (we reached out)" in prompt_for(
        {"origin": "DM", "originGroup": "WE_REACHED_OUT"}
    )
    assert "How this lead started: Met at a farmers market (they came to us)" in (
        prompt_for(
            {"origin": "Met at a farmers market", "originGroup": "THEY_CAME_TO_US"}
        )
    )
    assert "How this lead started" not in prompt_for({})
