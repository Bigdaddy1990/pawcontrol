"""Tests for privacy utilities."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest

from custom_components.pawcontrol.privacy import (
    DataHasher,
    GPSAnonymizer,
    PIIRedactor,
    PrivacyManager,
    RedactionRule,
    anonymize_user_id,
    mask_string,
    sanitize_return_value,
)


def test_pii_redactor_redacts_common_patterns() -> None:
    """Default redaction rules should sanitize known PII patterns."""
    redactor = PIIRedactor()

    text = (
        "email me at person@example.com, call 555-123-4567, "
        "host 10.1.2.3, card 4111-1111-1111-1111, ssn 123-45-6789"
    )

    redacted = redactor.redact_text(text)

    assert "person@example.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "10.1.2.3" not in redacted
    assert "4111-1111-1111-1111" not in redacted
    assert "123-45-6789" not in redacted
    assert "[EMAIL]" in redacted
    assert "[PHONE]" in redacted
    assert "[IP_ADDRESS]" in redacted
    assert "[CREDIT_CARD]" in redacted
    assert "[SSN]" in redacted


def test_pii_redactor_supports_field_and_custom_rules() -> None:
    """Redaction rules should support field-name and callable redactors."""
    redactor = PIIRedactor()
    redactor.add_rule(RedactionRule(field_names=["secret_key"]))
    redactor.add_rule(
        RedactionRule(
            pattern=None,
            redactor=lambda value: value.replace("dog_id_123", "[DOG_ID]"),
        )
    )

    payload: dict[str, Any] = {
        "secret_key": "api-token",
        "note": "linked to dog_id_123",
    }

    redacted = redactor.redact_dict(payload)

    assert redacted["secret_key"] == "[REDACTED]"
    assert redacted["note"] == "linked to [DOG_ID]"


def test_pii_redactor_recursive_toggle() -> None:
    """Recursive redaction should be optional for nested structures."""
    redactor = PIIRedactor()
    nested = {"outer": {"email": "person@example.com"}}

    shallow = redactor.redact_dict(nested, recursive=False)
    deep = redactor.redact_dict(nested, recursive=True)

    assert shallow == nested
    assert deep["outer"]["email"] == "[EMAIL]"


def test_gps_anonymizer_rounds_coordinates_and_dict_keys() -> None:
    """GPS anonymizer should round tuple and dict-based coordinates."""
    anonymizer = GPSAnonymizer(precision=2)

    assert anonymizer.anonymize(45.523123, -122.676543) == (45.52, -122.68)

    result = anonymizer.anonymize_dict(
        {"lat": 12.3456, "lon": 78.9012}, lat_key="lat", lon_key="lon"
    )
    assert result == {"lat": 12.35, "lon": 78.9}


def test_data_hasher_hash_string_and_selected_fields() -> None:
    """Hasher should apply chosen algorithm and hash only requested string fields."""
    hasher = DataHasher(algorithm="sha256")

    expected = hashlib.sha256(b"saltvalue").hexdigest()
    assert hasher.hash_string("value", salt="salt") == expected

    hashed = hasher.hash_dict(
        {"device_id": "abc", "count": 3}, ["device_id", "count"], salt="x"
    )
    assert hashed["device_id"] == hashlib.sha256(b"xabc").hexdigest()
    assert hashed["count"] == 3


@pytest.mark.asyncio
async def test_privacy_manager_sanitizes_and_prepares_diagnostics() -> None:
    """Privacy manager should combine redaction, GPS anonymization, and hashing."""
    manager = PrivacyManager(hass=object())

    sanitized = await manager.async_sanitize_data(
        {
            "email": "person@example.com",
            "latitude": 12.34567,
            "longitude": 45.67891,
            "device_id": "dog-1",
        },
        hash_fields=["device_id"],
    )
    diagnostics = await manager.async_prepare_diagnostics({
        "mac_address": "aa:bb:cc:dd:ee:ff",
        "device_id": "dog-1",
    })

    assert sanitized["email"] == "[EMAIL]"
    assert sanitized["latitude"] == 12.346
    assert sanitized["longitude"] == 45.679
    assert sanitized["device_id"] != "dog-1"
    assert diagnostics["mac_address"] != "aa:bb:cc:dd:ee:ff"
    assert diagnostics["device_id"] != "dog-1"


@pytest.mark.asyncio
async def test_sanitize_return_value_decorator_handles_toggles() -> None:
    """Decorator should sanitize dict responses and ignore non-dict values."""

    @sanitize_return_value(redact_pii=True, anonymize_gps=True)
    async def get_payload() -> dict[str, Any]:
        return {
            "email": "person@example.com",
            "latitude": 1.23456,
            "longitude": 2.34567,
        }

    @sanitize_return_value(redact_pii=False, anonymize_gps=False)
    async def get_raw() -> dict[str, Any]:
        return {"email": "person@example.com"}

    @sanitize_return_value()
    async def get_scalar() -> str:
        return "plain-text"

    payload = await get_payload()
    raw = await get_raw()
    scalar = await get_scalar()

    assert payload["email"] == "[EMAIL]"
    assert payload["latitude"] == 1.235
    assert payload["longitude"] == 2.346
    assert raw["email"] == "person@example.com"
    assert scalar == "plain-text"


def test_mask_and_user_id_helpers() -> None:
    """Utility helpers should mask strings and anonymize IDs."""
    assert mask_string("secret", visible_chars=2) == "se****"
    assert mask_string("abc", visible_chars=4) == "***"

    anon = anonymize_user_id("user_12345")
    assert re.fullmatch(r"user_[0-9a-f]{8}", anon)
