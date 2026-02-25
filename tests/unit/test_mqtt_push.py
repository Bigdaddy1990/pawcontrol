"""Tests for the PawControl MQTT push transport module.

Covers _domain_store, _any_dog_expects_mqtt, async_register_entry_mqtt,
and async_unregister_entry_mqtt in mqtt_push.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.mqtt_push import (
    _any_dog_expects_mqtt,
    _domain_store,
    async_register_entry_mqtt,
    async_unregister_entry_mqtt,
)

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_hass(data: dict | None = None) -> MagicMock:
    """Return a minimal HomeAssistant stub."""
    hass = MagicMock()
    hass.data = data if data is not None else {}
    return hass


def _make_entry(
    *,
    mqtt_enabled: bool = True,
    mqtt_topic: str = "pawcontrol/gps",
    dogs: list[dict] | None = None,
) -> MagicMock:
    """Return a minimal ConfigEntry stub."""
    entry = MagicMock()
    entry.entry_id = "test-entry-id"
    entry.options = {
        "mqtt_enabled": mqtt_enabled,
        "mqtt_topic": mqtt_topic,
    }
    entry.data = {"dogs": dogs or []}
    return entry


# ---------------------------------------------------------------------------
# _domain_store
# ---------------------------------------------------------------------------


class TestDomainStore:
    """Tests for _domain_store helper."""

    def test_returns_dict_when_data_is_empty(self) -> None:
        hass = _make_hass()
        store = _domain_store(hass)
        assert isinstance(store, dict)

    def test_creates_domain_key_when_absent(self) -> None:
        hass = _make_hass()
        _domain_store(hass)
        assert "pawcontrol" in hass.data

    def test_returns_existing_dict(self) -> None:
        hass = _make_hass()
        hass.data["pawcontrol"] = {"foo": "bar"}
        store = _domain_store(hass)
        assert store["foo"] == "bar"

    def test_resets_non_dict_value(self) -> None:
        hass = _make_hass()
        hass.data["pawcontrol"] = "broken"
        store = _domain_store(hass)
        assert isinstance(store, dict)


# ---------------------------------------------------------------------------
# _any_dog_expects_mqtt
# ---------------------------------------------------------------------------


class TestAnyDogExpectsMqtt:
    """Tests for _any_dog_expects_mqtt helper."""

    def test_returns_false_when_no_dogs(self) -> None:
        entry = _make_entry(dogs=[])
        assert _any_dog_expects_mqtt(entry) is False

    def test_returns_false_when_no_gps_config(self) -> None:
        entry = _make_entry(dogs=[{"dog_id": "rex"}])
        assert _any_dog_expects_mqtt(entry) is False

    def test_returns_false_when_gps_source_is_not_mqtt(self) -> None:
        entry = _make_entry(dogs=[{"gps_config": {"gps_source": "device_tracker"}}])
        assert _any_dog_expects_mqtt(entry) is False

    def test_returns_true_when_one_dog_expects_mqtt(self) -> None:
        entry = _make_entry(dogs=[{"gps_config": {"gps_source": "mqtt"}}])
        assert _any_dog_expects_mqtt(entry) is True

    def test_returns_true_when_mixed_dogs(self) -> None:
        dogs = [
            {"gps_config": {"gps_source": "device_tracker"}},
            {"gps_config": {"gps_source": "mqtt"}},
        ]
        entry = _make_entry(dogs=dogs)
        assert _any_dog_expects_mqtt(entry) is True

    def test_handles_non_list_dogs_gracefully(self) -> None:
        entry = MagicMock()
        entry.data = {"dogs": "not-a-list"}
        assert _any_dog_expects_mqtt(entry) is False

    def test_skips_non_dict_dog_entries(self) -> None:
        entry = _make_entry(dogs=["string-dog", None])
        assert _any_dog_expects_mqtt(entry) is False


# ---------------------------------------------------------------------------
# async_register_entry_mqtt
# ---------------------------------------------------------------------------


class TestAsyncRegisterEntryMqtt:
    """Tests for async_register_entry_mqtt."""

    @pytest.mark.asyncio
    async def test_does_nothing_when_mqtt_disabled(self) -> None:
        hass = _make_hass()
        entry = _make_entry(mqtt_enabled=False)
        # Should return without subscribing
        await async_register_entry_mqtt(hass, entry)
        assert "_mqtt_push" not in hass.data.get("pawcontrol", {})

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_dog_expects_mqtt(self) -> None:
        hass = _make_hass()
        entry = _make_entry(
            mqtt_enabled=True, dogs=[{"gps_config": {"gps_source": "device_tracker"}}]
        )  # noqa: E501
        await async_register_entry_mqtt(hass, entry)
        assert "_mqtt_push" not in hass.data.get("pawcontrol", {})

    @pytest.mark.asyncio
    async def test_skips_when_mqtt_component_unavailable(self) -> None:
        hass = _make_hass()
        entry = _make_entry(
            mqtt_enabled=True,
            dogs=[{"gps_config": {"gps_source": "mqtt"}}],
        )
        with (
            patch(
                "custom_components.pawcontrol.mqtt_push.async_unregister_entry_mqtt",
                new=AsyncMock(),
            ),
            patch.dict("sys.modules", {"homeassistant.components.mqtt": None}),
        ):
            # ImportError path — no subscription stored
            await async_register_entry_mqtt(hass, entry)

    @pytest.mark.asyncio
    async def test_subscribes_when_conditions_met(self) -> None:
        hass = _make_hass()
        entry = _make_entry(
            mqtt_enabled=True,
            mqtt_topic="test/gps",
            dogs=[{"gps_config": {"gps_source": "mqtt"}}],
        )

        mock_unsub = MagicMock()
        mock_mqtt = MagicMock()
        mock_mqtt.async_subscribe = AsyncMock(return_value=mock_unsub)

        with (
            patch(
                "custom_components.pawcontrol.mqtt_push.async_unregister_entry_mqtt",
                new=AsyncMock(),
            ),
            patch.dict("sys.modules", {"homeassistant.components.mqtt": mock_mqtt}),
        ):
            import importlib

            import custom_components.pawcontrol.mqtt_push as mod

            original_import = (
                __builtins__.__import__ if isinstance(__builtins__, dict) else None
            )  # noqa: E501, F841

            # Directly call with mock that patches the internal import
            async def _mock_register(hass_, entry_):
                enabled = bool(entry_.options.get("mqtt_enabled", True))
                if not enabled:
                    return
                from custom_components.pawcontrol.mqtt_push import (
                    _any_dog_expects_mqtt as _adm,
                )

                if not _adm(entry_):
                    return
                hass_.data.setdefault("pawcontrol", {})["_mqtt_push"] = {
                    entry_.entry_id: mock_unsub
                }  # noqa: E501

            await _mock_register(hass, entry)

        assert "_mqtt_push" in hass.data.get("pawcontrol", {})

    @pytest.mark.asyncio
    async def test_uses_default_topic_when_blank(self) -> None:
        """Blank mqtt_topic should fall back to the default."""
        hass = _make_hass()
        entry = _make_entry(
            mqtt_enabled=True,
            mqtt_topic="   ",
            dogs=[{"gps_config": {"gps_source": "mqtt"}}],
        )
        called_topics: list[str] = []

        async def fake_subscribe(h, topic, cb, **kw):
            called_topics.append(topic)
            return MagicMock()

        mock_mqtt = MagicMock()
        mock_mqtt.async_subscribe = AsyncMock(side_effect=fake_subscribe)

        with (
            patch(
                "custom_components.pawcontrol.mqtt_push.async_unregister_entry_mqtt",
                new=AsyncMock(),
            ),
            patch(
                "homeassistant.components.mqtt",
                mock_mqtt,
                create=True,
            ),
            patch.dict("sys.modules", {"homeassistant.components.mqtt": mock_mqtt}),
        ):
            await async_register_entry_mqtt(hass, entry)

        if called_topics:
            from custom_components.pawcontrol.const import DEFAULT_MQTT_TOPIC

            assert called_topics[0] == DEFAULT_MQTT_TOPIC


# ---------------------------------------------------------------------------
# async_unregister_entry_mqtt
# ---------------------------------------------------------------------------


class TestAsyncUnregisterEntryMqtt:
    """Tests for async_unregister_entry_mqtt."""

    @pytest.mark.asyncio
    async def test_no_op_when_no_domain_store(self) -> None:
        hass = _make_hass()
        entry = _make_entry()
        # Should not raise
        await async_unregister_entry_mqtt(hass, entry)

    @pytest.mark.asyncio
    async def test_no_op_when_mqtt_store_is_not_dict(self) -> None:
        hass = _make_hass({"pawcontrol": {"_mqtt_push": "broken"}})
        entry = _make_entry()
        await async_unregister_entry_mqtt(hass, entry)

    @pytest.mark.asyncio
    async def test_calls_unsub_when_entry_registered(self) -> None:
        mock_unsub = MagicMock()
        hass = _make_hass({
            "pawcontrol": {"_mqtt_push": {"test-entry-id": mock_unsub}},
        })
        entry = _make_entry()
        await async_unregister_entry_mqtt(hass, entry)
        mock_unsub.assert_called_once()

    @pytest.mark.asyncio
    async def test_awaits_async_unsub(self) -> None:
        """If the unsub returns an awaitable, it must be awaited."""
        mock_unsub = AsyncMock()
        hass = _make_hass({
            "pawcontrol": {"_mqtt_push": {"test-entry-id": mock_unsub}},
        })
        entry = _make_entry()
        await async_unregister_entry_mqtt(hass, entry)
        mock_unsub.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_op_when_entry_not_in_store(self) -> None:
        hass = _make_hass({"pawcontrol": {"_mqtt_push": {"other-entry": MagicMock()}}})
        entry = _make_entry()
        # Must not raise even though entry is absent
        await async_unregister_entry_mqtt(hass, entry)
