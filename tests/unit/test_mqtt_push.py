"""Unit tests for MQTT push transport helpers."""

from collections.abc import Awaitable, Callable
import sys
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.pawcontrol import mqtt_push
from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_GPS_SOURCE,
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC,
    DEFAULT_MQTT_TOPIC,
    DOMAIN,
)


class _AwaitableUnsub:
    """Minimal awaitable wrapper used by unsubscribe tests."""

    def __init__(self) -> None:
        self.awaited = False

    def __await__(self):  # type: ignore[override]
        async def _runner() -> None:
            self.awaited = True

        return _runner().__await__()


@pytest.mark.parametrize(
    ("entry_data", "expected"),
    [
        ({CONF_DOGS: []}, False),
        ({CONF_DOGS: "bad"}, False),
        ({CONF_DOGS: ["bad", {"gps_config": {CONF_GPS_SOURCE: "webhook"}}]}, False),
        ({CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]}, True),
    ],
)
def test_any_dog_expects_mqtt(entry_data: dict[str, object], expected: bool) -> None:
    """Dog source inspection should only accept mqtt-configured dict entries."""
    entry = SimpleNamespace(data=entry_data)

    assert mqtt_push._any_dog_expects_mqtt(entry) is expected


def test_domain_store_resets_non_mapping_domain_store() -> None:
    """Domain store helper should recover from non-dict hass.data values."""
    hass = SimpleNamespace(data={DOMAIN: []})

    store = mqtt_push._domain_store(hass)

    assert store == {}
    assert isinstance(hass.data[DOMAIN], dict)


@pytest.mark.asyncio
async def test_register_entry_mqtt_returns_early_when_disabled_or_not_needed() -> None:
    """Disabled MQTT or absent mqtt dogs should skip subscription entirely."""
    hass = SimpleNamespace(data={})
    entry_disabled = SimpleNamespace(
        entry_id="entry-disabled",
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={CONF_MQTT_ENABLED: False},
    )
    entry_not_needed = SimpleNamespace(
        entry_id="entry-not-needed",
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "webhook"}}]},
        options={CONF_MQTT_ENABLED: True},
    )

    await mqtt_push.async_register_entry_mqtt(hass, entry_disabled)
    await mqtt_push.async_register_entry_mqtt(hass, entry_not_needed)

    assert hass.data == {}


@pytest.mark.asyncio
async def test_register_entry_mqtt_handles_missing_mqtt_module() -> None:
    """Import errors from Home Assistant MQTT integration should be tolerated."""
    hass = SimpleNamespace(data={})
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={CONF_MQTT_ENABLED: True},
    )

    components_module = ModuleType("homeassistant.components")

    def _missing_mqtt(_: object) -> object:
        raise RuntimeError("mqtt unavailable")

    components_module.__getattr__ = _missing_mqtt  # type: ignore[assignment]

    previous_components = sys.modules.get("homeassistant.components")
    sys.modules["homeassistant.components"] = components_module
    try:
        await mqtt_push.async_register_entry_mqtt(hass, entry)
    finally:
        if previous_components is None:
            sys.modules.pop("homeassistant.components", None)
        else:
            sys.modules["homeassistant.components"] = previous_components

    assert hass.data == {}


@pytest.mark.asyncio
async def test_register_entry_mqtt_subscribes_and_processes_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful subscribe path should store unsubscribe and process valid payloads."""
    hass = SimpleNamespace(data={DOMAIN: {mqtt_push._MQTT_STORE_KEY: "broken"}})
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={
            CONF_MQTT_ENABLED: True,
            CONF_MQTT_TOPIC: "  paws/topic  ",
        },
    )

    observed: list[tuple[dict[str, object], str | None, int]] = []

    async def _process(
        _: object,
        __: object,
        payload: dict[str, object],
        *,
        source: str,
        raw_size: int,
        nonce: str | None,
    ) -> None:
        assert source == "mqtt"
        observed.append((payload, nonce, raw_size))

    monkeypatch.setattr(mqtt_push, "async_process_gps_push", _process)

    callback_holder: dict[str, Callable[[object], Awaitable[None]]] = {}

    async def _async_subscribe(
        _hass: object,
        topic: str,
        callback: Callable[[object], Awaitable[None]],
        qos: int,
    ) -> Callable[[], None]:
        assert topic == "paws/topic"
        assert qos == 0
        callback_holder["callback"] = callback

        def _unsub() -> None:
            return None

        return _unsub

    mqtt_module = ModuleType("homeassistant.components.mqtt")
    mqtt_module.async_subscribe = _async_subscribe  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant.components.mqtt", mqtt_module)

    await mqtt_push.async_register_entry_mqtt(hass, entry)

    store = hass.data[DOMAIN][mqtt_push._MQTT_STORE_KEY]
    assert isinstance(store, dict)
    assert callable(store[entry.entry_id])

    callback = callback_holder["callback"]
    await callback(SimpleNamespace(payload=b'{"dog_id":"d1","nonce":"n1"}'))
    await callback(SimpleNamespace(payload='{"dog_id":"d2"}'))
    await callback(SimpleNamespace(payload=b"not-json"))
    await callback(SimpleNamespace(payload=b"[]"))
    await callback(SimpleNamespace(payload=123))
    await callback(object())

    assert observed[0][0] == {"dog_id": "d1", "nonce": "n1"}
    assert observed[0][1] == "n1"
    assert observed[0][2] == len(b'{"dog_id":"d1","nonce":"n1"}')
    assert observed[1][0] == {"dog_id": "d2"}
    assert observed[1][1] is None


@pytest.mark.asyncio
async def test_register_entry_mqtt_uses_default_topic_and_handles_subscribe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty topic text should fall back to defaults and tolerate subscribe errors."""
    hass = SimpleNamespace(data={})
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={
            CONF_MQTT_ENABLED: True,
            CONF_MQTT_TOPIC: "   ",
        },
    )

    async def _async_subscribe(
        _hass: object,
        topic: str,
        callback: Callable[[object], Awaitable[None]],
        qos: int,
    ) -> Callable[[], None]:
        del callback
        assert topic == DEFAULT_MQTT_TOPIC
        assert qos == 0
        raise RuntimeError("cannot subscribe")

    mqtt_module = ModuleType("homeassistant.components.mqtt")
    mqtt_module.async_subscribe = _async_subscribe  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant.components.mqtt", mqtt_module)

    await mqtt_push.async_register_entry_mqtt(hass, entry)

    assert hass.data[DOMAIN][mqtt_push._MQTT_STORE_KEY] == {}


@pytest.mark.asyncio
async def test_register_entry_mqtt_replaces_existing_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-registering should unsubscribe stale callbacks before storing the new one."""
    old_unsub_called = False

    async def _old_unsub() -> None:
        nonlocal old_unsub_called
        old_unsub_called = True

    hass = SimpleNamespace(
        data={DOMAIN: {mqtt_push._MQTT_STORE_KEY: {"entry-id": _old_unsub}}}
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={CONF_DOGS: [{"gps_config": {CONF_GPS_SOURCE: "mqtt"}}]},
        options={CONF_MQTT_ENABLED: True},
    )

    def _new_unsub() -> None:
        return None

    async def _async_subscribe(
        _hass: object,
        topic: str,
        callback: Callable[[object], Awaitable[None]],
        qos: int,
    ) -> Callable[[], None]:
        del callback
        assert topic == DEFAULT_MQTT_TOPIC
        assert qos == 0
        return _new_unsub

    mqtt_module = ModuleType("homeassistant.components.mqtt")
    mqtt_module.async_subscribe = _async_subscribe  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant.components.mqtt", mqtt_module)

    await mqtt_push.async_register_entry_mqtt(hass, entry)

    assert old_unsub_called is True
    assert hass.data[DOMAIN][mqtt_push._MQTT_STORE_KEY]["entry-id"] is _new_unsub


@pytest.mark.asyncio
async def test_unregister_entry_mqtt_supports_async_unsubscribe() -> None:
    """Unregister should await async unsubscribe callbacks and remove entries."""
    awaitable_unsub = _AwaitableUnsub()

    def _unsub() -> _AwaitableUnsub:
        return awaitable_unsub

    hass = SimpleNamespace(
        data={DOMAIN: {mqtt_push._MQTT_STORE_KEY: {"entry-id": _unsub}}}
    )
    entry = SimpleNamespace(entry_id="entry-id")

    await mqtt_push.async_unregister_entry_mqtt(hass, entry)

    assert awaitable_unsub.awaited is True
    assert hass.data[DOMAIN][mqtt_push._MQTT_STORE_KEY] == {}


@pytest.mark.asyncio
async def test_unregister_entry_mqtt_ignores_invalid_store_and_unsub_errors() -> None:
    """Unregister should be resilient to malformed storage and callback failures."""
    hass = SimpleNamespace(data={DOMAIN: {mqtt_push._MQTT_STORE_KEY: []}})
    entry = SimpleNamespace(entry_id="entry-id")

    await mqtt_push.async_unregister_entry_mqtt(hass, entry)

    assert hass.data[DOMAIN][mqtt_push._MQTT_STORE_KEY] == []

    def _boom() -> None:
        raise RuntimeError("unsubscribe failed")

    hass.data[DOMAIN][mqtt_push._MQTT_STORE_KEY] = {"entry-id": _boom}
    await mqtt_push.async_unregister_entry_mqtt(hass, entry)

    assert hass.data[DOMAIN][mqtt_push._MQTT_STORE_KEY] == {}
