"""Single-user API access control.

FormIQ has no user accounts: the only requirement is that a deployed
instance isn't open to the internet, since /analyze burns CPU and
DELETE /history/{id} destroys data. So one shared secret, compared
against the X-API-Key header, guards every route except /health (which
the container healthcheck curls unauthenticated).

When FORMIQ_API_KEY is unset the guard is a no-op, which keeps local dev
and the test suite unchanged. Deployments must set it.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("FORMIQ_API_KEY")
    if not expected:
        return
    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
