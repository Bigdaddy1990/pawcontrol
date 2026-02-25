"""Tests for webhook registration and request handling."""

from __future__ import annotations

import json
import logging
import sys
from types import SimpleNamespace
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_GPS_SOURCE,
    CONF_WEBHOOK_ENABLED,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_REQUIRE_SIGNATURE,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
)
from custom_components.pawcontrol.webhook_security import WebhookAuthenticator
from custom_components.pawcontrol.webhooks import (
    _any_dog_expects_webhook,
    _handle_webhook,
    async_ensure_webhook_config,
    async_register_entry_webhook,
    async_unregister_entry_webhook,
    get_entry_webhook_url,
)


class _RequestStub:
    """Minimal webhook request stub."""

    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}

    async def read(self) -> bytes:
        """Return payload once like aiohttp request bodies."""
        return self._payload


def _response_json(response: Any) -> dict[str, Any]:
    """Decode aiohttp json_response body."""
    return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_generates_missing_credentials(
    hass: HomeAssistant,
) -> None:
    """Webhook config should be generated only when webhook GPS is enabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={CONF_WEBHOOK_ENABLED: True},
    )
    entry.add_to_hass(hass)

    await async_ensure_webhook_config(hass, entry)
    await hass.async_block_till_done()

    assert isinstance(entry.options[CONF_WEBHOOK_ID], str)
    assert isinstance(entry.options[CONF_WEBHOOK_SECRET], str)
    assert entry.options[CONF_WEBHOOK_REQUIRE_SIGNATURE] is True


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_noop_when_webhook_not_needed(
    hass: HomeAssistant,
) -> None:
    """Webhook credentials should remain untouched when no dog expects webhook."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "manual"}}]},
        options={CONF_WEBHOOK_ENABLED: True},
    )
    entry.add_to_hass(hass)

    await async_ensure_webhook_config(hass, entry)

    assert CONF_WEBHOOK_ID not in entry.options
    assert CONF_WEBHOOK_SECRET not in entry.options


def test_any_dog_expects_webhook_handles_invalid_shapes() -> None:
    """Dog source detection should ignore malformed data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [None, {}, {"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
    )

    assert _any_dog_expects_webhook(entry) is True


def test_any_dog_expects_webhook_returns_false_when_dogs_not_list() -> None:
    """Dog source detection should reject non-list storage shapes."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DOGS: {"gps_config": {}}})

    assert _any_dog_expects_webhook(entry) is False


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_keeps_existing_credentials(
    hass: HomeAssistant,
) -> None:
    """Existing webhook credentials should not be regenerated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: "existing-id",
            CONF_WEBHOOK_SECRET: "existing-secret",
        },
    )
    entry.add_to_hass(hass)

    await async_ensure_webhook_config(hass, entry)

    assert entry.options[CONF_WEBHOOK_ID] == "existing-id"
    assert entry.options[CONF_WEBHOOK_SECRET] == "existing-secret"


@pytest.mark.asyncio
async def test_async_register_entry_webhook_registers_and_unregisters_existing(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook registration should unregister stale handlers before registering."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: "register-id",
            CONF_WEBHOOK_SECRET: "register-secret",
            CONF_WEBHOOK_REQUIRE_SIGNATURE: False,
        },
    )
    entry.add_to_hass(hass)

    calls: dict[str, Any] = {}

    def _fake_unregister(_hass: HomeAssistant, webhook_id: str) -> None:
        calls["unregister"] = webhook_id

    def _fake_register(
        _hass: HomeAssistant,
        domain: str,
        name: str,
        webhook_id: str,
        handler: Any,
    ) -> None:
        calls.update({
            "domain": domain,
            "name": name,
            "register": webhook_id,
            "handler": handler,
        })

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_unregister", _fake_unregister
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_register", _fake_register
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.get_entry_webhook_url",
        lambda _hass, _entry: None,
    )

    await async_register_entry_webhook(hass, entry)

    assert calls["unregister"] == "register-id"
    assert calls["register"] == "register-id"
    assert calls["domain"] == DOMAIN
    assert calls["name"]
    assert calls["handler"] is _handle_webhook


@pytest.mark.asyncio
async def test_async_register_entry_webhook_skips_when_not_enabled(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook registration should stop early when webhook mode is disabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ENABLED: False,
            CONF_WEBHOOK_ID: "disabled-id",
        },
    )
    entry.add_to_hass(hass)

    called = False

    def _fake_register(*_: Any, **__: Any) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_register", _fake_register
    )

    async def _noop_ensure(*_: Any) -> None:
        return None

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_ensure_webhook_config",
        _noop_ensure,
    )

    await async_register_entry_webhook(hass, entry)

    assert called is False


@pytest.mark.asyncio
async def test_async_register_entry_webhook_skips_when_id_missing(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook registration should stop early when webhook id is invalid."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: 1,
            CONF_WEBHOOK_SECRET: "a-secret",
        },
    )
    entry.add_to_hass(hass)

    called = False

    def _fake_register(*_: Any, **__: Any) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_register", _fake_register
    )

    async def _noop_ensure(*_: Any) -> None:
        return None

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_ensure_webhook_config",
        _noop_ensure,
    )

    await async_register_entry_webhook(hass, entry)

    assert called is False


@pytest.mark.asyncio
async def test_async_register_entry_webhook_logs_url_when_available(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Webhook registration should log the generated URL when present."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: "with-url",
            CONF_WEBHOOK_SECRET: "a-secret",
            CONF_WEBHOOK_REQUIRE_SIGNATURE: False,
        },
    )
    entry.add_to_hass(hass)

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_unregister",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_register",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.get_entry_webhook_url",
        lambda *_: "https://example.test/api/webhook/with-url",
    )

    caplog.set_level(logging.INFO, logger="custom_components.pawcontrol.webhooks")

    await async_register_entry_webhook(hass, entry)

    assert "PawControl webhook URL for entry" in caplog.text


@pytest.mark.asyncio
async def test_async_unregister_entry_webhook_skips_invalid_ids(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook unregistration should ignore empty webhook ids."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={CONF_WEBHOOK_ID: ""})
    entry.add_to_hass(hass)

    called = False

    def _fake_unregister(_hass: HomeAssistant, webhook_id: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_unregister", _fake_unregister
    )

    await async_unregister_entry_webhook(hass, entry)

    assert called is False


@pytest.mark.asyncio
async def test_async_unregister_entry_webhook_unregisters_valid_id(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook unregistration should call Home Assistant for valid ids."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={CONF_WEBHOOK_ID: "remove-me"},
    )
    entry.add_to_hass(hass)

    seen_id: str | None = None

    def _fake_unregister(_hass: HomeAssistant, webhook_id: str) -> None:
        nonlocal seen_id
        seen_id = webhook_id

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_unregister", _fake_unregister
    )

    await async_unregister_entry_webhook(hass, entry)

    assert seen_id == "remove-me"


def test_get_entry_webhook_url_returns_none_without_id(hass: HomeAssistant) -> None:
    """Webhook URL generation should return None when id is missing."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})

    assert get_entry_webhook_url(hass, entry) is None


def test_get_entry_webhook_url_returns_generated_url(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook URL helper should delegate to Home Assistant generator."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={CONF_WEBHOOK_ID: "abc123"})

    monkeypatch.setitem(
        sys.modules,
        "homeassistant.components.webhook",
        SimpleNamespace(
            async_generate_url=(
                lambda _hass, webhook_id: f"https://example.test/api/webhook/{webhook_id}"
            )
        ),
    )

    assert (
        get_entry_webhook_url(hass, entry)
        == "https://example.test/api/webhook/abc123"
    )


@pytest.mark.asyncio
async def test_handle_webhook_rejects_unknown_webhook_id(hass: HomeAssistant) -> None:
    """Unknown webhook ids should return not found."""
    response = await _handle_webhook(hass, "missing", _RequestStub(b"{}"))

    assert response.status == 404
    assert _response_json(response)["error"] == "unknown_webhook"


@pytest.mark.asyncio
async def test_handle_webhook_requires_signature_headers(hass: HomeAssistant) -> None:
    """Signature-enabled entries should reject missing signature headers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-1",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
            CONF_WEBHOOK_SECRET: "top-secret",
        },
    )
    entry.add_to_hass(hass)

    response = await _handle_webhook(
        hass,
        "webhook-1",
        _RequestStub(b'{"dog_id":"dino"}'),
    )

    assert response.status == 401
    assert _response_json(response)["error"] == "missing_signature"


@pytest.mark.asyncio
async def test_handle_webhook_rejects_missing_secret_when_signature_required(
    hass: HomeAssistant,
) -> None:
    """Signature mode should fail fast when secrets are not configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-no-secret",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
        },
    )
    entry.add_to_hass(hass)

    response = await _handle_webhook(
        hass,
        "webhook-no-secret",
        _RequestStub(b'{"dog_id":"dino"}'),
    )

    assert response.status == 400
    assert _response_json(response)["error"] == "webhook_not_configured"


@pytest.mark.asyncio
async def test_handle_webhook_rejects_invalid_signature_timestamp(
    hass: HomeAssistant,
) -> None:
    """Signature mode should reject non-numeric timestamps."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-bad-ts",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
            CONF_WEBHOOK_SECRET: "my-secret",
        },
    )
    entry.add_to_hass(hass)

    response = await _handle_webhook(
        hass,
        "webhook-bad-ts",
        _RequestStub(
            b'{"dog_id":"dino"}',
            headers={
                "X-PawControl-Signature": "sig",
                "X-PawControl-Timestamp": "not-a-number",
            },
        ),
    )

    assert response.status == 401
    assert _response_json(response)["error"] == "invalid_signature"


@pytest.mark.asyncio
async def test_handle_webhook_rejects_invalid_signature_value(
    hass: HomeAssistant,
) -> None:
    """Signature mode should reject bad signatures."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-bad-sig",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
            CONF_WEBHOOK_SECRET: "my-secret",
        },
    )
    entry.add_to_hass(hass)

    response = await _handle_webhook(
        hass,
        "webhook-bad-sig",
        _RequestStub(
            b'{"dog_id":"dino"}',
            headers={
                "X-PawControl-Signature": "bad-signature",
                "X-PawControl-Timestamp": "1700000000",
            },
        ),
    )

    assert response.status == 401
    assert _response_json(response)["error"] == "invalid_signature"


@pytest.mark.asyncio
async def test_handle_webhook_rejects_invalid_json(hass: HomeAssistant) -> None:
    """Malformed JSON should fail with a bad request response."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-2",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: False,
        },
    )
    entry.add_to_hass(hass)

    response = await _handle_webhook(hass, "webhook-2", _RequestStub(b"{invalid"))

    assert response.status == 400
    assert _response_json(response)["error"] == "invalid_json"


@pytest.mark.asyncio
async def test_handle_webhook_rejects_non_object_payload(
    hass: HomeAssistant,
) -> None:
    """JSON payloads must be object mappings for push processing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-list",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: False,
        },
    )
    entry.add_to_hass(hass)

    response = await _handle_webhook(hass, "webhook-list", _RequestStub(b"[1,2,3]"))

    assert response.status == 400
    assert _response_json(response)["error"] == "invalid_payload"


@pytest.mark.asyncio
async def test_handle_webhook_success_forwards_nonce(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid payloads should be forwarded to the push router with nonce."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-3",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: False,
        },
    )
    entry.add_to_hass(hass)

    captured: dict[str, Any] = {}

    async def _fake_process(
        hass_arg: HomeAssistant,
        entry_arg: MockConfigEntry,
        payload: dict[str, Any],
        *,
        source: str,
        raw_size: int,
        nonce: str | None,
    ) -> dict[str, Any]:
        captured.update({
            "hass": hass_arg,
            "entry": entry_arg,
            "payload": payload,
            "source": source,
            "raw_size": raw_size,
            "nonce": nonce,
        })
        return {"ok": True, "dog_id": "dino"}

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_process_gps_push",
        _fake_process,
    )

    raw_payload = b'{"dog_id":"dino","nonce":"abc-123"}'
    response = await _handle_webhook(hass, "webhook-3", _RequestStub(raw_payload))

    assert response.status == 200
    assert _response_json(response) == {"ok": True, "dog_id": "dino"}
    assert captured["source"] == "webhook"
    assert captured["raw_size"] == len(raw_payload)
    assert captured["nonce"] == "abc-123"


@pytest.mark.asyncio
async def test_handle_webhook_with_signature_and_rejection(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signed requests should return router rejection details unchanged."""
    secret = "signed-secret"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ID: "webhook-4",
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
            CONF_WEBHOOK_SECRET: secret,
        },
    )
    entry.add_to_hass(hass)

    async def _fake_process(*_: Any, **__: Any) -> dict[str, Any]:
        return {"ok": False, "status": 422, "error": "stale", "dog_id": "dino"}

    monkeypatch.setattr(
        "custom_components.pawcontrol.webhooks.async_process_gps_push",
        _fake_process,
    )

    raw_payload = b'{"dog_id":"dino"}'
    auth = WebhookAuthenticator(secret=secret)
    signature, timestamp = auth.generate_signature(raw_payload)
    response = await _handle_webhook(
        hass,
        "webhook-4",
        _RequestStub(
            raw_payload,
            headers={
                "X-PawControl-Signature": signature,
                "X-PawControl-Timestamp": str(timestamp),
            },
        ),
    )

    assert response.status == 422
    assert _response_json(response) == {"ok": False, "error": "stale", "dog_id": "dino"}
