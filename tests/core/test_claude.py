"""Tests for the shared Claude helper, with a fake Anthropic client (no real calls)."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import app.core.claude as claude_service
from app.core.claude import Image, generate_structured


class Answer(BaseModel):
    text: str


@pytest.fixture
def fake_client(monkeypatch):
    """Replace the Anthropic client with one that records each request."""
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model=kwargs["model"],
            usage=SimpleNamespace(
                input_tokens=10, output_tokens=5, cache_read_input_tokens=0
            ),
            stop_reason="end_turn",
            parsed_output=Answer(text="ok"),
            _request_id="req_test",
        )

    client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(parse=parse))
    )
    monkeypatch.setattr(claude_service, "get_client", lambda: client)
    return calls


def test_text_only_prompt_is_sent_as_a_string(fake_client):
    generate_structured(feature="test", system="s", prompt="hello", output_model=Answer)

    assert fake_client[0]["messages"] == [{"role": "user", "content": "hello"}]


def test_images_come_before_the_prompt(fake_client):
    generate_structured(
        feature="test",
        system="s",
        prompt="read this",
        output_model=Answer,
        images=[Image(data="AAAA")],
    )

    content = fake_client[0]["messages"][0]["content"]
    assert content == [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"},
        },
        {"type": "text", "text": "read this"},
    ]


def test_model_override_and_default(fake_client):
    generate_structured(feature="test", system="s", prompt="p", output_model=Answer)
    generate_structured(
        feature="test",
        system="s",
        prompt="p",
        output_model=Answer,
        model="claude-opus-5-5",
    )

    assert fake_client[0]["model"] == "claude-sonnet-5-5"
    assert fake_client[1]["model"] == "claude-opus-5-5"


def test_haiku_is_sent_without_the_server_side_fallback(fake_client):
    generate_structured(
        feature="test",
        system="s",
        prompt="p",
        output_model=Answer,
        model="claude-haiku-5-5",
    )
    generate_structured(feature="test", system="s", prompt="p", output_model=Answer)

    assert "fallbacks" not in fake_client[0] and "betas" not in fake_client[0]
    assert fake_client[1]["fallbacks"] == "default"


def test_image_labels_come_just_before_their_image(fake_client):
    generate_structured(
        feature="test",
        system="s",
        prompt="read these",
        output_model=Answer,
        images=[Image(data="A", label="Photo 1"), Image(data="B", label="Photo 2")],
    )

    content = fake_client[0]["messages"][0]["content"]
    assert [block["type"] for block in content] == [
        "text",
        "image",
        "text",
        "image",
        "text",
    ]
    assert content[0]["text"] == "Photo 1"
    assert content[3]["source"]["data"] == "B"
