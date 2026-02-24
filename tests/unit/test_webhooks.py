"""Unit tests for webhook endpoint helpers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_GPS_SOURCE,
    CONF_MODULES,
    CONF_WEBHOOK_ENABLED,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_REQUIRE_SIGNATURE,
    CONF_WEBHOOK_SECRET,
)
from custom_components.pawcontrol.exceptions import AuthenticationError
from custom_components.pawcontrol.webhooks import (
    _any_dog_expects_webhook,
    _handle_webhook,
    _new_webhook_id,
    _new_webhook_secret,
    _resolve_entry_for_webhook_id,
    async_ensure_webhook_config,
    async_register_entry_webhook,
    async_unregister_entry_webhook,
    get_entry_webhook_url,
)


class _DummyRequest:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def read(self) -> bytes:
        return self._body


@pytest.fixture
def config_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {
        CONF_DOGS: [
            {
                "dog_id": "buddy",
                "dog_name": "Buddy",
                "gps_config": {CONF_GPS_SOURCE: "webhook"},
                CONF_MODULES: {},
            }
        ]
    }
    entry.options = {CONF_WEBHOOK_ENABLED: True}
    return entry


@pytest.fixture
def hass(config_entry: MagicMock) -> MagicMock:
    hass_obj = MagicMock()
    hass_obj.config_entries = MagicMock()
    hass_obj.config_entries.async_entries.return_value = [config_entry]
    hass_obj.config_entries.async_update_entry = MagicMock()
    return hass_obj


def test_any_dog_expects_webhook_variants(config_entry: MagicMock) -> None:
    assert _any_dog_expects_webhook(config_entry)

    config_entry.data = {
        CONF_DOGS: ["invalid", {"gps_config": {CONF_GPS_SOURCE: "api"}}]
    }
    assert _any_dog_expects_webhook(config_entry) is False

    config_entry.data = {CONF_DOGS: "invalid"}
    assert _any_dog_expects_webhook(config_entry) is False

    config_entry.data = {CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "api"}}]}
    assert _any_dog_expects_webhook(config_entry) is False


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_generates_credentials(
    hass: MagicMock, config_entry: MagicMock
) -> None:
    with (
        patch(
            "custom_components.pawcontrol.webhooks._new_webhook_id", return_value="id-1"
        ),
        patch(
            "custom_components.pawcontrol.webhooks._new_webhook_secret",
            return_value="secret-1",
        ),
    ):
        await async_ensure_webhook_config(hass, config_entry)

    hass.config_entries.async_update_entry.assert_called_once()
    options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert options[CONF_WEBHOOK_ID] == "id-1"
    assert options[CONF_WEBHOOK_SECRET] == "secret-1"
    assert CONF_WEBHOOK_REQUIRE_SIGNATURE in options


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_keeps_existing_credentials(
    hass: MagicMock, config_entry: MagicMock
) -> None:
    config_entry.options = {
        CONF_WEBHOOK_ENABLED: True,
        CONF_WEBHOOK_ID: "already-present",
        CONF_WEBHOOK_SECRET: "secret-present",
    }

    await async_ensure_webhook_config(hass, config_entry)

    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_register_unregister_webhook(
    hass: MagicMock, config_entry: MagicMock
) -> None:
    config_entry.options.update({
        CONF_WEBHOOK_ID: "webhook-1",
        CONF_WEBHOOK_SECRET: "secret-1",
        CONF_WEBHOOK_ENABLED: True,
    })

    with (
        patch(
            "custom_components.pawcontrol.webhooks.async_ensure_webhook_config",
            new=AsyncMock(),
        ),
        patch("custom_components.pawcontrol.webhooks.async_unregister") as unregister,
        patch("custom_components.pawcontrol.webhooks.async_register") as register,
        patch(
            "custom_components.pawcontrol.webhooks.get_entry_webhook_url",
            return_value="https://example.test/webhook",
        ),
    ):
        await async_register_entry_webhook(hass, config_entry)
        await async_unregister_entry_webhook(hass, config_entry)

    unregister.assert_called_with(hass, "webhook-1")
    assert register.call_count == 1


def test_get_entry_webhook_url(hass: MagicMock, config_entry: MagicMock) -> None:
    config_entry.options = {CONF_WEBHOOK_ID: "webhook-1"}

    with patch(
        "homeassistant.components.webhook.async_generate_url",
        return_value="https://local/webhook-1",
        create=True,
    ):
        assert get_entry_webhook_url(hass, config_entry) == "https://local/webhook-1"

    config_entry.options = {}
    assert get_entry_webhook_url(hass, config_entry) is None


def test_resolve_entry_for_webhook_id(hass: MagicMock, config_entry: MagicMock) -> None:
    config_entry.options = {CONF_WEBHOOK_ID: "id-1"}

    assert _resolve_entry_for_webhook_id(hass, "id-1") is config_entry
    assert _resolve_entry_for_webhook_id(hass, "id-2") is None


def test_new_webhook_secrets_are_non_empty() -> None:
    assert isinstance(_new_webhook_id(), str)
    assert _new_webhook_id()
    assert isinstance(_new_webhook_secret(), str)
    assert _new_webhook_secret()


@pytest.mark.asyncio
async def test_webhook_registration_early_returns(
    hass: MagicMock, config_entry: MagicMock
) -> None:
    config_entry.options = {CONF_WEBHOOK_ENABLED: False}
    await async_ensure_webhook_config(hass, config_entry)
    hass.config_entries.async_update_entry.assert_not_called()

    config_entry.options = {CONF_WEBHOOK_ENABLED: True}
    config_entry.data = {CONF_DOGS: [{"dog_id": "buddy", "dog_name": "Buddy"}]}
    with (
        patch(
            "custom_components.pawcontrol.webhooks.async_ensure_webhook_config",
            new=AsyncMock(),
        ),
        patch("custom_components.pawcontrol.webhooks.async_register") as register,
    ):
        await async_register_entry_webhook(hass, config_entry)
    register.assert_not_called()

    config_entry.data = {
        CONF_DOGS: [
            {
                "dog_id": "buddy",
                "dog_name": "Buddy",
                "gps_config": {CONF_GPS_SOURCE: "webhook"},
            }
        ]
    }
    config_entry.options = {CONF_WEBHOOK_ENABLED: True}
    with (
        patch(
            "custom_components.pawcontrol.webhooks.async_ensure_webhook_config",
            new=AsyncMock(),
        ),
        patch("custom_components.pawcontrol.webhooks.async_register") as register_no_id,
    ):
        await async_register_entry_webhook(hass, config_entry)
    register_no_id.assert_not_called()

    config_entry.options = {}
    with patch("custom_components.pawcontrol.webhooks.async_unregister") as unregister:
        await async_unregister_entry_webhook(hass, config_entry)
    unregister.assert_not_called()


@pytest.mark.asyncio
async def test_handle_webhook_error_paths(
    hass: MagicMock, config_entry: MagicMock
) -> None:
    config_entry.options = {
        CONF_WEBHOOK_ID: "id-1",
        CONF_WEBHOOK_ENABLED: True,
        CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
    }

    unknown = await _handle_webhook(hass, "missing", _DummyRequest(b"{}"))
    assert unknown.status == 404

    missing_secret = await _handle_webhook(hass, "id-1", _DummyRequest(b"{}"))
    assert missing_secret.status == 400

    config_entry.options[CONF_WEBHOOK_SECRET] = "secret-1"
    missing_signature = await _handle_webhook(hass, "id-1", _DummyRequest(b"{}"))
    assert missing_signature.status == 401

    bad_ts = await _handle_webhook(
        hass,
        "id-1",
        _DummyRequest(
            b"{}",
            {
                "X-PawControl-Signature": "sig",
                "X-PawControl-Timestamp": "nan-ts",
            },
        ),
    )
    assert bad_ts.status == 401

    with patch(
        "custom_components.pawcontrol.webhooks.WebhookAuthenticator.verify_signature",
        side_effect=AuthenticationError("invalid"),
    ):
        invalid_sig = await _handle_webhook(
            hass,
            "id-1",
            _DummyRequest(
                b"{}",
                {
                    "X-PawControl-Signature": "sig",
                    "X-PawControl-Timestamp": "123.0",
                },
            ),
        )
    assert invalid_sig.status == 401

    config_entry.options[CONF_WEBHOOK_REQUIRE_SIGNATURE] = False
    invalid_json = await _handle_webhook(hass, "id-1", _DummyRequest(b"{bad"))
    assert invalid_json.status == 400

    invalid_payload = await _handle_webhook(hass, "id-1", _DummyRequest(b"[1, 2, 3]"))
    assert invalid_payload.status == 400


@pytest.mark.asyncio
async def test_handle_webhook_success_and_rejection(
    hass: MagicMock, config_entry: MagicMock
) -> None:
    config_entry.options = {
        CONF_WEBHOOK_ID: "id-1",
        CONF_WEBHOOK_REQUIRE_SIGNATURE: False,
    }

    payload = {
        "dog_id": "buddy",
        "latitude": 1.2,
        "longitude": 3.4,
        "nonce": "nonce-1",
    }

    with patch(
        "custom_components.pawcontrol.webhooks.async_process_gps_push",
        new=AsyncMock(return_value={"ok": True, "dog_id": "buddy"}),
    ) as process_push:
        ok = await _handle_webhook(
            hass,
            "id-1",
            _DummyRequest(json.dumps(payload).encode("utf-8")),
        )

    assert ok.status == 200
    process_push.assert_awaited_once()
    assert process_push.await_args.kwargs["nonce"] == "nonce-1"

    with patch(
        "custom_components.pawcontrol.webhooks.async_process_gps_push",
        new=AsyncMock(
            return_value={
                "ok": False,
                "error": "denied",
                "status": 409,
                "dog_id": "buddy",
            }
        ),
    ):
        rejected = await _handle_webhook(
            hass,
            "id-1",
            _DummyRequest(json.dumps(payload).encode("utf-8")),
        )

    assert rejected.status == 409
    assert json.loads(rejected.text)["dog_id"] == "buddy"
