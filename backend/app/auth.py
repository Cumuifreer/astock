from __future__ import annotations

import base64
import binascii
import secrets


def basic_auth_matches(authorization: str, username: str, password: str) -> bool:
    if not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
        provided_username, provided_password = decoded.split(":", 1)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False
    return secrets.compare_digest(provided_username, username) and secrets.compare_digest(
        provided_password,
        password,
    )
