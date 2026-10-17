"""Shared helper for calling Claude. Every Claude call in pitchr-ai goes through here.

Each call is logged with its feature, model, tokens and duration (CLAUDE.md rule 3).
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import anthropic
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger("pitchr_ai.claude")

# If Claude's safety checks decline a request, Anthropic re-runs it on the
# fallback model it recommends for that case, inside the same call.
# Haiku has no server-side fallback, so it's sent without one.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def supports_fallback(model: str) -> bool:
    return not model.startswith("claude-haiku-")


@dataclass(frozen=True)
class Image:
    """An image for Claude to read: base64 data (no newlines) and its media type."""

    data: str
    media_type: str = "image/jpeg"
    # Shown just before the image (e.g. "Photo 2"), so the answer can refer to it
    label: str | None = None


class ClaudeError(Exception):
    """Claude couldn't produce a usable answer."""


@lru_cache
def get_client() -> anthropic.Anthropic:
    """Create the Anthropic client once and reuse it."""
    api_key = get_settings().anthropic_api_key.get_secret_value()
    return anthropic.Anthropic(api_key=api_key)


# [OutputModel: BaseModel] means "some Pydantic model": the function returns
# an instance of whichever model it was given.
def generate_structured[OutputModel: BaseModel](
    *,
    feature: str,
    system: str,
    prompt: str,
    output_model: type[OutputModel],
    effort: str = "medium",
    max_tokens: int = 16000,
    images: Sequence[Image] = (),
    model: str | None = None,
) -> OutputModel:
    """Ask Claude for an answer shaped exactly like `output_model`.

    `feature` names the caller in the logs, e.g. "lead_snapshot".
    `images` are shown to Claude before the prompt. `model` overrides the
    CLAUDE_MODEL setting for features that use a different model.
    Raises ClaudeError if the call fails or the answer can't be used.
    """
    model = model or get_settings().claude_model
    start = time.perf_counter()

    content: str | list[dict] = prompt
    if images:
        content = []
        for image in images:
            if image.label:
                content.append({"type": "text", "text": image.label})
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": image.data,
                    },
                }
            )
        content.append({"type": "text", "text": prompt})

    fallback = (
        {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        if supports_fallback(model)
        else {}
    )

    try:
        response = get_client().beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=output_model,
            output_config={"effort": effort},
            **fallback,
        )
    except anthropic.APIError as error:
        # The SDK already retried rate limits, server errors and timeouts
        # before raising, so anything that reaches here is a real failure.
        # Anthropic's message says why (e.g. a 400 for a schema that's too
        # complex); it describes the request, never the lead's data
        logger.error(
            "claude_call feature=%s model=%s status=error error=%s duration_ms=%d message=%s",
            feature,
            model,
            type(error).__name__,
            elapsed_ms(start),
            str(getattr(error, "message", error))[:300],
        )
        raise ClaudeError(f"Claude call failed: {type(error).__name__}") from error

    usage = response.usage
    logger.info(
        "claude_call feature=%s model=%s images=%d input_tokens=%d output_tokens=%d "
        "cache_read_tokens=%d duration_ms=%d stop_reason=%s request_id=%s",
        feature,
        response.model,  # can differ from `model` if the fallback ran
        len(images),
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_input_tokens or 0,
        elapsed_ms(start),
        response.stop_reason,
        response._request_id,
    )

    if response.stop_reason == "refusal":
        raise ClaudeError("Claude declined the request")
    if response.stop_reason == "max_tokens":
        raise ClaudeError("Claude's answer was cut off (hit max_tokens)")
    if response.parsed_output is None:
        raise ClaudeError("Claude's answer didn't match the expected format")

    return response.parsed_output


def elapsed_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)
