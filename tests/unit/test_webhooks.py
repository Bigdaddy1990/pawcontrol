"""Unit tests for webhook endpoint helpers."""

from __future__ import annotations

from collections.abc import Mapping
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_GPS_SOURCE,
    CONF_MODULES,
    CONF_WEBHOOK_ENABLED,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_REQUIRE_SIGNATURE,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
)
import custom_components.pawcontrol.webhooks as webhooks


class _DummyRequest:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def read(self) -> bytes:
        return self._body


class _ConfigEntries:
    def __init__(self, entries: list[MagicMock] | None = None) -> None:
        self._entries = entries or []
        self.updated_options: Mapping[str, object] | None = None

    def async_entries(self, domain: str) -> list[MagicMock]:
        assert domain == DOMAIN
        return self._entries

    def async_update_entry(
        self,
        entry: MagicMock,
        *,
        options: Mapping[str, object],
    ) -> None:
        self.updated_options = options
        entry.options = dict(options)


def _make_entry(
    *,
    data: dict[str, object] | None = None,
    options: dict[str, object] | None = None,
) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = (
        data
        if data is not None
        else {
            CONF_DOGS: [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    "gps_config": {CONF_GPS_SOURCE: "webhook"},
                    CONF_MODULES: {},
                }
            ]
        }
    )
    entry.options = options if options is not None else {CONF_WEBHOOK_ENABLED: True}
    return entry


def _make_hass(entries: list[MagicMock] | None = None) -> SimpleNamespace:
    return SimpleNamespace(config_entries=_ConfigEntries(entries))


def test_any_dog_expects_webhook_variants() -> None:
    assert webhooks._any_dog_expects_webhook(_make_entry()) is True
    assert (
        webhooks._any_dog_expects_webhook(
            _make_entry(data={CONF_DOGS: ["invalid", {"gps_config": {}}]})
        )
        is False
    )
    assert (
        webhooks._any_dog_expects_webhook(_make_entry(data={CONF_DOGS: "oops"}))
        is False
    )


def test_new_webhook_credentials_use_token_urlsafe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("secrets.token_urlsafe", lambda length: f"token-{length}")
    assert webhooks._new_webhook_id() == "token-24"
    assert webhooks._new_webhook_secret() == "token-32"


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_generated_and_skipped_paths() -> None:
    hass = _make_hass()
    entry = _make_entry()

    with (
        pytest.MonkeyPatch.context() as mp,
    ):
        mp.setattr(webhooks, "_new_webhook_id", lambda: "id-1")
        mp.setattr(webhooks, "_new_webhook_secret", lambda: "secret-1")
        await webhooks.async_ensure_webhook_config(hass, entry)

    assert hass.config_entries.updated_options is not None
    assert entry.options[CONF_WEBHOOK_ID] == "id-1"
    assert entry.options[CONF_WEBHOOK_SECRET] == "secret-1"
    assert entry.options[CONF_WEBHOOK_REQUIRE_SIGNATURE] is True

    # Disabled webhook => no update
    disabled = _make_entry(options={CONF_WEBHOOK_ENABLED: False})
    disabled_hass = _make_hass()
    await webhooks.async_ensure_webhook_config(disabled_hass, disabled)
    assert disabled_hass.config_entries.updated_options is None

    # Existing credentials => no update
    configured = _make_entry(
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: "existing",
            CONF_WEBHOOK_SECRET: "existing-secret",
        }
    )
    configured_hass = _make_hass()
    await webhooks.async_ensure_webhook_config(configured_hass, configured)
    assert configured_hass.config_entries.updated_options is None


@pytest.mark.asyncio
async def test_register_and_unregister_webhook_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _make_entry(
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: "abc",
            CONF_WEBHOOK_SECRET: "secret",
        }
    )
    hass = _make_hass([entry])

    register_calls: list[str] = []
    unregister_calls: list[str] = []

    monkeypatch.setattr(webhooks, "async_ensure_webhook_config", AsyncMock())
    monkeypatch.setattr(
        webhooks,
        "async_register",
        lambda *_args: register_calls.append("register"),
    )
    monkeypatch.setattr(
        webhooks,
        "async_unregister",
        lambda _hass, webhook_id: unregister_calls.append(webhook_id),
    )
    monkeypatch.setattr(
        webhooks, "get_entry_webhook_url", lambda *_args: "https://example/h"
    )

    await webhooks.async_register_entry_webhook(hass, entry)
    await webhooks.async_unregister_entry_webhook(hass, entry)

    assert register_calls == ["register"]
    assert unregister_calls == ["abc", "abc"]

    # No-op paths
    disabled_entry = _make_entry(
        options={CONF_WEBHOOK_ENABLED: False, CONF_WEBHOOK_ID: "id"}
    )
    await webhooks.async_register_entry_webhook(
        _make_hass([disabled_entry]), disabled_entry
    )

    missing_id_entry = _make_entry(options={CONF_WEBHOOK_ENABLED: True})
    await webhooks.async_register_entry_webhook(
        _make_hass([missing_id_entry]), missing_id_entry
    )
    await webhooks.async_unregister_entry_webhook(
        _make_hass([missing_id_entry]), missing_id_entry
    )


@pytest.mark.asyncio
async def test_register_handles_unregister_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _make_entry(options={CONF_WEBHOOK_ENABLED: True, CONF_WEBHOOK_ID: "abc"})
    hass = _make_hass([entry])
    monkeypatch.setattr(webhooks, "async_ensure_webhook_config", AsyncMock())

    def _raise(*_args: object) -> None:
        raise RuntimeError("boom")

    register = MagicMock()
    monkeypatch.setattr(webhooks, "async_unregister", _raise)
    monkeypatch.setattr(webhooks, "async_register", register)
    monkeypatch.setattr(webhooks, "get_entry_webhook_url", lambda *_args: None)

    await webhooks.async_register_entry_webhook(hass, entry)
    register.assert_called_once()


def test_get_entry_webhook_url_handles_missing_id() -> None:
    hass = _make_hass()
    assert webhooks.get_entry_webhook_url(hass, _make_entry(options={})) is None

    from unittest.mock import patch

    with patch(
        "homeassistant.components.webhook.async_generate_url",
        lambda _hass, webhook_id: f"https://example/{webhook_id}",
        create=True,
    ):
        assert (
            webhooks.get_entry_webhook_url(
                hass,
                _make_entry(options={CONF_WEBHOOK_ID: "hook-id"}),
            )
            == "https://example/hook-id"
        )


def test_resolve_entry_for_webhook_id() -> None:
    entry = _make_entry(options={CONF_WEBHOOK_ID: "id-1"})
    hass = _make_hass([entry])
    assert webhooks._resolve_entry_for_webhook_id(hass, "id-1") is entry
    assert webhooks._resolve_entry_for_webhook_id(hass, "missing") is None


@pytest.mark.asyncio
async def test_handle_webhook_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = _make_entry(
        options={
            CONF_WEBHOOK_ID: "id-1",
            CONF_WEBHOOK_SECRET: "secret-1",
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
        }
    )
    hass = _make_hass([entry])

    unknown = await webhooks._handle_webhook(hass, "missing", _DummyRequest(b"{}"))
    assert unknown.status == 404

    missing_sig = await webhooks._handle_webhook(hass, "id-1", _DummyRequest(b"{}"))
    assert missing_sig.status == 401

    bad_ts = await webhooks._handle_webhook(
        hass,
        "id-1",
        _DummyRequest(
            b"{}",
            headers={
                "X-PawControl-Signature": "sig",
                "X-PawControl-Timestamp": "bad",
            },
        ),
    )
    assert bad_ts.status == 401

    class _FailingAuthenticator:
        def __init__(self, secret: str) -> None:
            self.secret = secret

        def verify_signature(self, _raw: bytes, _sig: str, _ts: float) -> None:
            raise webhooks.AuthenticationError("bad")

    monkeypatch.setattr(webhooks, "WebhookAuthenticator", _FailingAuthenticator)
    invalid_sig = await webhooks._handle_webhook(
        hass,
        "id-1",
        _DummyRequest(
            b"{}",
            headers={
                "X-PawControl-Signature": "sig",
                "X-PawControl-Timestamp": "1",
            },
        ),
    )
    assert invalid_sig.status == 401

    # Signature disabled and payload validation paths.
    entry.options = {CONF_WEBHOOK_ID: "id-1", CONF_WEBHOOK_REQUIRE_SIGNATURE: False}

    invalid_json = await webhooks._handle_webhook(hass, "id-1", _DummyRequest(b"{"))
    assert invalid_json.status == 400

    invalid_payload = await webhooks._handle_webhook(
        hass,
        "id-1",
        _DummyRequest(json.dumps(["not-object"]).encode()),
    )
    assert invalid_payload.status == 400

    process = AsyncMock(return_value={"ok": True, "dog_id": "buddy"})
    monkeypatch.setattr(webhooks, "async_process_gps_push", process)
    ok_response = await webhooks._handle_webhook(
        hass,
        "id-1",
        _DummyRequest(json.dumps({"nonce": "n-1"}).encode()),
    )
    assert ok_response.status == 200
    assert process.await_args.kwargs["nonce"] == "n-1"

    process_fail = AsyncMock(
        return_value={"ok": False, "status": 409, "error": "dup", "dog_id": "buddy"}
    )
    monkeypatch.setattr(webhooks, "async_process_gps_push", process_fail)
    failed = await webhooks._handle_webhook(
        hass,
        "id-1",
        _DummyRequest(json.dumps({}).encode()),
    )
    assert failed.status == 409


@pytest.mark.asyncio
async def test_handle_webhook_requires_secret_when_signatures_enabled() -> None:
    entry = _make_entry(
        options={CONF_WEBHOOK_ID: "id-1", CONF_WEBHOOK_REQUIRE_SIGNATURE: True}
    )
    hass = _make_hass([entry])
    response = await webhooks._handle_webhook(hass, "id-1", _DummyRequest(b"{}"))
    assert response.status == 400
