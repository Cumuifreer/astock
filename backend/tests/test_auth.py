import base64

from backend.app.auth import basic_auth_matches


def test_basic_auth_requires_exact_credentials_and_handles_malformed_headers():
    valid = base64.b64encode("owner:strong-password".encode()).decode()
    invalid = base64.b64encode("owner:wrong-password".encode()).decode()

    assert basic_auth_matches(f"Basic {valid}", "owner", "strong-password") is True
    assert basic_auth_matches(f"Basic {invalid}", "owner", "strong-password") is False
    assert basic_auth_matches("Basic not-base64", "owner", "strong-password") is False
    assert basic_auth_matches("", "owner", "strong-password") is False
