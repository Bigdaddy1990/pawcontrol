"""Tests for diagnostics redaction helpers."""

from custom_components.pawcontrol.diagnostics_redaction import (
    compile_redaction_patterns,
    redact_sensitive_data,
)


def test_compile_redaction_patterns_normalizes_and_deduplicates_keys() -> None:
    """Patterns should be deterministic and case-insensitive by key normalization."""
    patterns = compile_redaction_patterns(["Token", "token", "api_key"])

    assert len(patterns) == 2
    assert any(pattern.search("token") for pattern in patterns)
    assert any(pattern.search("api_key") for pattern in patterns)


def test_redact_sensitive_data_redacts_nested_mapping_keys() -> None:
    """Sensitive keys and nested values should be recursively redacted."""
    payload = {
        "token": "plain-text",
        "profile": {
            "email": "guardian@example.com",
            "safe": "neighborhood park",
        },
        "events": [{"api_key": "abcdef"}, {"note": "keep me"}],
    }

    redacted = redact_sensitive_data(
        payload,
        patterns=compile_redaction_patterns(["token", "api_key"]),
    )

    assert redacted["token"] == "**REDACTED**"
    assert redacted["profile"]["email"] == "**REDACTED**"
    assert redacted["profile"]["safe"] == "neighborhood park"
    assert redacted["events"][0]["api_key"] == "**REDACTED**"
    assert redacted["events"][1]["note"] == "keep me"


def test_redact_sensitive_data_preserves_non_sensitive_scalar_types() -> None:
    """Scalar values that are not strings should pass through unchanged."""
    payload = {
        "count": 3,
        "active": True,
        "ratio": 0.5,
        "nullable": None,
    }

    redacted = redact_sensitive_data(payload, patterns=compile_redaction_patterns([]))

    assert redacted == payload


def test_redact_sensitive_data_redacts_common_sensitive_string_formats() -> None:
    """UUIDs, IPs, MAC addresses and long tokens should be redacted."""
    payload = {
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "ipv4": "192.168.10.3",
        "mac": "AA:BB:CC:DD:EE:FF",
        "token_like": "A12345678901234567890",
    }

    redacted = redact_sensitive_data(payload, patterns=compile_redaction_patterns([]))

    assert set(redacted.values()) == {"**REDACTED**"}
