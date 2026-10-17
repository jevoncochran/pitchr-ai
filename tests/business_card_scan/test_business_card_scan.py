"""Tests for POST /business-cards/scan, with Claude faked so they're free and fast."""

import pytest
from anthropic.lib._parse._transform import transform_schema

import app.features.business_card_scan.service as business_card_scan_service
from app.core.claude import ClaudeError
from app.features.business_card_scan.prompt import build_prompt
from app.features.business_card_scan.schemas import (
    BusinessCardReading,
    BusinessCardScanRequest,
    BusinessRead,
    PersonCardRead,
)

CONTACTS = [
    {"id": "c-maria", "firstName": "Maria", "title": "Owner", "isDecisionMaker": True},
    {"id": "c-jen", "firstName": "Jen", "lastName": "Park"},
]


def body(photos: int = 1, **over):
    """A request from NestJS for an existing lead, with `photos` photos."""
    return {
        "photos": [{"data": f"P{i}"} for i in range(photos)],
        "business": "Lopez Med Spa",
        "contacts": CONTACTS,
        **over,
    }


NEW_LEAD = {
    "business": None,
    "contacts": [],
    "industries": [{"id": "i-aesthetics", "name": "Aesthetics"}],
    "businessTypes": [{"id": "t-medspa", "name": "Med spa"}],
}


def business(**fields) -> BusinessRead:
    text = {
        name: ""
        for name, info in BusinessRead.model_fields.items()
        if info.annotation is str
    }
    return BusinessRead(**{**text, "other_phones": [], "social_handles": [], **fields})


def person(photos: list[int], first_name: str, **fields) -> PersonCardRead:
    text = {
        name: ""
        for name, info in PersonCardRead.model_fields.items()
        if info.annotation is str
    }
    return PersonCardRead(
        **{
            **text,
            "photos": photos,
            "first_name": first_name,
            "is_decision_maker": False,
            "same_business": "yes",
            "match": "new",
            "candidate_contact_ids": [],
            **fields,
        }
    )


def reading(
    people=(), business_only=(), not_cards=(), **business_fields
) -> BusinessCardReading:
    return BusinessCardReading(
        business=business(**business_fields),
        people=list(people),
        business_only_photos=list(business_only),
        not_business_card_photos=list(not_cards),
    )


@pytest.fixture
def fake_claude(monkeypatch):
    """Make Claude return whatever reading a test sets; record each call."""
    state = {"reading": reading(), "calls": []}

    def fake_generate_structured(**kwargs):
        state["calls"].append(kwargs)
        if isinstance(state["reading"], Exception):
            raise state["reading"]
        return state["reading"]

    monkeypatch.setattr(
        business_card_scan_service, "generate_structured", fake_generate_structured
    )
    return state


def test_schema_stays_within_the_structured_output_limits():
    """The API refuses (400) more than 16 union-typed or 24 optional parameters, in total."""
    schema = transform_schema(BusinessCardReading)
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


def test_sends_each_photo_labeled_and_the_contacts(client, fake_claude):
    client.post("/business-cards/scan", json=body(photos=3))

    call = fake_claude["calls"][0]
    assert call["feature"] == "business_card_scan"
    assert [(i.label, i.data) for i in call["images"]] == [
        ("Photo 1", "P0"),
        ("Photo 2", "P1"),
        ("Photo 3", "P2"),
    ]
    assert "id c-maria: Maria (title: Owner, decision-maker)" in call["prompt"]
    assert "Read the 3 photos above." in call["prompt"]


def test_three_people_and_a_shared_back(client, fake_claude):
    fake_claude["reading"] = reading(
        people=[
            person(
                [1],
                "María",
                last_name="López",
                email="Maria@LopezMedSpa.com",
                match="existing",
                matched_contact_id="c-maria",
            ),
            person([2], "Sam", title="Marketing coordinator"),
            person([3], "Ana", title="Aesthetician"),
        ],
        business_only=[4],
        name="Lopez Med Spa",
        website="lopezmedspa.com",
        instagram_handle="@lopezmedspa",
    )

    data = client.post("/business-cards/scan", json=body(photos=4)).json()

    assert [p["firstName"] for p in data["people"]] == ["María", "Sam", "Ana"]
    assert [p["photos"] for p in data["people"]] == [[0], [1], [2]]
    assert data["people"][0]["email"] == "maria@lopezmedspa.com"
    assert data["people"][0]["matchedContactId"] == "c-maria"
    assert data["people"][1]["lastName"] is None
    assert data["businessOnlyPhotos"] == [3]
    assert data["business"]["name"] == "Lopez Med Spa"
    assert data["business"]["instagramHandle"] == "lopezmedspa"
    assert data["business"]["email"] is None


def test_a_person_with_their_own_back(client, fake_claude):
    fake_claude["reading"] = reading(people=[person([1, 2], "María")])

    data = client.post("/business-cards/scan", json=body(photos=2)).json()

    assert data["people"][0]["photos"] == [0, 1]
    assert data["businessOnlyPhotos"] == []


def test_each_photo_is_used_once_and_bad_numbers_are_dropped(client, fake_claude):
    fake_claude["reading"] = reading(
        people=[person([1, 9], "María"), person([1], "Sam"), person([2], "Ana")],
        not_cards=[2, 3],
    )

    data = client.post("/business-cards/scan", json=body(photos=3)).json()

    # Sam's only photo was already María's, so Sam is dropped
    assert [p["firstName"] for p in data["people"]] == ["María", "Ana"]
    assert data["people"][0]["photos"] == [0]
    assert data["notBusinessCardPhotos"] == [2]


def test_photos_left_out_are_kept_as_business_only(client, fake_claude):
    fake_claude["reading"] = reading(people=[person([1], "María"), person([2], "  ")])

    data = client.post("/business-cards/scan", json=body(photos=3)).json()

    assert [p["firstName"] for p in data["people"]] == ["María"]
    assert data["businessOnlyPhotos"] == [1, 2]


def test_a_card_for_another_business_is_reported(client, fake_claude):
    fake_claude["reading"] = reading(
        people=[
            person([1], "Tom", business_name="Bright Smile Dental", same_business="no")
        ]
    )

    data = client.post("/business-cards/scan", json=body()).json()

    assert data["people"][0]["sameBusiness"] == "no"
    assert data["people"][0]["businessName"] == "Bright Smile Dental"


def test_unknown_or_repeated_contacts_become_a_choice(client, fake_claude):
    fake_claude["reading"] = reading(
        people=[
            person([1], "María", match="existing", matched_contact_id="c-maria"),
            person([2], "Maria", match="existing", matched_contact_id="c-maria"),
            person([3], "Jen", match="existing", matched_contact_id="c-made-up"),
        ]
    )

    people = client.post("/business-cards/scan", json=body(photos=3)).json()["people"]

    assert people[0]["match"] == "existing"
    # The same contact can't be two people: the second one asks
    assert people[1]["match"] == "ambiguous"
    assert people[1]["candidateContactIds"] == ["c-maria"]
    # An id NestJS didn't send never becomes a match
    assert people[2]["match"] == "ambiguous"
    assert people[2]["matchedContactId"] is None
    assert people[2]["candidateContactIds"] == ["c-jen"]


def test_ambiguous_with_nobody_on_file_is_new(client, fake_claude):
    fake_claude["reading"] = reading(people=[person([1], "María", match="ambiguous")])

    data = client.post("/business-cards/scan", json=body(contacts=[])).json()

    assert data["people"][0]["match"] == "new"


def test_new_lead_lists_the_options_and_checks_suggestions(client, fake_claude):
    fake_claude["reading"] = reading(
        people=[person([1], "María", match="existing", matched_contact_id="c-maria")],
        name="Lopez Med Spa",
        email="Info@LopezMedSpa.com",
        suggested_industry_id="i-aesthetics",
        suggested_business_type_id="t-made-up",
    )

    data = client.post("/business-cards/scan", json=body(**NEW_LEAD)).json()

    prompt = fake_claude["calls"][0]["prompt"]
    assert "start a new lead" in prompt
    assert "- id i-aesthetics: Aesthetics" in prompt
    assert "Contacts on file" not in prompt
    assert data["business"]["email"] == "info@lopezmedspa.com"
    assert data["business"]["suggestedIndustryId"] == "i-aesthetics"
    # Not in the list sent: never passed on
    assert data["business"]["suggestedBusinessTypeId"] is None
    # Nobody is on file for a new lead
    assert data["people"][0]["match"] == "new"
    assert data["people"][0]["matchedContactId"] is None


def test_at_most_six_photos(client, fake_claude):
    assert client.post("/business-cards/scan", json=body(photos=7)).status_code == 422
    assert client.post("/business-cards/scan", json=body(photos=0)).status_code == 422


def test_claude_failure_is_a_502(client, fake_claude):
    fake_claude["reading"] = ClaudeError("nope")

    assert client.post("/business-cards/scan", json=body()).status_code == 502


def test_prompt_says_when_there_are_no_contacts():
    request = BusinessCardScanRequest(photos=[{"data": "A"}], business="X", contacts=[])

    prompt = build_prompt(request)

    assert "(none)" in prompt
    assert "Read the 1 photo above." in prompt
