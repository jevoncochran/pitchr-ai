"""Request and response models for the visit debrief feature.

A note dictated right after an in-person visit becomes a proposal for the visit
form: outcome, provider, come-back date, materials, the people involved and a
summary. See pitchr-server's docs/visit-debrief.md for the spec.
"""

import datetime as dt
from typing import Literal

from pydantic import Field

from app.core.schemas import CamelModel

# The in-person outcomes the visit form offers (TouchPointOutcome in pitchr-server,
# without the call-only ones)
Outcome = Literal[
    "BUSINESS_CLOSED",
    "DECISION_MAKER_NOT_AVAILABLE",
    "COME_BACK_LATER",
    "INTERESTED",
    "NOT_INTERESTED",
    "HAS_PROVIDER",
    "NOT_A_FIT",
    "MEETING_BOOKED",
]
ProviderType = Literal["VIDEO", "MARKETING_AGENCY", "UNKNOWN"]

# ── Request (sent by NestJS) ─────────────────────────────────────────────────


class DebriefLead(CamelModel):
    business: str
    industry: str | None = None
    business_type: str | None = None
    pipeline_stage: str | None = None


class DebriefContact(CamelModel):
    id: str
    first_name: str
    last_name: str | None = None
    title: str | None = None
    is_decision_maker: bool = False


class RecentTouchpoint(CamelModel):
    date: dt.datetime
    type: str
    summary: str | None = None


class VisitDebriefRequest(CamelModel):
    # Today in the team's time zone (NestJS's teamDateKey), for working out dates
    today: dt.date
    note: str = Field(min_length=1, max_length=5000)
    lead: DebriefLead
    contacts: list[DebriefContact] = Field(default_factory=list)
    # The three most recent, so "came back as she asked" makes sense
    recent_touchpoints: list[RecentTouchpoint] = Field(
        default_factory=list, max_length=3
    )


# ── What Claude returns ──────────────────────────────────────────────────────
#
# Structured outputs limit a schema to 16 union-typed and 24 optional
# parameters in total, so every field is required and "" (or "none") stands for
# nothing; check_proposal() turns those into None. tests/visit_debrief checks it.


class PersonRead(CamelModel):
    """Someone the note mentions: spoken to, or named (e.g. the owner who wasn't in)."""

    contact_id: str = Field(
        description="The id of the contact on file this is, when clearly one of them. Otherwise an empty string."
    )
    candidate_contact_ids: list[str] = Field(
        description="When it could be more than one contact on file: their ids, and contact_id stays empty."
    )
    first_name: str = Field(
        description="As said, or as on file for a contact on file. Empty string if no name was said."
    )
    last_name: str = Field(description="Empty string if not said and not on file.")
    title: str = Field(
        description='Their role as said ("front desk", "owner", "office manager"). Empty string if not said.'
    )
    is_decision_maker: Literal["yes", "no", "unknown"] = Field(
        description='"yes" only when the note says they decide (owner, "she makes the decisions"); "no" when it says someone else does; otherwise "unknown".'
    )
    spoke_with: bool = Field(
        description="True only if we actually talked to them on this visit."
    )


class DebriefRead(CamelModel):
    outcome: Literal[
        "BUSINESS_CLOSED",
        "DECISION_MAKER_NOT_AVAILABLE",
        "COME_BACK_LATER",
        "INTERESTED",
        "NOT_INTERESTED",
        "HAS_PROVIDER",
        "NOT_A_FIT",
        "MEETING_BOOKED",
        "unclear",
    ]
    provider_type: Literal["VIDEO", "MARKETING_AGENCY", "UNKNOWN", "none"] = Field(
        description='The kind of provider they have, if the note says they have one; "none" if it doesn\'t come up.'
    )
    come_back_date: str = Field(
        description="YYYY-MM-DD from the calendar given, when the note gives a day to come back or a meeting day. Empty string otherwise."
    )
    come_back_time: str = Field(
        description="HH:MM (24-hour) when a time or a part of the day was said. Empty string otherwise."
    )
    come_back_day_estimated: bool = Field(
        description='True only when the day came from a period ("next week", "in January"), not a day that was said ("tomorrow", "Thursday").'
    )
    come_back_estimated_from: str = Field(
        description='The words a come-back date or time was estimated from ("next week", "tomorrow afternoon"). Empty string when the day and time were said exactly.'
    )
    left_materials: bool = Field(
        description="True when we left a card, flyer, brochure or other materials."
    )
    summary: str
    people: list[PersonRead]
    questions: list[str] = Field(
        description="Short questions for things the note leaves unclear and the owner should decide. Empty when nothing is unclear."
    )


# ── Response (sent to NestJS) ────────────────────────────────────────────────


class Person(CamelModel):
    contact_id: str | None = None
    candidate_contact_ids: list[str] = Field(default_factory=list)
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    is_decision_maker: bool | None = None
    spoke_with: bool = False


class VisitDebriefResponse(CamelModel):
    # The model that wrote this proposal
    model: str | None = None
    outcome: Outcome | None = None
    provider_type: ProviderType | None = None
    come_back_date: dt.date | None = None
    come_back_time: str | None = None
    # The words the date or time was estimated from ("next week"), so the form
    # can say it's an estimate; None when it was said exactly
    come_back_estimate: str | None = None
    left_materials: bool = False
    summary: str
    people: list[Person] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
