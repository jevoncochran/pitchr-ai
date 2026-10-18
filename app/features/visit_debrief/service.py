"""The visit debrief feature: Claude reads the dictated note, then the answer is checked in code.

See pitchr-server's docs/visit-debrief.md for the spec.
"""

import datetime as dt
import re

from app.core.claude import generate_structured
from app.core.config import get_settings
from app.features.visit_debrief.prompt import SYSTEM_PROMPT, build_prompt
from app.features.visit_debrief.schemas import (
    DebriefRead,
    Person,
    VisitDebriefRequest,
    VisitDebriefResponse,
)

FEATURE = "visit_debrief"

# Mostly extraction, plus a short summary; the eval decides if more is needed
EFFORT = "low"

MAX_QUESTIONS = 5
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def debrief_visit(
    request: VisitDebriefRequest, model: str | None = None, effort: str = EFFORT
) -> VisitDebriefResponse:
    """Turn a dictated note into a proposal for the visit form. `model` and
    `effort` can be overridden for evals.

    Raises ClaudeError (from the Claude helper) if Claude can't produce one.
    """
    model = model or get_settings().visit_debrief_model
    read = generate_structured(
        feature=FEATURE,
        system=SYSTEM_PROMPT,
        prompt=build_prompt(request),
        output_model=DebriefRead,
        effort=effort,
        model=model,
    )
    # NestJS keeps the model with each proposal, to compare models on real notes
    return check_proposal(read, request).model_copy(update={"model": model})


def check_proposal(
    read: DebriefRead, request: VisitDebriefRequest
) -> VisitDebriefResponse:
    """Make Claude's answer safe for the form to use as is.

    - "" and "none" become None; "unclear" is no outcome.
    - A come-back date must be a real date, today or later; a time must be HH:MM.
    - Contact ids must be ones NestJS sent, and two people can't be one contact.
    """
    questions = [q.strip() for q in read.questions if q.strip()]

    come_back_estimate = read.come_back_estimated_from.strip() or None
    come_back_date = parse_date(read.come_back_date)
    if come_back_date and read.come_back_day_estimated:
        # A day estimated from a period ("next week") lands on a working day; a
        # day said exactly ("tomorrow") doesn't move, even with an estimated time
        come_back_date = first_workday(come_back_date)
    if come_back_date and come_back_date < request.today:
        come_back_date = None
    come_back_time = read.come_back_time.strip()
    if not TIME.match(come_back_time):
        come_back_time = None
    if not (come_back_date or come_back_time):
        come_back_estimate = None

    known_ids = {contact.id for contact in request.contacts}
    taken: set[str] = set()
    people: list[Person] = []
    for person in read.people:
        first_name = blank(person.first_name)
        title = blank(person.title)
        contact_id = blank(person.contact_id)
        candidates = [
            i for i in dict.fromkeys(person.candidate_contact_ids) if i in known_ids
        ]
        if contact_id and (contact_id not in known_ids or contact_id in taken):
            # An id we don't have, or one already taken by someone else: ask instead
            if contact_id in known_ids:
                candidates = [contact_id]
            contact_id = None
        if contact_id:
            candidates = []
            taken.add(contact_id)
        if not (contact_id or candidates or first_name or title):
            continue  # nobody to put on the form
        people.append(
            Person(
                contact_id=contact_id,
                candidate_contact_ids=candidates,
                first_name=first_name,
                last_name=blank(person.last_name),
                title=title,
                is_decision_maker={"yes": True, "no": False}.get(
                    person.is_decision_maker
                ),
                spoke_with=person.spoke_with,
            )
        )

    people = drop_borrowed_names(people)

    return VisitDebriefResponse(
        outcome=None if read.outcome == "unclear" else read.outcome,
        provider_type=None if read.provider_type == "none" else read.provider_type,
        come_back_date=come_back_date,
        come_back_time=come_back_time,
        come_back_estimate=come_back_estimate,
        left_materials=read.left_materials,
        summary=read.summary.strip(),
        people=people,
        questions=questions[:MAX_QUESTIONS],
    )


def blank(value: str) -> str | None:
    return value.strip() or None


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


def first_workday(day: dt.date) -> dt.date:
    """The day itself, or the next Monday to Friday that isn't a US holiday."""
    while day.weekday() >= 5 or is_holiday(day):
        day += dt.timedelta(days=1)
    return day


def is_holiday(day: dt.date) -> bool:
    """Days most local businesses' decision-makers are out: New Year's Day,
    Memorial Day, July 4th, Labor Day, Thanksgiving, Christmas."""
    if (day.month, day.day) in {(1, 1), (7, 4), (12, 25)}:
        return True
    weekday, nth = day.weekday(), (day.day - 1) // 7 + 1
    last = (day + dt.timedelta(days=7)).month != day.month
    return (
        (day.month == 5 and weekday == 0 and last)  # Memorial Day: last Monday of May
        or (
            day.month == 9 and weekday == 0 and nth == 1
        )  # Labor Day: 1st Monday of September
        or (
            day.month == 11 and weekday == 3 and nth == 4
        )  # Thanksgiving: 4th Thursday of November
    )


def drop_borrowed_names(people: list[Person]) -> list[Person]:
    """Two new people with the same name are almost always one name given to
    two people (the nameless front desk person getting the owner's name). The
    name stays with the decision-maker; the other goes back to having no name."""

    def name(p: Person) -> str:
        return " ".join(n for n in (p.first_name, p.last_name) if n).lower()

    new = [
        p
        for p in people
        if not p.contact_id and not p.candidate_contact_ids and name(p)
    ]
    result = []
    for person in people:
        twins = [p for p in new if p is not person and name(p) == name(person)]
        if (
            person in new
            and twins
            and not person.is_decision_maker
            and any(t.is_decision_maker for t in twins)
        ):
            person = person.model_copy(update={"first_name": None, "last_name": None})
            if not person.title:
                continue  # nothing left to go on
        result.append(person)
    return result
