"""Tests for privacy and anonymization helpers."""

import hashlib
from typing import Any
from unittest.mock import Mock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.privacy import (
    DataHasher,
    PIIRedactor,
    PrivacyManager,
    RedactionRule,
    anonymize_user_id,
    mask_string,
    sanitize_return_value,
)


def test_pii_redactor_redacts_default_patterns_and_nested_values() -> None:
    """PII redaction should sanitize common patterns recursively."""
    redactor = PIIRedactor()

    payload: dict[str, Any] = {
        "email": "walker@example.com",
        "nested": {
            "phone": "503-555-1212",
            "ip": "10.0.0.7",
        },
        "list_values": [
            "4111 1111 1111 1111",
            {"ssn": "123-45-6789"},
        ],
    }

    redacted = redactor.redact_dict(payload)

    assert redacted["email"] == "[EMAIL]"
    assert redacted["nested"]["phone"] == "[PHONE]"
    assert redacted["nested"]["ip"] == "[IP_ADDRESS]"
    assert redacted["list_values"][0] == "[CREDIT_CARD]"
    assert redacted["list_values"][1]["ssn"] == "[SSN]"


def test_pii_redactor_field_name_rule_redacts_named_fields() -> None:
    """Named fields should be redacted with fixed placeholders."""
    redactor = PIIRedactor()
    redactor.add_rule(RedactionRule(field_names=["api_key", "secret"]))

    redacted = redactor.redact_dict({
        "api_key": "abc123",
        "secret": "xyz",
        "safe": "ok",
    })

    assert redacted == {"api_key": "[REDACTED]", "secret": "[REDACTED]", "safe": "ok"}


@pytest.mark.asyncio
async def test_privacy_manager_sanitizes_and_hashes_requested_fields() -> None:
    """Privacy manager should redact, anonymize GPS, and hash explicit fields."""
    manager = PrivacyManager(Mock(spec=HomeAssistant), gps_precision=2)

    payload = {
        "email": "user@example.com",
        "latitude": 45.523123,
        "longitude": -122.676543,
        "device_id": "dev-123",
    }

    result = await manager.async_sanitize_data(payload, hash_fields=["device_id"])

    assert result["email"] == "[EMAIL]"
    assert result["latitude"] == 45.52
    assert result["longitude"] == -122.68
    assert result["device_id"] == hashlib.sha256(b"dev-123").hexdigest()


@pytest.mark.asyncio
async def test_sanitize_return_value_decorator_applies_redaction_and_gps() -> None:
    """Decorator should sanitize dict return values from async callables."""

    @sanitize_return_value(redact_pii=True, anonymize_gps=True)
    async def _get_payload() -> dict[str, Any]:
        return {
            "email": "fido@example.com",
            "latitude": 40.712776,
            "longitude": -74.005974,
        }

    result = await _get_payload()

    assert result == {
        "email": "[EMAIL]",
        "latitude": 40.713,
        "longitude": -74.006,
    }


def test_hash_helpers_and_mask_utilities_are_deterministic() -> None:
    """Hashing and masking helpers should return stable, predictable output."""
    hasher = DataHasher()

    assert (
        hasher.hash_string("abc", salt="salt-")
        == hashlib.sha256(b"salt-abc").hexdigest()
    )
    assert mask_string("secret", visible_chars=2) == "se****"
    assert mask_string("dog", visible_chars=4) == "***"
    assert (
        anonymize_user_id("walker")
        == f"user_{hashlib.sha256(b'walker').hexdigest()[:8]}"
    )
