"""Tests for webhook security helpers."""

import pytest

from custom_components.pawcontrol.exceptions import (
    AuthenticationError,
    RateLimitError,
    ValidationError,
)
from custom_components.pawcontrol.webhook_security import (
    RateLimitConfig,
    WebhookAuthenticator,
    WebhookRateLimiter,
    WebhookRequest,
    WebhookSecurityManager,
    WebhookValidator,
)


def test_webhook_authenticator_validates_signature() -> None:
    """Authenticator should accept the generated HMAC signature."""
    auth = WebhookAuthenticator(secret="test-secret")

    signature, timestamp = auth.generate_signature(b'{"event":"walk"}')

    assert auth.verify_signature(b'{"event":"walk"}', signature, timestamp)


def test_webhook_authenticator_rejects_old_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticator should reject requests outside the timestamp window."""
    auth = WebhookAuthenticator(secret="test-secret", max_timestamp_diff=5.0)
    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time",
        lambda: 100.0,
    )

    signature, _ = auth.generate_signature(b"{}", 90.0)

    with pytest.raises(AuthenticationError, match="Timestamp difference too large"):
        auth.verify_signature(b"{}", signature, 90.0)


def test_webhook_rate_limiter_bans_sources_after_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate limiter should ban and then report blocked sources."""
    now = [1000.0]
    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time",
        lambda: now[0],
    )
    limiter = WebhookRateLimiter(
        RateLimitConfig(
            requests_per_minute=1, requests_per_hour=10, ban_duration_seconds=30
        ),
    )

    limiter.check_limit("1.2.3.4")
    with pytest.raises(RateLimitError, match="requests/minute"):
        limiter.check_limit("1.2.3.4")

    with pytest.raises(RateLimitError, match="Source banned"):
        limiter.check_limit("1.2.3.4")

    stats = limiter.get_stats()
    assert stats["banned_sources"] == 1

    now[0] = 1100.0
    limiter.check_limit("1.2.3.4")
    limiter.reset_source("1.2.3.4")
    assert limiter.get_stats()["total_sources"] == 0


def test_webhook_validator_rejects_bad_payload_shapes() -> None:
    """Validator should reject malformed payloads."""
    validator = WebhookValidator(required_fields=["event"], max_payload_size=10)

    with pytest.raises(ValidationError, match="payload_size"):
        validator.validate_payload(b"01234567890")

    with pytest.raises(ValidationError, match="payload_json"):
        validator.validate_payload(b"{bad-json")

    with pytest.raises(ValidationError, match="payload_type"):
        validator.validate_payload(["not", "a", "dict"])  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="payload_fields"):
        validator.validate_payload({"other": "value"})


def test_webhook_validator_sanitizes_nested_strings() -> None:
    """Validator should trim keys/values and strip control characters."""
    validator = WebhookValidator(required_fields=["event"])

    payload = {
        "event": "  walk\x00\x01\t",
        "nested": {" key ": "\n hello\x02"},
        "items": [{" value ": " keep\x03 "}],
    }

    sanitized = validator.validate_payload(payload)

    assert sanitized["event"] == "walk"
    assert sanitized["nested"]["key"] == "hello"
    assert sanitized["items"][0]["value"] == "keep"


async def test_webhook_security_manager_processes_valid_request() -> None:
    """Security manager should authenticate and validate incoming payloads."""
    manager = WebhookSecurityManager(
        hass=object(),
        secret="test-secret",
        required_fields=["event"],
    )
    signature, timestamp = manager._authenticator.generate_signature(
        b'{"event":"feed"}',
    )
    request = WebhookRequest(
        payload=b'{"event":"feed"}',
        signature=signature,
        timestamp=timestamp,
        source_ip="127.0.0.1",
    )

    validated = await manager.async_process_webhook(request)

    assert validated == {"event": "feed"}
    assert "rate_limiter" in manager.get_security_stats()


def test_webhook_authenticator_missing_signature_is_rejected() -> None:
    """Missing signatures should fail request verification."""
    auth = WebhookAuthenticator(secret="test-secret")
    request = WebhookRequest(payload=b"{}", signature=None, timestamp=100.0)

    with pytest.raises(AuthenticationError, match="Missing signature"):
        auth.verify_request(request)
