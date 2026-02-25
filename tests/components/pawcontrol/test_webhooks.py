"""Tests for webhook registration and request handling."""

from __future__ import annotations

import json
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
        captured.update(
            {
                "hass": hass_arg,
                "entry": entry_arg,
                "payload": payload,
                "source": source,
                "raw_size": raw_size,
                "nonce": nonce,
            }
        )
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
