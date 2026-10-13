"""Facts for the lead snapshot, computed in plain Python (no AI).

Dates, "days ago" and counts are facts, so code computes them and gets them
right every time. Claude only writes the parts that need judgment.
"""

import datetime as dt
from dataclasses import dataclass

from app.schemas.lead_snapshot import (
    EffortCounts,
    LastActivity,
    LastContact,
    LeadSnapshotRequest,
    SignalInfo,
    TouchpointInfo,
)

# Touchpoint types that count toward each effort total. Any type not listed
# here (including "OTHER" and types added to Pitchr later) counts as "other",
# so every touchpoint is counted somewhere.
VISIT_TYPES = {"IN_PERSON", "VISIT_ATTEMPT"}
EMAIL_TYPES = {"EMAIL"}
CALL_TYPES = {"CALL"}
DM_TYPES = {"INSTAGRAM_DM"}
TEXT_TYPES = {"TEXT"}
MEETING_TYPES = {"MEETING"}
NETWORKING_TYPES = {"NETWORKING"}
WALK_UP_TYPES = {"WALK_UP"}
REFERRAL_OUTREACH_TYPES = {"REFERRAL_OUTREACH"}

KNOWN_TYPES = (
    VISIT_TYPES
    | EMAIL_TYPES
    | CALL_TYPES
    | DM_TYPES
    | TEXT_TYPES
    | MEETING_TYPES
    | NETWORKING_TYPES
    | WALK_UP_TYPES
    | REFERRAL_OUTREACH_TYPES
)

SIGNAL_LABELS = {
    "FOLLOW": "Followed us",
    "POST_ENGAGEMENT": "Liked or commented on a post",
    "DIRECT_MESSAGE": "Sent us a DM",
    "WEBSITE_FORM": "Filled out the website form",
    "REFERRAL": "Referred by someone",
}

PLATFORM_LABELS = {
    "INSTAGRAM": "Instagram",
    "FACEBOOK": "Facebook",
    "TIKTOK": "TikTok",
    "YOUTUBE": "YouTube",
    "LINKEDIN": "LinkedIn",
    "OTHER": "another platform",
}

# How to name a touchpoint type in "Responded to our ___"
TOUCHPOINT_NOUNS = {
    "EMAIL": "email",
    "CALL": "call",
    "TEXT": "text",
    "INSTAGRAM_DM": "Instagram DM",
    "IN_PERSON": "visit",
    "MEETING": "meeting",
}


@dataclass
class SnapshotFacts:
    last_contact: LastContact | None
    last_activity: LastActivity | None
    effort: EffortCounts


def find_last_contact(
    touchpoints: list[TouchpointInfo], today: dt.date
) -> LastContact | None:
    """Our most recent outreach, or None if we've never reached out."""
    if not touchpoints:
        return None

    latest = max(touchpoints, key=lambda tp: tp.date)
    latest_date = latest.date.date()
    return LastContact(
        date=latest_date,
        days_ago=(today - latest_date).days,
        type=latest.type,
    )


def describe_signal(signal: SignalInfo) -> str:
    """e.g. "Followed us on Instagram" or "Filled out the website form"."""
    label = SIGNAL_LABELS.get(signal.type, signal.type)
    if signal.platform:
        platform = PLATFORM_LABELS.get(signal.platform, signal.platform)
        return f"{label} on {platform}"
    return label


def find_last_activity(
    touchpoints: list[TouchpointInfo], signals: list[SignalInfo], today: dt.date
) -> LastActivity | None:
    """The lead's most recent action: a signal, or a response to our outreach."""
    # Collect every action the lead took as (when, what happened) pairs
    actions: list[tuple[dt.datetime, str]] = []

    for signal in signals:
        actions.append((signal.date, describe_signal(signal)))

    for tp in touchpoints:
        if tp.received_response:
            noun = TOUCHPOINT_NOUNS.get(tp.type, "outreach")
            actions.append((tp.date, f"Responded to our {noun}"))

    if not actions:
        return None

    latest_when, latest_what = max(actions, key=lambda action: action[0])
    latest_date = latest_when.date()
    return LastActivity(
        date=latest_date,
        days_ago=(today - latest_date).days,
        description=latest_what,
    )


def count_effort(touchpoints: list[TouchpointInfo]) -> EffortCounts:
    """How much outreach we've done, by type."""
    return EffortCounts(
        visits=sum(1 for tp in touchpoints if tp.type in VISIT_TYPES),
        emails=sum(1 for tp in touchpoints if tp.type in EMAIL_TYPES),
        calls=sum(1 for tp in touchpoints if tp.type in CALL_TYPES),
        dms=sum(1 for tp in touchpoints if tp.type in DM_TYPES),
        texts=sum(1 for tp in touchpoints if tp.type in TEXT_TYPES),
        meetings=sum(1 for tp in touchpoints if tp.type in MEETING_TYPES),
        networking_events=sum(1 for tp in touchpoints if tp.type in NETWORKING_TYPES),
        walk_ups=sum(1 for tp in touchpoints if tp.type in WALK_UP_TYPES),
        referral_outreach=sum(
            1 for tp in touchpoints if tp.type in REFERRAL_OUTREACH_TYPES
        ),
        other=sum(1 for tp in touchpoints if tp.type not in KNOWN_TYPES),
    )


def compute_facts(request: LeadSnapshotRequest) -> SnapshotFacts:
    """All the code-computed parts of a snapshot."""
    return SnapshotFacts(
        last_contact=find_last_contact(request.touchpoints, request.today),
        last_activity=find_last_activity(
            request.touchpoints, request.signals, request.today
        ),
        effort=count_effort(request.touchpoints),
    )
