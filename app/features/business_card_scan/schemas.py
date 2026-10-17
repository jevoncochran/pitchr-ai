"""Request and response models for the business card scan feature.

One upload is up to 6 photos of up to 3 business cards from one business: each
person's side, plus a side with only the business on it that's often shared by
all of them. See pitchr-server's docs/business-card-scan.md for the spec.
"""

from typing import Literal

from pydantic import Field

from app.core.schemas import CamelModel

MAX_PHOTOS = 6

# ── Request (sent by NestJS) ─────────────────────────────────────────────────


class BusinessCardContact(CamelModel):
    """A contact already on the lead, so a business card can be matched to it."""

    id: str
    first_name: str
    last_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    is_decision_maker: bool = False


class Option(CamelModel):
    """One industry or business type Claude may suggest for a new lead."""

    id: str
    name: str


class Photo(CamelModel):
    # Base64 (no newlines). NestJS shrinks each photo first, so it stays well
    # under Claude's per-image limit.
    data: str = Field(min_length=1, max_length=7_000_000)
    media_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"


class BusinessCardScanRequest(CamelModel):
    photos: list[Photo] = Field(min_length=1, max_length=MAX_PHOTOS)
    # An existing lead: its name and contacts, to match the business cards against.
    # A new lead (Add Lead's "Fill in from business card"): no business, and
    # the lists to suggest an industry and business type from instead.
    business: str | None = None
    contacts: list[BusinessCardContact] = Field(default_factory=list)
    industries: list[Option] = Field(default_factory=list)
    business_types: list[Option] = Field(default_factory=list)

    @property
    def is_new_lead(self) -> bool:
        return self.business is None


# ── What Claude returns ──────────────────────────────────────────────────────
#
# Structured outputs limit a schema to 16 union-typed parameters ("text or null")
# and 24 optional ones, in total. So every field here is required, and a value
# that isn't on a business card is an empty string, not null; check_reading()
# turns those into None. tests/business_card_scan checks the schema stays in bounds.

EMPTY = "Empty string if it isn't on the business cards."


class BusinessRead(CamelModel):
    """The business, from every photo that shows it (most often a shared back)."""

    name: str = Field(description=f"The business name as printed. {EMPTY}")
    email: str = Field(
        description=f"A general address for the business (info@, hello@, contact@), not a person's own email. {EMPTY}"
    )
    website: str = Field(description=EMPTY)
    instagram_handle: str = Field(description=f"Without the @. {EMPTY}")
    address: str = Field(description=f"The address as printed. {EMPTY}")
    address_line1: str = Field(description=f"Street address. {EMPTY}")
    city: str = Field(description=EMPTY)
    state: str = Field(description=f"Two-letter US state code. {EMPTY}")
    zip: str = Field(description=EMPTY)
    other_phones: list[str] = Field(
        description="The business's main line, fax and other numbers that aren't one person's."
    )
    social_handles: list[str]
    suggested_industry_id: str = Field(
        description="New leads only: an industry id from the list given. Empty string if none clearly fits."
    )
    suggested_business_type_id: str = Field(
        description="New leads only: a business type id from the list given. Empty string if none clearly fits."
    )


class PersonCardRead(CamelModel):
    """One person's business card: their side, and their own back if they have one."""

    photos: list[int] = Field(
        description="The photo numbers of this person's own side(s). Never a side with only the business on it."
    )
    first_name: str = Field(description=EMPTY)
    last_name: str = Field(description=EMPTY)
    title: str = Field(description=EMPTY)
    email: str = Field(description=f"The person's own email. {EMPTY}")
    phone: str = Field(
        description=f"The person's direct or cell number, otherwise the card's only number. {EMPTY}"
    )
    is_decision_maker: bool = Field(
        description=(
            "True only when the title is clearly the top decision-maker: owner, co-owner, founder, "
            "president, CEO, managing partner, practice owner, or general manager of a single location."
        ),
    )
    business_name: str = Field(
        description=f"The business this card is for, as printed on it or its own back. {EMPTY}"
    )
    same_business: Literal["yes", "no", "unclear"] = Field(
        description=(
            "Whether this card is for the lead's business (an existing lead) or the business most "
            "cards share (a new lead). unclear when the card names no business."
        )
    )
    match: Literal["existing", "new", "ambiguous"] = Field(
        description="existing: one of the lead's contacts. new: not on file. ambiguous: could be more than one."
    )
    matched_contact_id: str = Field(
        description="The contact's id when match is existing; otherwise an empty string."
    )
    candidate_contact_ids: list[str] = Field(
        description="The possible contacts' ids when match is ambiguous; otherwise empty."
    )


class BusinessCardReading(CamelModel):
    business: BusinessRead
    people: list[PersonCardRead] = Field(
        description="One entry per person's business card. Empty when no photo names a person."
    )
    business_only_photos: list[int] = Field(
        description="Photo numbers of sides with only the business on them (shared by everyone)."
    )
    not_business_card_photos: list[int] = Field(
        description="Photo numbers that aren't business cards (storefront, flyer, menu, a person...)."
    )


# ── Response (sent to NestJS) ────────────────────────────────────────────────
#
# What Claude read, checked and cleaned up: null for anything missing, photo
# numbers turned into 0-based positions in the request's `photos`.


class Business(CamelModel):
    name: str | None = None
    email: str | None = None
    website: str | None = None
    instagram_handle: str | None = None
    address: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    other_phones: list[str] = Field(default_factory=list)
    social_handles: list[str] = Field(default_factory=list)
    suggested_industry_id: str | None = None
    suggested_business_type_id: str | None = None


class PersonCard(CamelModel):
    photos: list[int]
    first_name: str
    last_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    is_decision_maker: bool = False
    business_name: str | None = None
    same_business: Literal["yes", "no", "unclear"] = "unclear"
    match: Literal["existing", "new", "ambiguous"] = "new"
    matched_contact_id: str | None = None
    candidate_contact_ids: list[str] = Field(default_factory=list)


class BusinessCardScanResponse(CamelModel):
    business: Business
    people: list[PersonCard] = Field(default_factory=list)
    business_only_photos: list[int] = Field(default_factory=list)
    not_business_card_photos: list[int] = Field(default_factory=list)
