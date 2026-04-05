"""Tests for MQTT GPS push transport wiring."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
import sys

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_GPS_SOURCE,
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC,
    DEFAULT_MQTT_TOPIC,
    DOMAIN,
)
from custom_components.pawcontrol.mqtt_push import (
    _MQTT_STORE_KEY,
    _any_dog_expects_mqtt,
    _domain_store,
    async_register_entry_mqtt,
    async_unregister_entry_mqtt,
)


def test_domain_store_resets_invalid_domain_container(hass: Any) -> None:
    """Domain store helper should normalize hass.data[DOMAIN] to a dict."""
    hass.data[DOMAIN] = []

    store = _domain_store(hass)

    assert isinstance(store, dict)
    assert hass.data[DOMAIN] is store


def test_any_dog_expects_mqtt_handles_malformed_dogs() -> None:
    """Dog source detection should ignore malformed dog entries."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [None, {}, {"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
    )

    assert _any_dog_expects_mqtt(entry) is True


@pytest.mark.asyncio
async def test_async_register_entry_mqtt_skips_when_disabled(hass: Any) -> None:
    """Registration should no-op when MQTT mode is disabled in options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={CONF_MQTT_ENABLED: False},
    )

    await async_register_entry_mqtt(hass, entry)

    assert _MQTT_STORE_KEY not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_async_register_entry_mqtt_subscribes_and_routes_messages(
    hass: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registration should subscribe and callback should forward valid payloads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={CONF_MQTT_ENABLED: True, CONF_MQTT_TOPIC: "  paw/topic  "},
    )

    process_push = AsyncMock()
    monkeypatch.setattr("custom_components.pawcontrol.mqtt_push.async_process_gps_push", process_push)

    unsubscribe_called = False

    def _old_unsubscribe() -> None:
        nonlocal unsubscribe_called
        unsubscribe_called = True

    hass.data.setdefault(DOMAIN, {})[_MQTT_STORE_KEY] = {entry.entry_id: _old_unsubscribe}

    captured: dict[str, Any] = {}

    async def _fake_subscribe(
        _hass: Any,
        topic: str,
        callback: Any,
        qos: int,
    ) -> Any:
        captured.update({"topic": topic, "callback": callback, "qos": qos})

        def _unsubscribe() -> None:
            return None

        return _unsubscribe

    mqtt_module = ModuleType("homeassistant.components.mqtt")
    mqtt_module.async_subscribe = _fake_subscribe  # type: ignore[attr-defined]
    components_module = sys.modules.setdefault(
        "homeassistant.components",
        ModuleType("homeassistant.components"),
    )
    components_module.mqtt = mqtt_module  # type: ignore[attr-defined]
    sys.modules["homeassistant.components.mqtt"] = mqtt_module

    await async_register_entry_mqtt(hass, entry)

    assert unsubscribe_called is True
    assert captured["topic"] == "paw/topic"
    assert captured["qos"] == 0

    callback = captured["callback"]
    await callback(SimpleNamespace(payload=b'{"dog_id":"a","nonce":"n-1"}'))
    await callback(SimpleNamespace(payload='{"dog_id":"b"}'))
    await callback(SimpleNamespace(payload=b"not json"))
    await callback(SimpleNamespace(payload=b'["not-dict"]'))

    assert process_push.await_count == 2
    first_call = process_push.await_args_list[0]
    assert first_call.kwargs["source"] == "mqtt"
    assert first_call.kwargs["raw_size"] > 0
    assert first_call.kwargs["nonce"] == "n-1"
    second_call = process_push.await_args_list[1]
    assert second_call.kwargs["nonce"] is None


@pytest.mark.asyncio
async def test_async_register_entry_mqtt_handles_subscribe_error(
    hass: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Subscription failures should be swallowed and not store unsub handlers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={CONF_MQTT_ENABLED: True, CONF_MQTT_TOPIC: DEFAULT_MQTT_TOPIC},
    )

    async def _raise_subscribe(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom")

    mqtt_module = ModuleType("homeassistant.components.mqtt")
    mqtt_module.async_subscribe = _raise_subscribe  # type: ignore[attr-defined]
    components_module = sys.modules.setdefault(
        "homeassistant.components",
        ModuleType("homeassistant.components"),
    )
    components_module.mqtt = mqtt_module  # type: ignore[attr-defined]
    sys.modules["homeassistant.components.mqtt"] = mqtt_module

    await async_register_entry_mqtt(hass, entry)

    assert entry.entry_id not in hass.data.get(DOMAIN, {}).get(_MQTT_STORE_KEY, {})


@pytest.mark.asyncio
async def test_async_unregister_entry_mqtt_awaits_async_unsubscribe(hass: Any) -> None:
    """Unregister should await async unsubscribe callables when returned."""
    called = False

    async def _awaitable() -> None:
        nonlocal called
        called = True

    def _unsubscribe() -> Any:
        return _awaitable()

    entry = MockConfigEntry(domain=DOMAIN)
    hass.data.setdefault(DOMAIN, {})[_MQTT_STORE_KEY] = {entry.entry_id: _unsubscribe}

    await async_unregister_entry_mqtt(hass, entry)

    assert called is True
    assert entry.entry_id not in hass.data[DOMAIN][_MQTT_STORE_KEY]
