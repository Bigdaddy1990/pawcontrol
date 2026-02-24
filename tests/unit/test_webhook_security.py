from __future__ import annotations

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


def test_webhook_authenticator_rejects_invalid_algorithm() -> None:
    auth = WebhookAuthenticator("secret", algorithm="sha999")

    with pytest.raises(ValueError, match="Unsupported HMAC algorithm"):
        auth.generate_signature(b"payload", 100.0)


def test_webhook_authenticator_verify_signature_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = WebhookAuthenticator("secret", max_timestamp_diff=10)

    signature, timestamp = auth.generate_signature(b"ok", 100.0)

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: 200.0
    )
    with pytest.raises(AuthenticationError, match="Timestamp difference too large"):
        auth.verify_signature(b"ok", signature, timestamp)

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: 100.0
    )
    with pytest.raises(AuthenticationError, match="Invalid signature"):
        auth.verify_signature(b"ok", "bad-signature", timestamp)

    assert auth.verify_signature(b"ok", signature, timestamp) is True


def test_rate_limit_state_counts_and_ban(monkeypatch: pytest.MonkeyPatch) -> None:
    state = RateLimitState(source="1.2.3.4")

    state.add_request(30.0)
    state.add_request(80.0)
    state.add_request(2000.0)

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: 90.0
    )
    assert state.get_minute_count() == 2
    assert state.get_hour_count() == 3

    state.banned_until = 100.0
    assert state.is_banned() is True

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: 101.0
    )
    assert state.is_banned() is False


def test_rate_limiter_limit_ban_stats_and_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RateLimitConfig(
        requests_per_minute=1, requests_per_hour=100, ban_duration_seconds=120.0
    )
    limiter = WebhookRateLimiter(config)

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: 10.0
    )
    limiter.check_limit("source")

    with pytest.raises(RateLimitError, match="requests/minute"):
        limiter.check_limit("source")

    with pytest.raises(RateLimitError, match="Source banned"):
        limiter.check_limit("source")

    stats = limiter.get_stats()
    assert stats["banned_sources"] == 1
    assert stats["total_sources"] == 1

    limiter.reset_source("source")
    assert limiter.get_stats()["total_sources"] == 0


def test_webhook_validator_rejects_invalid_payloads() -> None:
    validator = WebhookValidator(required_fields=["dog_id"])

    with pytest.raises(ValidationError, match="Maximum allowed size"):
        WebhookValidator(max_payload_size=2).validate_payload(b"abc")

    with pytest.raises(ValidationError, match="Payload must be valid JSON"):
        validator.validate_payload(b"not-json")

    with pytest.raises(ValidationError, match="Payload must be a JSON object"):
        validator.validate_payload(["not", "a", "dict"])  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="Required fields missing"):
        validator.validate_payload({"event": "walk"})


def test_webhook_validator_sanitizes_nested_payload() -> None:
    validator = WebhookValidator(required_fields=["dog_id"])

    payload = {
        "dog_id": "  abc\x00\n",
        "nested": {" note ": "\t hi \r"},
        "list": [{" key ": " value \x1f"}, 5],
    }

    assert validator.validate_payload(payload) == {
        "dog_id": "abc",
        "nested": {"note": "hi"},
        "list": [{"key": "value"}, 5],
    }


@pytest.mark.asyncio
async def test_webhook_security_manager_process_and_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "secret"
    manager = WebhookSecurityManager(
        hass=None,  # type: ignore[arg-type]
        secret=secret,
        rate_limit_config=RateLimitConfig(requests_per_minute=1, requests_per_hour=10),
        required_fields=["dog_id"],
    )
    auth = WebhookAuthenticator(secret)
    signature, ts = auth.generate_signature(b'{"dog_id":"a1"}', 123.0)

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhook_security.time.time", lambda: 123.0
    )

    request = WebhookRequest(
        payload=b'{"dog_id":"a1"}',
        signature=signature,
        timestamp=ts,
        source_ip="10.0.0.5",
    )
    assert await manager.async_process_webhook(request) == {"dog_id": "a1"}

    with pytest.raises(RateLimitError):
        await manager.async_process_webhook(request)

    stats = manager.get_security_stats()
    assert "rate_limiter" in stats
    assert "timestamp" in stats


@pytest.mark.asyncio
async def test_webhook_security_manager_missing_signature() -> None:
    manager = WebhookSecurityManager(hass=None, secret="secret")  # type: ignore[arg-type]

    with pytest.raises(AuthenticationError, match="Missing signature"):
        await manager.async_process_webhook(
            WebhookRequest(payload=b"{}", signature=None, timestamp=0)
        )
