"""Only callers that know the shared secret (NestJS) may use the API.

The check runs on every route automatically (it's attached to the whole app in
main.py). The only way to make a route public is to add it to PUBLIC_PATHS.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

# Routes anyone can call. Everything else requires the shared secret.
# /health stays open because Railway's health checks can't send headers.
PUBLIC_PATHS = {"/health"}

# Declaring the header this way also adds an "Authorize" button to /docs.
# auto_error=False: we raise the 401 ourselves, after checking PUBLIC_PATHS.
api_key_header = APIKeyHeader(name="X-Internal-Api-Key", auto_error=False)


def require_api_key(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    api_key: Annotated[str | None, Depends(api_key_header)],
) -> None:
    """Reject the request unless its X-Internal-Api-Key header matches our secret."""
    if request.url.path in PUBLIC_PATHS:
        return

    expected = settings.pitchr_ai_api_key.get_secret_value()
    # compare_digest takes the same time whether the first or last character is
    # wrong, so the key can't be guessed one character at a time by timing responses.
    if api_key is None or not secrets.compare_digest(
        api_key.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
