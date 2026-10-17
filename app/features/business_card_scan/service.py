"""The business card scan feature: Claude reads the photos, then the answer is checked in code.

See pitchr-server's docs/business-card-scan.md for the spec.
"""

from app.core.claude import Image, generate_structured
from app.core.config import get_settings
from app.features.business_card_scan.prompt import SYSTEM_PROMPT, build_prompt
from app.features.business_card_scan.schemas import (
    Business,
    BusinessCardReading,
    BusinessCardScanRequest,
    BusinessCardScanResponse,
    PersonCard,
)

FEATURE = "business_card_scan"

# Reading business cards is extraction, not judgment.
EFFORT = "low"


def scan_business_cards(
    request: BusinessCardScanRequest, model: str | None = None
) -> BusinessCardScanResponse:
    """Read one upload's photos together. `model` can be overridden for evals.

    Raises ClaudeError (from the Claude helper) if Claude can't read them.
    """
    reading = generate_structured(
        feature=FEATURE,
        system=SYSTEM_PROMPT,
        prompt=build_prompt(request),
        output_model=BusinessCardReading,
        effort=EFFORT,
        images=[
            Image(data=photo.data, media_type=photo.media_type, label=f"Photo {i}")
            for i, photo in enumerate(request.photos, start=1)
        ],
        model=model or get_settings().business_card_scan_model,
    )
    return check_reading(reading, request)


def check_reading(
    reading: BusinessCardReading, request: BusinessCardScanRequest
) -> BusinessCardScanResponse:
    """Make Claude's answer consistent, so NestJS can apply it without second-guessing.

    - Photo numbers become 0-based positions; each photo is used once, and a
      photo Claude left out (or a person without a readable name) counts as a
      side with only the business on it, so it's still kept with the lead.
    - Contact ids must be ones NestJS sent, and two people can't be one contact.
    - Empty strings ("" for anything missing) become None.
    """
    photo_count = len(request.photos)
    used: set[int] = set()

    def take(numbers: list[int]) -> list[int]:
        positions = []
        for number in numbers:
            position = number - 1
            if 0 <= position < photo_count and position not in used:
                used.add(position)
                positions.append(position)
        return positions

    known_ids = {contact.id for contact in request.contacts}
    matched_ids: set[str] = set()
    people: list[PersonCard] = []
    for person in reading.people:
        first_name = person.first_name.strip()
        if not first_name:
            continue
        photos = take(person.photos)
        if not photos:
            continue

        match = person.match
        matched_id = person.matched_contact_id.strip() or None
        candidates = [i for i in person.candidate_contact_ids if i in known_ids]
        if request.is_new_lead:
            match, matched_id, candidates = "new", None, []
        if match == "existing" and (
            matched_id not in known_ids or matched_id in matched_ids
        ):
            # A contact we don't have, or one already taken by another card:
            # let the owner pick instead
            candidates = [matched_id] if matched_id in known_ids else candidates
            match, matched_id = "ambiguous", None
        if match == "ambiguous" and not candidates:
            candidates = sorted(known_ids - matched_ids)
        if match == "ambiguous" and not candidates:
            match = "new"  # nobody on file to choose from
        if match != "existing":
            matched_id = None
        if match != "ambiguous":
            candidates = []
        if matched_id:
            matched_ids.add(matched_id)

        people.append(
            PersonCard(
                photos=photos,
                first_name=first_name,
                last_name=blank(person.last_name),
                title=blank(person.title),
                email=lower(person.email),
                phone=blank(person.phone),
                is_decision_maker=person.is_decision_maker,
                business_name=blank(person.business_name),
                same_business=person.same_business,
                match=match,
                matched_contact_id=matched_id,
                candidate_contact_ids=candidates,
            )
        )

    business_only = take(reading.business_only_photos)
    not_cards = take(reading.not_business_card_photos)
    business_only += [p for p in range(photo_count) if p not in used]

    read = reading.business
    industry_ids = {o.id for o in request.industries}
    type_ids = {o.id for o in request.business_types}
    business = Business(
        name=blank(read.name),
        email=lower(read.email),
        website=blank(read.website),
        instagram_handle=clean_handle(read.instagram_handle),
        address=blank(read.address),
        address_line1=blank(read.address_line1),
        city=blank(read.city),
        state=blank(read.state),
        zip=blank(read.zip),
        other_phones=[p.strip() for p in read.other_phones if p.strip()],
        social_handles=[h.strip() for h in read.social_handles if h.strip()],
        # Suggestions only from the lists sent (a new lead)
        suggested_industry_id=read.suggested_industry_id
        if read.suggested_industry_id in industry_ids
        else None,
        suggested_business_type_id=read.suggested_business_type_id
        if read.suggested_business_type_id in type_ids
        else None,
    )

    return BusinessCardScanResponse(
        business=business,
        people=people,
        business_only_photos=sorted(business_only),
        not_business_card_photos=sorted(not_cards),
    )


def blank(value: str) -> str | None:
    return value.strip() or None


def lower(value: str) -> str | None:
    return value.strip().lower() or None


def clean_handle(handle: str) -> str | None:
    """ "@lopezmedspa", "instagram.com/lopezmedspa/" and "lopezmedspa" are the same handle."""
    handle = handle.strip().rstrip("/").split("/")[-1].lstrip("@").strip()
    return handle or None
