"""Request and response models for the lead snapshot feature.

See docs/lead-snapshot.md for the full spec.
"""

import datetime as dt
from typing import Literal

from pydantic import Field

from app.core.schemas import CamelModel

# ── Request (sent by NestJS) ─────────────────────────────────────────────────


class LeadInfo(CamelModel):
    business: str
    industry: str | None = None
    business_type: str | None = None
    pipeline_stage: str
    sequence_step: int = 0
    is_hot: bool = False
    priority: str | None = None
    source: str | None = None
    discovered_via: str | None = None
    referred_by: str | None = None
    dormant_reason: str | None = None
    dormant_revisit_at: dt.datetime | None = None


class ContactInfo(CamelModel):
    first_name: str
    last_name: str | None = None
    title: str | None = None
    is_decision_maker: bool = False
    how_we_met: str | None = None
    bio: str | None = None


class TouchpointInfo(CamelModel):
    date: dt.datetime
    type: str
    received_response: bool = False
    contact_names: list[str] = Field(default_factory=list)
    summary: str | None = None
    # DMs, emails and texts logged since outreach sessions: PENDING, REPLIED or
    # NO_RESPONSE. When REPLIED, their message and the day they sent it.
    response: str | None = None
    response_text: str | None = None
    responded_on: dt.date | None = None


class SignalInfo(CamelModel):
    date: dt.datetime
    type: str
    platform: str | None = None
    note: str | None = None


class NoteInfo(CamelModel):
    date: dt.datetime
    text: str


class TaskInfo(CamelModel):
    due_date: dt.datetime | None = None
    type: str
    note: str | None = None


class LeadSnapshotRequest(CamelModel):
    today: dt.date
    lead: LeadInfo
    contacts: list[ContactInfo] = Field(default_factory=list)
    touchpoints: list[TouchpointInfo] = Field(default_factory=list)
    signals: list[SignalInfo] = Field(default_factory=list)
    notes: list[NoteInfo] = Field(default_factory=list)
    open_tasks: list[TaskInfo] = Field(default_factory=list)


# ── Response ─────────────────────────────────────────────────────────────────


class LastContact(CamelModel):
    """Our most recent outreach. Computed in code."""

    date: dt.date
    days_ago: int
    type: str


class LastActivity(CamelModel):
    """The lead's most recent action (a signal or a response). Computed in code."""

    date: dt.date
    days_ago: int
    description: str


class EffortCounts(CamelModel):
    """How much outreach we've done so far. Computed in code."""

    visits: int
    emails: int
    calls: int
    dms: int
    texts: int
    meetings: int
    networking_events: int
    walk_ups: int
    referral_outreach: int
    other: int


class SnapshotAnalysis(CamelModel):
    """The parts that need judgment. Written by Claude."""

    headline: str = Field(description="One line, under 15 words.")
    decision_maker: str = Field(
        description='Name, role and status, e.g. "Jane Doe, owner. Met in person 5/21, receptive." Or "Unknown".'
    )
    key_facts: list[str] = Field(
        description="1-4 short bullets, only things the data says. Fewer when there's little to say."
    )
    odds: Literal["high", "medium", "low", "unknown"]
    odds_reason: str = Field(description="One sentence, grounded in the data.")
    goal: str = Field(description="One sentence on what this contact should achieve.")
    suggested_approach: str = Field(description="1-2 sentences.")


class LeadSnapshotResponse(CamelModel):
    last_contact: LastContact | None
    last_activity: LastActivity | None
    effort: EffortCounts
    analysis: SnapshotAnalysis
