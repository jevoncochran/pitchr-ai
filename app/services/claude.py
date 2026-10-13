"""Shared helper for calling Claude. Every Claude call in pitchr-ai goes through here.

Each call is logged with its feature, model, tokens and duration (CLAUDE.md rule 3).
"""

import logging
import time
from functools import lru_cache

import anthropic
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger("pitchr_ai.claude")

# If Claude's safety checks decline a request, Anthropic re-runs it on the
# fallback model it recommends for that case, inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


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
) -> OutputModel:
    """Ask Claude for an answer shaped exactly like `output_model`.

    `feature` names the caller in the logs, e.g. "lead_snapshot".
    Raises ClaudeError if the call fails or the answer can't be used.
    """
    model = get_settings().claude_model
    start = time.perf_counter()

    try:
        response = get_client().beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_model,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.APIError as error:
        # The SDK already retried rate limits, server errors and timeouts
        # before raising, so anything that reaches here is a real failure.
        logger.error(
            "claude_call feature=%s model=%s status=error error=%s duration_ms=%d",
            feature,
            model,
            type(error).__name__,
            elapsed_ms(start),
        )
        raise ClaudeError(f"Claude call failed: {type(error).__name__}") from error

    usage = response.usage
    logger.info(
        "claude_call feature=%s model=%s input_tokens=%d output_tokens=%d "
        "cache_read_tokens=%d duration_ms=%d stop_reason=%s request_id=%s",
        feature,
        response.model,  # can differ from `model` if the fallback ran
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
