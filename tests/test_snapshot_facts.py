"""Tests for the code-computed parts of a snapshot (no AI involved)."""

import datetime as dt

from app.schemas.lead_snapshot import SignalInfo, TouchpointInfo
from app.services.snapshot_facts import (
    count_effort,
    describe_signal,
    find_last_activity,
    find_last_contact,
)

TODAY = dt.date(2026, 10, 13)


def touchpoint(date: str, type: str, responded: bool = False) -> TouchpointInfo:
    return TouchpointInfo(
        date=dt.datetime.fromisoformat(f"{date}T15:00:00+00:00"),
        type=type,
        received_response=responded,
    )


def signal(date: str, type: str, platform: str | None = None) -> SignalInfo:
    return SignalInfo(
        date=dt.datetime.fromisoformat(f"{date}T12:00:00+00:00"),
        type=type,
        platform=platform,
    )


# ── Last contact ─────────────────────────────────────────────────────────────


def test_last_contact_is_none_without_touchpoints():
    assert find_last_contact([], TODAY) is None


def test_last_contact_is_the_most_recent_touchpoint_regardless_of_order():
    touchpoints = [
        touchpoint("2026-05-21", "NETWORKING"),
        touchpoint("2026-06-02", "CALL"),
        touchpoint("2026-05-01", "IN_PERSON"),
    ]

    last = find_last_contact(touchpoints, TODAY)

    assert last.date == dt.date(2026, 6, 2)
    assert last.type == "CALL"
    assert last.days_ago == 133


# ── Last activity ────────────────────────────────────────────────────────────


def test_last_activity_is_none_when_they_never_did_anything():
    touchpoints = [touchpoint("2026-05-06", "INSTAGRAM_DM")]  # no response

    assert find_last_activity(touchpoints, [], TODAY) is None


def test_last_activity_picks_the_newest_of_signals_and_responses():
    touchpoints = [touchpoint("2026-09-01", "EMAIL", responded=True)]
    signals = [signal("2026-10-06", "FOLLOW", "INSTAGRAM")]

    last = find_last_activity(touchpoints, signals, TODAY)

    assert last.date == dt.date(2026, 10, 6)
    assert last.days_ago == 7
    assert last.description == "Followed us on Instagram"


def test_last_activity_describes_a_response():
    touchpoints = [touchpoint("2026-09-01", "EMAIL", responded=True)]

    last = find_last_activity(touchpoints, [], TODAY)

    assert last.description == "Responded to our email"


# ── Signal descriptions ──────────────────────────────────────────────────────


def test_social_signal_includes_platform():
    assert (
        describe_signal(signal("2026-10-06", "DIRECT_MESSAGE", "LINKEDIN"))
        == "Sent us a DM on LinkedIn"
    )


def test_non_social_signal_has_no_platform():
    assert (
        describe_signal(signal("2026-10-06", "WEBSITE_FORM"))
        == "Filled out the website form"
    )


def test_unknown_signal_type_falls_back_to_raw_name():
    assert describe_signal(signal("2026-10-06", "SOME_NEW_TYPE")) == "SOME_NEW_TYPE"


# ── Effort counts ────────────────────────────────────────────────────────────


def test_visit_attempts_count_as_visits():
    effort = count_effort(
        [
            touchpoint("2026-05-01", "IN_PERSON"),
            touchpoint("2026-05-02", "VISIT_ATTEMPT"),
        ]
    )

    assert effort.visits == 2


def test_every_touchpoint_is_counted_somewhere():
    types = [
        "IN_PERSON", "VISIT_ATTEMPT", "EMAIL", "CALL", "INSTAGRAM_DM", "TEXT",
        "MEETING", "NETWORKING", "WALK_UP", "REFERRAL_OUTREACH", "OTHER",
        "SOME_FUTURE_TYPE",
    ]  # fmt: skip

    effort = count_effort([touchpoint("2026-05-01", t) for t in types])

    assert sum(effort.model_dump().values()) == len(types)
    assert effort.other == 2  # "OTHER" plus the unrecognized type
