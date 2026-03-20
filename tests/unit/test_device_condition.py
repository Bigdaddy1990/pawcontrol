"""Unit tests for PawControl device conditions."""

from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.const import (
    CONF_CONDITION,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_TYPE,
    STATE_OFF,
    STATE_ON,
)
import pytest

from custom_components.pawcontrol import device_condition
from custom_components.pawcontrol.const import DOMAIN

CONF_STATUS = "status"


class _FakeStates:
    """Minimal Home Assistant state registry stub."""

    def __init__(self, states: dict[str, str] | None = None) -> None:
        self._states = states or {}

    def get(self, entity_id: str | None) -> SimpleNamespace | None:
        if entity_id is None:
            return None
        state = self._states.get(entity_id)
        if state is None:
            return None
        return SimpleNamespace(state=state)


@pytest.mark.asyncio
async def test_async_get_conditions_returns_empty_when_device_has_no_dog_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Devices without a PawControl dog mapping should expose no conditions."""
    hass = SimpleNamespace()
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id=None),
    )

    conditions = await device_condition.async_get_conditions(hass, "device-1")

    assert conditions == []


@pytest.mark.asyncio
async def test_async_get_conditions_builds_entries_for_available_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Condition discovery should emit one payload per resolvable entity."""
    hass = SimpleNamespace()
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id="buddy"),
    )
    monkeypatch.setattr(
        device_condition,
        "build_device_automation_metadata",
        lambda: {"secondary": False, "generated": True},
    )
    monkeypatch.setattr(
        device_condition,
        "build_unique_id",
        lambda dog_id, suffix: f"{dog_id}:{suffix}",
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_entity_id",
        lambda _hass, _device_id, unique_id, _platform: (
            f"sensor.{unique_id.replace(':', '_')}"
            if unique_id.endswith(("is_hungry", "status"))
            else None
        ),
    )

    conditions = await device_condition.async_get_conditions(hass, "device-1")

    assert conditions == [
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            "metadata": {"secondary": False, "generated": True},
            CONF_TYPE: "is_hungry",
            CONF_ENTITY_ID: "sensor.buddy_is_hungry",
        },
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            "metadata": {"secondary": False, "generated": True},
            CONF_TYPE: "status_is",
            CONF_ENTITY_ID: "sensor.buddy_status",
        },
    ]


@pytest.mark.asyncio
async def test_async_get_condition_capabilities_only_adds_status_field() -> None:
    """Only the status condition should advertise extra schema fields."""
    hass = SimpleNamespace()

    capabilities = await device_condition.async_get_condition_capabilities(
        hass,
        {CONF_TYPE: "status_is"},
    )

    assert "extra_fields" in capabilities
    assert capabilities["extra_fields"]({CONF_STATUS: "sleeping"}) == {
        CONF_STATUS: "sleeping"
    }
    assert (
        await device_condition.async_get_condition_capabilities(
            hass,
            {CONF_TYPE: "is_hungry"},
        )
        == {}
    )


@pytest.mark.asyncio
async def test_async_condition_from_config_prefers_runtime_snapshot(
    monkeypatch,
) -> None:
    """Snapshot-backed conditions should use coordinator runtime data first."""
    hass = SimpleNamespace(
        states=_FakeStates({"binary_sensor.buddy_hunger": STATE_OFF})
    )
    runtime_data = object()
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=runtime_data,
        ),
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_status_snapshot",
        lambda seen_runtime_data, dog_id: (
            {"is_hungry": True, "in_safe_zone": False}
            if seen_runtime_data is runtime_data and dog_id == "buddy"
            else None
        ),
    )

    hungry_condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: "binary_sensor.buddy_hunger",
            CONF_TYPE: "is_hungry",
        },
    )
    safe_zone_condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: "binary_sensor.buddy_safe_zone",
            CONF_TYPE: "in_safe_zone",
        },
    )

    assert hungry_condition(hass, None) is True
    assert safe_zone_condition(hass, None) is False


@pytest.mark.asyncio
async def test_async_condition_from_config_falls_back_to_entity_state(
    monkeypatch,
) -> None:
    """Binary and status conditions should fall back to Home Assistant state."""
    hass = SimpleNamespace(
        states=_FakeStates({
            "binary_sensor.buddy_attention_needed": STATE_ON,
            "sensor.buddy_status": "sleeping",
        })
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=None,
        ),
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_status_snapshot",
        lambda _runtime_data, _dog_id: None,
    )

    attention_condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: "binary_sensor.buddy_attention_needed",
            CONF_TYPE: "attention_needed",
        },
    )
    status_condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: "sensor.buddy_status",
            CONF_STATUS: "sleeping",
            CONF_TYPE: "status_is",
        },
    )

    assert attention_condition(hass, None) is True
    assert status_condition(hass, None) is True


@pytest.mark.asyncio
async def test_async_condition_from_config_handles_missing_status_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The status condition should fail closed when no expected value is set."""
    hass = SimpleNamespace(states=_FakeStates())
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=None,
        ),
    )

    logger = Mock()
    monkeypatch.setattr(device_condition, "_LOGGER", logger)

    condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: "sensor.buddy_status",
            CONF_TYPE: "status_is",
        },
    )

    assert condition(hass, None) is False
    logger.debug.assert_called_once_with("Missing status value for status_is condition")


@pytest.mark.asyncio
async def test_async_condition_from_config_logs_unknown_condition_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected validated condition types should be rejected defensively."""
    hass = SimpleNamespace(states=_FakeStates())
    monkeypatch.setattr(
        device_condition,
        "CONDITION_SCHEMA",
        lambda config: {
            **config,
            CONF_DEVICE_ID: config[CONF_DEVICE_ID],
            CONF_TYPE: "unexpected",
        },
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=None,
        ),
    )

    logger = Mock()
    monkeypatch.setattr(device_condition, "_LOGGER", logger)

    condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "is_hungry",
        },
    )

    assert condition(hass, None) is False
    logger.debug.assert_called_once_with(
        "Unknown PawControl condition type: %s",
        "unexpected",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condition_type", "entity_id", "state_value", "expected"),
    [
        ("is_hungry", "binary_sensor.buddy_is_hungry", STATE_ON, True),
        ("needs_walk", "binary_sensor.buddy_needs_walk", STATE_ON, True),
        ("on_walk", "binary_sensor.buddy_on_walk", STATE_ON, True),
        ("in_safe_zone", "binary_sensor.buddy_safe_zone", STATE_OFF, False),
        ("attention_needed", "binary_sensor.buddy_missing", None, False),
    ],
)
async def test_async_condition_from_config_uses_state_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
    condition_type: str,
    entity_id: str,
    state_value: str | None,
    expected: bool,
) -> None:
    """State-backed conditions should evaluate against Home Assistant state."""
    hass = SimpleNamespace(
        states=_FakeStates({entity_id: state_value} if state_value is not None else {})
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=None,
        ),
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_status_snapshot",
        lambda _runtime_data, _dog_id: None,
    )

    condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: entity_id,
            CONF_TYPE: condition_type,
        },
    )

    assert condition(hass, None) is expected


@pytest.mark.asyncio
async def test_async_condition_from_config_status_uses_snapshot_before_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status conditions should prefer coordinator snapshots over entity state."""
    hass = SimpleNamespace(states=_FakeStates({"sensor.buddy_status": "resting"}))
    runtime_data = object()
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=runtime_data,
        ),
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_status_snapshot",
        lambda seen_runtime_data, dog_id: (
            {"state": "running"}
            if seen_runtime_data is runtime_data and dog_id == "buddy"
            else None
        ),
    )

    condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: "sensor.buddy_status",
            CONF_STATUS: "running",
            CONF_TYPE: "status_is",
        },
    )

    assert condition(hass, None) is True


@pytest.mark.asyncio
async def test_status_condition_returns_false_without_entity_or_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status conditions should fail closed when no snapshot or entity exists."""
    hass = SimpleNamespace(states=_FakeStates())
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=None,
        ),
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_status_snapshot",
        lambda _runtime_data, _dog_id: None,
    )

    condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: "sensor.buddy_status",
            CONF_STATUS: "running",
            CONF_TYPE: "status_is",
        },
    )

    assert condition(hass, None) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condition_type", "snapshot_key"),
    [("needs_walk", "needs_walk"), ("on_walk", "on_walk")],
)
async def test_async_condition_from_config_reads_snapshot_flags_for_walk_conditions(
    monkeypatch: pytest.MonkeyPatch,
    condition_type: str,
    snapshot_key: str,
) -> None:
    """Walk-related conditions should read their dedicated snapshot flags."""
    hass = SimpleNamespace(states=_FakeStates())
    runtime_data = object()
    monkeypatch.setattr(
        device_condition,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=runtime_data,
        ),
    )
    monkeypatch.setattr(
        device_condition,
        "resolve_status_snapshot",
        lambda seen_runtime_data, dog_id: (
            {snapshot_key: True}
            if seen_runtime_data is runtime_data and dog_id == "buddy"
            else None
        ),
    )

    condition = await device_condition.async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: "device-1",
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: f"binary_sensor.buddy_{condition_type}",
            CONF_TYPE: condition_type,
        },
    )

    assert condition(hass, None) is True
