"""Tests for diagnostics redaction helpers."""

from custom_components.pawcontrol.diagnostics_redaction import (
    compile_redaction_patterns,
    redact_sensitive_data,
)


def test_compile_redaction_patterns_normalizes_case_and_duplicates() -> None:
    """Ensure redaction keys are normalized before regex compilation."""
    patterns = compile_redaction_patterns(["Token", "TOKEN", "api_key"])

    assert len(patterns) == 2
    assert any(pattern.search("token") for pattern in patterns)
    assert any(pattern.search("api_key") for pattern in patterns)


def test_redact_sensitive_data_masks_matching_keys_and_sensitive_strings() -> None:
    """Redaction should mask configured keys and sensitive string values."""
    payload = {
        "token": "raw-token",
        "nested": {
            "email": "owner@example.com",
            "safe": "walk reminder",
            "children": [
                "d6b22bb7-f26f-4d13-8f6f-671b1a2bd2de",
                "normal value",
            ],
        },
    }

    redacted = redact_sensitive_data(
        payload,
        patterns=compile_redaction_patterns(["token"]),
    )

    assert redacted == {
        "token": "**REDACTED**",
        "nested": {
            "email": "**REDACTED**",
            "safe": "walk reminder",
            "children": ["**REDACTED**", "normal value"],
        },
    }


def test_redact_sensitive_data_preserves_non_sensitive_scalars() -> None:
    """Numeric and boolean values should be preserved during recursion."""
    payload = {
        "counter": 3,
        "enabled": True,
        "ips": ["127.0.0.1", "not-an-ip"],
    }

    redacted = redact_sensitive_data(payload, patterns=compile_redaction_patterns([]))

    assert redacted == {
        "counter": 3,
        "enabled": True,
        "ips": ["**REDACTED**", "not-an-ip"],
    }
