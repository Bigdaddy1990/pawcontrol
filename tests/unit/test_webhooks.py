"""Unit tests for webhook endpoint helpers."""

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
