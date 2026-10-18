"""Tests for POST /visits/debrief, with Claude faked so they're free and fast."""

import pytest
from anthropic.lib._parse._transform import transform_schema

import app.features.visit_debrief.service as visit_debrief_service
from app.core.claude import ClaudeError
from app.features.visit_debrief.prompt import build_prompt
from app.features.visit_debrief.schemas import (
    DebriefRead,
    PersonRead,
    VisitDebriefRequest,
)
from app.features.visit_debrief.service import first_workday, is_holiday

BODY = {
    "today": "2026-10-16",
    "note": "Spoke with Jen at the front desk. Owner is Maria, in on Thursdays. Left a card.",
    "lead": {
        "business": "Lopez Med Spa",
        "industry": "Aesthetics",
        "pipelineStage": "CONTACTED",
    },
    "contacts": [
        {
            "id": "c-maria",
            "firstName": "María",
            "lastName": "López",
            "title": "Owner",
            "isDecisionMaker": True,
        },
        {
            "id": "c-maria-g",
            "firstName": "Maria",
            "lastName": "Gomez",
            "title": "Office manager",
        },
    ],
    "recentTouchpoints": [
        {
            "date": "2026-10-01T15:00:00Z",
            "type": "IN_PERSON",
            "summary": "Owner not in, try Thursday",
        },
    ],
}


def person(**fields) -> PersonRead:
    return PersonRead(
        **{
            "contact_id": "",
            "candidate_contact_ids": [],
            "first_name": "",
            "last_name": "",
            "title": "",
            "is_decision_maker": "unknown",
            "spoke_with": False,
            **fields,
        }
    )


def read(**fields) -> DebriefRead:
    return DebriefRead(
        **{
            "outcome": "COME_BACK_LATER",
            "provider_type": "none",
            "come_back_date": "",
            "come_back_time": "",
            "come_back_day_estimated": False,
            "come_back_estimated_from": "",
            "left_materials": False,
            "summary": " We spoke with Jen. ",
            "people": [],
            "questions": [],
            **fields,
        }
    )


@pytest.fixture
def fake_claude(monkeypatch):
    state = {"read": read(), "calls": []}

    def fake_generate_structured(**kwargs):
        state["calls"].append(kwargs)
        if isinstance(state["read"], Exception):
            raise state["read"]
        return state["read"]

    monkeypatch.setattr(
        visit_debrief_service, "generate_structured", fake_generate_structured
    )
    return state


def test_schema_stays_within_the_structured_output_limits():
    """The API refuses (400) more than 16 union-typed or 24 optional parameters, in total."""
    schema = transform_schema(DebriefRead)
    definitions = schema.get("$defs", {})
    unions, optional = [], []

    def walk(node):
        if "$ref" in node:
            node = definitions[node["$ref"].split("/")[-1]]
        required = set(node.get("required", []))
        for name, prop in node.get("properties", {}).items():
            if name not in required:
                optional.append(name)
            if "anyOf" in prop or isinstance(prop.get("type"), list):
                unions.append(name)
            walk(prop.get("items", prop) if prop.get("type") == "array" else prop)

    walk(schema)
    assert unions == []
    assert optional == []


def test_prompt_has_a_calendar_the_lead_contacts_touchpoints_and_the_note():
    prompt = build_prompt(VisitDebriefRequest(**BODY))

    assert "Today is Friday, 10/16/26 (2026-10-16)." in prompt
    assert "Fri 10/16/26 = 2026-10-16 (today)" in prompt
    assert "Thu 10/22/26 = 2026-10-22" in prompt
    assert "Mon 11/16/26 = 2026-11-16" in prompt
    assert "Business: Lopez Med Spa" in prompt
    assert "- id c-maria: María López (Owner, decision-maker)" in prompt
    assert "- id c-maria-g: Maria Gomez (Office manager)" in prompt
    assert "- 10/1/26, IN_PERSON: Owner not in, try Thursday" in prompt
    assert prompt.endswith("<note>\n" + BODY["note"] + "\n</note>")


def test_returns_the_proposal_as_camel_case(client, fake_claude):
    fake_claude["read"] = read(
        outcome="COME_BACK_LATER",
        provider_type="MARKETING_AGENCY",
        come_back_date="2026-10-22",
        come_back_time="14:00",
        left_materials=True,
        people=[
            person(
                first_name="Jen",
                title="front desk",
                spoke_with=True,
                is_decision_maker="no",
            ),
            person(
                contact_id="c-maria",
                first_name="María",
                last_name="López",
                title="owner",
                is_decision_maker="yes",
            ),
        ],
        questions=["  ", "Check Maria's email against her card"],
    )

    response = client.post("/visits/debrief", json=BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "claude-haiku-5-5"
    assert body["outcome"] == "COME_BACK_LATER"
    assert body["providerType"] == "MARKETING_AGENCY"
    assert body["comeBackDate"] == "2026-10-22"
    assert body["comeBackTime"] == "14:00"
    assert body["leftMaterials"] is True
    assert body["summary"] == "We spoke with Jen."
    assert body["people"][0] == {
        "contactId": None,
        "candidateContactIds": [],
        "firstName": "Jen",
        "lastName": None,
        "title": "front desk",
        "isDecisionMaker": False,
        "spokeWith": True,
    }
    assert body["people"][1]["contactId"] == "c-maria"
    assert body["people"][1]["isDecisionMaker"] is True
    assert body["questions"] == ["Check Maria's email against her card"]


def test_unclear_and_none_become_null(client, fake_claude):
    fake_claude["read"] = read(outcome="unclear", provider_type="none")

    body = client.post("/visits/debrief", json=BODY).json()

    assert body["outcome"] is None
    assert body["providerType"] is None


@pytest.mark.parametrize(
    ("date", "time", "expected_date", "expected_time"),
    [
        ("2026-10-15", "15:00", None, "15:00"),  # yesterday: dropped
        ("next thursday", "3pm", None, None),  # not a date or a time
        ("2026-02-30", "25:00", None, None),  # not real
        ("2026-10-16", "09:30", "2026-10-16", "09:30"),  # today is fine
    ],
)
def test_come_back_date_and_time_must_be_real(
    client, fake_claude, date, time, expected_date, expected_time
):
    fake_claude["read"] = read(come_back_date=date, come_back_time=time)

    body = client.post("/visits/debrief", json=BODY).json()

    assert body["comeBackDate"] == expected_date
    assert body["comeBackTime"] == expected_time


def test_unknown_or_repeated_contacts_become_a_choice(client, fake_claude):
    fake_claude["read"] = read(
        people=[
            person(contact_id="c-maria", first_name="María"),
            person(contact_id="c-maria", first_name="Maria"),
            person(contact_id="c-made-up", first_name="Jen"),
            person(
                candidate_contact_ids=["c-maria", "c-maria-g", "c-ghost"],
                first_name="Maria",
            ),
        ]
    )

    people = client.post("/visits/debrief", json=BODY).json()["people"]

    assert people[0]["contactId"] == "c-maria"
    # The same contact can't be two people: the second one asks
    assert (people[1]["contactId"], people[1]["candidateContactIds"]) == (
        None,
        ["c-maria"],
    )
    # An id NestJS didn't send: a new person, by name
    assert (people[2]["contactId"], people[2]["candidateContactIds"]) == (None, [])
    assert people[2]["firstName"] == "Jen"
    # Only candidates NestJS sent
    assert people[3]["candidateContactIds"] == ["c-maria", "c-maria-g"]


def test_people_with_nothing_to_go_on_are_dropped(client, fake_claude):
    fake_claude["read"] = read(
        people=[person(), person(title="manager", spoke_with=True)]
    )

    people = client.post("/visits/debrief", json=BODY).json()["people"]

    assert [p["title"] for p in people] == ["manager"]


def test_sends_the_prompt_to_claude(client, fake_claude):
    client.post("/visits/debrief", json=BODY)

    call = fake_claude["calls"][0]
    assert call["feature"] == "visit_debrief"
    assert call["effort"] == "low"
    assert call["model"] == "claude-haiku-5-5"
    assert "<note>" in call["prompt"]


def test_claude_failure_is_a_502(client, fake_claude):
    fake_claude["read"] = ClaudeError("nope")

    assert client.post("/visits/debrief", json=BODY).status_code == 502


def test_requires_a_note(client, fake_claude):
    assert client.post("/visits/debrief", json={**BODY, "note": ""}).status_code == 422


@pytest.mark.parametrize(
    ("date", "estimated_from", "expected"),
    [
        ("2026-10-19", "next week", "2026-10-19"),  # already a Monday
        ("2026-11-01", "next month", "2026-11-02"),  # a Sunday: the Monday after
        ("2027-01-01", "in January", "2027-01-04"),  # New Year's Day, then a weekend
        ("2026-11-26", "after Thanksgiving week", "2026-11-27"),  # Thanksgiving
        (
            "2026-10-17",
            "",
            "2026-10-17",
        ),  # "tomorrow" (a Saturday) said exactly: not moved
    ],
)
def test_an_estimated_date_lands_on_a_workday(
    client, fake_claude, date, estimated_from, expected
):
    fake_claude["read"] = read(
        come_back_date=date,
        come_back_day_estimated=bool(estimated_from),
        come_back_estimated_from=estimated_from,
    )

    body = client.post("/visits/debrief", json=BODY).json()

    assert body["comeBackDate"] == expected
    assert body["comeBackEstimate"] == (estimated_from or None)


def test_an_estimated_time_is_marked(client, fake_claude):
    fake_claude["read"] = read(
        come_back_date="2026-10-17",
        come_back_time="13:00",
        come_back_estimated_from="tomorrow afternoon",
    )

    body = client.post("/visits/debrief", json=BODY).json()

    assert (body["comeBackDate"], body["comeBackTime"], body["comeBackEstimate"]) == (
        "2026-10-17",
        "13:00",
        "tomorrow afternoon",
    )


def test_no_estimate_without_a_date_or_time(client, fake_claude):
    fake_claude["read"] = read(come_back_estimated_from="soon")

    assert client.post("/visits/debrief", json=BODY).json()["comeBackEstimate"] is None


def test_holidays():
    import datetime as dt

    holidays = [
        "2026-01-01",
        "2026-05-25",
        "2026-07-04",
        "2026-09-07",
        "2026-11-26",
        "2026-12-25",
    ]
    assert all(is_holiday(dt.date.fromisoformat(d)) for d in holidays)
    assert not any(
        is_holiday(dt.date.fromisoformat(d))
        for d in ["2026-05-18", "2026-09-14", "2026-11-19"]
    )
    assert first_workday(dt.date(2026, 12, 25)) == dt.date(2026, 12, 28)


def test_a_name_borrowed_from_the_owner_is_dropped(client, fake_claude):
    fake_claude["read"] = read(
        people=[
            person(
                last_name="Kim",
                title="front desk",
                spoke_with=True,
                is_decision_maker="no",
            ),
            person(last_name="Kim", title="owner", is_decision_maker="yes"),
        ]
    )

    people = client.post("/visits/debrief", json=BODY).json()["people"]

    assert [(p["lastName"], p["title"]) for p in people] == [
        (None, "front desk"),
        ("Kim", "owner"),
    ]
