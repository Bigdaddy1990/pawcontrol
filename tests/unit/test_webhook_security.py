"""Unit tests for webhook security helpers."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import (
    AuthenticationError,
    RateLimitError,
    ValidationError,
)
from custom_components.pawcontrol.webhook_security import (
    RateLimitConfig,
    RateLimitState,
    WebhookAuthenticator,
    WebhookRateLimiter,
    WebhookRequest,
    WebhookSecurityManager,
    WebhookValidator,
)


def test_rate_limit_state_counts_and_ban_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RateLimitState should count in-window requests and ban status correctly."""
    state = RateLimitState(source="source-a")

    state.add_request(timestamp=50.0)
    state.add_request(timestamp=95.0)
    state.add_request(timestamp=98.0)

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: 100.0
    )

    assert state.get_minute_count() == 3
    assert state.get_hour_count() == 3

    state.banned_until = 120.0
    assert state.is_banned() is True

    state.banned_until = 100.0
    assert state.is_banned() is False


def test_webhook_authenticator_rejects_old_timestamp() -> None:
    """Authenticator should reject timestamps older than configured max diff."""
    authenticator = WebhookAuthenticator(secret="top-secret", max_timestamp_diff=0.01)
    signature, timestamp = authenticator.generate_signature(b'{"ok": true}')

    with pytest.raises(AuthenticationError, match="Timestamp difference too large"):
        authenticator.verify_signature(b'{"ok": true}', signature, timestamp - 10)


def test_webhook_authenticator_rejects_missing_signature() -> None:
    """Missing signatures should fail request verification."""
    authenticator = WebhookAuthenticator(secret="top-secret")
    request = WebhookRequest(payload=b"{}", signature=None, timestamp=1.0)

    with pytest.raises(AuthenticationError, match="Missing signature"):
        authenticator.verify_request(request)


def test_webhook_authenticator_rejects_unknown_algorithm() -> None:
    """Unsupported digest algorithms should raise a ValueError."""
    authenticator = WebhookAuthenticator(
        secret="top-secret", algorithm="does-not-exist"
    )

    with pytest.raises(ValueError, match="Unsupported HMAC algorithm"):
        authenticator.generate_signature(b"{}")


def test_rate_limiter_bans_and_resets_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rate limiter should ban abusive sources and allow reset."""
    now = 100.0
    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: now
    )
    limiter = WebhookRateLimiter(
        RateLimitConfig(
            requests_per_minute=1, requests_per_hour=10, ban_duration_seconds=30.0
        )
    )

    limiter.check_limit("1.2.3.4")

    with pytest.raises(RateLimitError, match="Rate limit exceeded"):
        limiter.check_limit("1.2.3.4")

    with pytest.raises(RateLimitError, match="Source banned"):
        limiter.check_limit("1.2.3.4")

    stats = limiter.get_stats()
    assert stats["banned_sources"] == 1
    assert stats["total_requests"] == 2

    limiter.reset_source("1.2.3.4")
    assert limiter.get_stats()["total_sources"] == 0


def test_validator_parses_bytes_and_sanitizes_nested_payload() -> None:
    """Validator should parse JSON bytes and sanitize strings recursively."""
    validator = WebhookValidator(required_fields=["dog_id", "event"])

    payload = json.dumps({
        "dog_id": "  buddy\x00 ",
        "event": " feed\n",
        " extra ": " value ",
        "meta": {" note ": "\x01ok\t "},
        "items": [{"label": "  one\x02"}, "two"],
    }).encode()

    validated = validator.validate_payload(payload)

    assert validated == {
        "dog_id": "buddy",
        "event": "feed",
        "extra": "value",
        "meta": {"note": "ok"},
        "items": [{"label": "one"}, "two"],
    }


def test_validator_rejects_invalid_json() -> None:
    """Validator should raise ValidationError for invalid JSON payload bytes."""
    validator = WebhookValidator()

    with pytest.raises(ValidationError, match="Payload must be valid JSON"):
        validator.validate_payload(b"not-json")


@pytest.mark.asyncio
async def test_security_manager_processes_valid_request() -> None:
    """Security manager should run rate limit, authentication, and validation."""
    manager = WebhookSecurityManager(
        SimpleNamespace(),
        secret="s3cr3t",
        rate_limit_config=RateLimitConfig(requests_per_minute=5),
        required_fields=["dog_id", "event"],
    )

    payload = b'{"dog_id": "buddy", "event": "walk"}'
    signature, timestamp = manager._authenticator.generate_signature(payload)
    request = WebhookRequest(
        payload=payload,
        signature=signature,
        timestamp=timestamp,
        source_ip="10.0.0.8",
    )

    result = await manager.async_process_webhook(request)

    assert result["dog_id"] == "buddy"
    assert manager.get_security_stats()["rate_limiter"]["total_requests"] == 1
