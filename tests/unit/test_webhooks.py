"""Unit tests for webhook endpoint helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol import webhooks
from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_GPS_SOURCE,
    CONF_WEBHOOK_ENABLED,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_REQUIRE_SIGNATURE,
    CONF_WEBHOOK_SECRET,
)
from custom_components.pawcontrol.exceptions import AuthenticationError


class _Request:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def read(self) -> bytes:
        return self._body


def _make_entry(
    *, data: dict[str, Any] | None = None, options: dict[str, Any] | None = None
) -> Any:
    return SimpleNamespace(entry_id="entry-1", data=data or {}, options=options or {})


def _make_hass(entries: list[Any] | None = None) -> Any:
    class _Entries:
        def __init__(self) -> None:
            self.updated_options: dict[str, Any] | None = None

        def async_entries(self, _domain: str) -> list[Any]:
            return entries or []

        def async_update_entry(self, _entry: Any, *, options: dict[str, Any]) -> None:
            self.updated_options = options

    return SimpleNamespace(config_entries=_Entries())


def test_any_dog_expects_webhook_handles_shapes() -> None:
    entry = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]}
    )
    assert webhooks._any_dog_expects_webhook(entry) is True

    non_matching = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "manual"}}]}
    )
    assert webhooks._any_dog_expects_webhook(non_matching) is False

    malformed = _make_entry(data={CONF_DOGS: "not-a-list"})
    assert webhooks._any_dog_expects_webhook(malformed) is False

    mixed = _make_entry(data={CONF_DOGS: ["dog", {"gps_config": {}}]})
    assert webhooks._any_dog_expects_webhook(mixed) is False


def test_new_webhook_credentials_use_token_urlsafe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential generators should delegate to secrets.token_urlsafe."""
    monkeypatch.setattr("secrets.token_urlsafe", lambda length: f"token-{length}")

    assert webhooks._new_webhook_id() == "token-24"
    assert webhooks._new_webhook_secret() == "token-32"


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_creates_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = _make_hass()
    entry = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={CONF_WEBHOOK_ENABLED: True},
    )

    monkeypatch.setattr(webhooks, "_new_webhook_id", lambda: "generated-id")
    monkeypatch.setattr(webhooks, "_new_webhook_secret", lambda: "generated-secret")

    await webhooks.async_ensure_webhook_config(hass, entry)

    updated = hass.config_entries.updated_options
    assert updated is not None
    assert updated[CONF_WEBHOOK_ID] == "generated-id"
    assert updated[CONF_WEBHOOK_SECRET] == "generated-secret"
    assert updated[CONF_WEBHOOK_REQUIRE_SIGNATURE] is True


@pytest.mark.asyncio
async def test_async_ensure_webhook_config_skips_when_disabled_or_present() -> None:
    """No update should happen when webhooks are disabled or already configured."""
    disabled_hass = _make_hass()
    disabled_entry = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={CONF_WEBHOOK_ENABLED: False},
    )
    await webhooks.async_ensure_webhook_config(disabled_hass, disabled_entry)
    assert disabled_hass.config_entries.updated_options is None

    configured_hass = _make_hass()
    configured_entry = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: "existing-id",
            CONF_WEBHOOK_SECRET: "existing-secret",
        },
    )
    await webhooks.async_ensure_webhook_config(configured_hass, configured_entry)
    assert configured_hass.config_entries.updated_options is None


@pytest.mark.asyncio
async def test_register_and_unregister_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={
            CONF_WEBHOOK_ENABLED: True,
            CONF_WEBHOOK_ID: "abc",
            CONF_WEBHOOK_SECRET: "secret",
        },
    )
    hass = _make_hass([entry])
    calls: list[tuple[str, str]] = []

    async def _noop(*_args: Any) -> None:
        return None

    monkeypatch.setattr(webhooks, "async_ensure_webhook_config", _noop)
    monkeypatch.setattr(
        webhooks,
        "async_unregister",
        lambda _hass, webhook_id: calls.append(("unregister", webhook_id)),
    )
    monkeypatch.setattr(
        webhooks,
        "async_register",
        lambda _hass, _domain, _name, webhook_id, _handler: calls.append((
            "register",
            webhook_id,
        )),
    )
    monkeypatch.setattr(
        webhooks,
        "get_entry_webhook_url",
        lambda _hass, _entry: "https://example/webhook",
    )

    await webhooks.async_register_entry_webhook(hass, entry)
    await webhooks.async_unregister_entry_webhook(hass, entry)

    assert calls == [("unregister", "abc"), ("register", "abc"), ("unregister", "abc")]


@pytest.mark.asyncio
async def test_register_and_unregister_short_circuit_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Register/unregister should no-op when prerequisites are not met."""
    calls: list[str] = []

    async def _noop(*_args: Any) -> None:
        return None

    monkeypatch.setattr(webhooks, "async_ensure_webhook_config", _noop)
    monkeypatch.setattr(webhooks, "async_unregister", lambda *_args: calls.append("u"))
    monkeypatch.setattr(webhooks, "async_register", lambda *_args: calls.append("r"))

    disabled_entry = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={CONF_WEBHOOK_ENABLED: False, CONF_WEBHOOK_ID: "abc"},
    )
    await webhooks.async_register_entry_webhook(
        _make_hass([disabled_entry]),
        disabled_entry,
    )

    missing_id_entry = _make_entry(
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={CONF_WEBHOOK_ENABLED: True},
    )
    await webhooks.async_register_entry_webhook(
        _make_hass([missing_id_entry]), missing_id_entry
    )

    await webhooks.async_unregister_entry_webhook(
        _make_hass([missing_id_entry]), missing_id_entry
    )

    assert calls == []


def test_get_entry_webhook_url_handles_missing_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook URL helper should return None without IDs and use HA helper otherwise."""
    hass = _make_hass()
    missing = _make_entry(options={})
    assert webhooks.get_entry_webhook_url(hass, missing) is None

    entry = _make_entry(options={CONF_WEBHOOK_ID: "hook-id"})
    from homeassistant.components import webhook as webhook_component

    monkeypatch.setattr(
        webhook_component,
        "async_generate_url",
        lambda _hass, webhook_id: f"https://example/{webhook_id}",
        raising=False,
    )
    assert webhooks.get_entry_webhook_url(hass, entry) == "https://example/hook-id"


@pytest.mark.asyncio
async def test_handle_webhook_requires_signature_and_valid_json() -> None:
    entry = _make_entry(
        options={CONF_WEBHOOK_ID: "abc", CONF_WEBHOOK_REQUIRE_SIGNATURE: True}
    )
    hass = _make_hass([entry])

    missing = await webhooks._handle_webhook(hass, "abc", _Request(b"{}"))
    assert missing.status == 400

    unknown = await webhooks._handle_webhook(hass, "missing", _Request(b"{}"))
    assert unknown.status == 404


@pytest.mark.asyncio
async def test_handle_webhook_missing_signature_or_invalid_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject missing signatures plus invalid JSON and payload shapes."""
    secure_entry = _make_entry(
        options={
            CONF_WEBHOOK_ID: "abc",
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
            CONF_WEBHOOK_SECRET: "secret",
        }
    )
    hass = _make_hass([secure_entry])

    missing_sig = await webhooks._handle_webhook(hass, "abc", _Request(b"{}"))
    assert missing_sig.status == 401

    open_entry = _make_entry(
        options={CONF_WEBHOOK_ID: "open", CONF_WEBHOOK_REQUIRE_SIGNATURE: False}
    )
    open_hass = _make_hass([open_entry])
    monkeypatch.setattr(
        webhooks,
        "async_process_gps_push",
        lambda *_args, **_kwargs: pytest.fail("should not be called"),
    )

    invalid_json = await webhooks._handle_webhook(open_hass, "open", _Request(b"{"))
    assert invalid_json.status == 400

    invalid_payload = await webhooks._handle_webhook(
        open_hass,
        "open",
        _Request(b"[]"),
    )
    assert invalid_payload.status == 400


@pytest.mark.asyncio
async def test_handle_webhook_signature_failures_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _make_entry(
        options={
            CONF_WEBHOOK_ID: "abc",
            CONF_WEBHOOK_REQUIRE_SIGNATURE: True,
            CONF_WEBHOOK_SECRET: "secret",
        }
    )
    hass = _make_hass([entry])

    class _Auth:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def verify_signature(self, _raw: bytes, _sig: str, _ts: float) -> None:
            if _sig == "bad":
                raise AuthenticationError("bad")

    monkeypatch.setattr(webhooks, "WebhookAuthenticator", _Auth)

    async def _push_ok(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "dog_id": "dino"}

    monkeypatch.setattr(webhooks, "async_process_gps_push", _push_ok)

    invalid_ts = await webhooks._handle_webhook(
        hass,
        "abc",
        _Request(
            b"{}",
            {"X-PawControl-Signature": "ok", "X-PawControl-Timestamp": "not-a-number"},
        ),
    )
    assert invalid_ts.status == 401

    bad_sig = await webhooks._handle_webhook(
        hass,
        "abc",
        _Request(
            b"{}", {"X-PawControl-Signature": "bad", "X-PawControl-Timestamp": "1"}
        ),
    )
    assert bad_sig.status == 401

    ok = await webhooks._handle_webhook(
        hass,
        "abc",
        _Request(
            b'{"dog_id":"dino","latitude":1,"longitude":2}',
            {"X-PawControl-Signature": "ok", "X-PawControl-Timestamp": "1"},
        ),
    )
    assert ok.status == 200


@pytest.mark.asyncio
async def test_handle_webhook_forwards_non_ok_push_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _make_entry(
        options={CONF_WEBHOOK_ID: "abc", CONF_WEBHOOK_REQUIRE_SIGNATURE: False}
    )
    hass = _make_hass([entry])

    async def _push(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "status": 422, "error": "bad_payload", "dog_id": "dino"}

    monkeypatch.setattr(webhooks, "async_process_gps_push", _push)

    response = await webhooks._handle_webhook(
        hass,
        "abc",
        _Request(b'{"dog_id":"dino","latitude":1,"longitude":2,"nonce":"n"}'),
    )

    assert response.status == 422
    assert response.text
