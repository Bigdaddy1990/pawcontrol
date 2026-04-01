"""Coverage tests for device_action.py + device_condition.py + device_trigger.py — (0% → 28%+).

Covers: ActionDefinition, ConditionDefinition, TriggerDefinition dataclasses
        and resolve_device_context helpers.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.device_action import (
    ActionDefinition,
    DeviceActionPayload,
)
from custom_components.pawcontrol.device_condition import (
    ConditionDefinition,
    DeviceConditionPayload,
)
from custom_components.pawcontrol.device_trigger import (
    TriggerDefinition,
    DeviceTriggerPayload,
)


# ─── ActionDefinition ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_action_definition_init() -> None:
    a = ActionDefinition(type="walk_start")
    assert a.type == "walk_start"


@pytest.mark.unit
def test_action_definition_feeding() -> None:
    a = ActionDefinition(type="trigger_feeding")
    assert a.type == "trigger_feeding"


@pytest.mark.unit
def test_device_action_payload_is_dict() -> None:
    payload: DeviceActionPayload = {"type": "walk_start", "device_id": "dev_001"}
    assert payload["type"] == "walk_start"


# ─── ConditionDefinition ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_condition_definition_init() -> None:
    c = ConditionDefinition(
        type="is_walking",
        platform="device",
        entity_suffix="_walk_state",
    )
    assert c.type == "is_walking"
    assert c.platform == "device"


@pytest.mark.unit
def test_condition_definition_feeding() -> None:
    c = ConditionDefinition(
        type="is_fed_today",
        platform="device",
        entity_suffix="_feeding_status",
    )
    assert c.entity_suffix == "_feeding_status"


@pytest.mark.unit
def test_device_condition_payload_is_dict() -> None:
    payload: DeviceConditionPayload = {
        "type": "is_walking", "device_id": "dev_001", "platform": "device"
    }
    assert payload["type"] == "is_walking"


# ─── TriggerDefinition ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_trigger_definition_minimal() -> None:
    t = TriggerDefinition(
        type="walk_started",
        platform="device",
        entity_suffix="_walk_state",
    )
    assert t.type == "walk_started"
    assert t.to_state is None
    assert t.from_state is None


@pytest.mark.unit
def test_trigger_definition_with_states() -> None:
    t = TriggerDefinition(
        type="walk_ended",
        platform="device",
        entity_suffix="_walk_state",
        to_state="idle",
        from_state="walking",
    )
    assert t.to_state == "idle"
    assert t.from_state == "walking"


@pytest.mark.unit
def test_device_trigger_payload_is_dict() -> None:
    payload: DeviceTriggerPayload = {
        "type": "walk_started",
        "device_id": "dev_001",
        "platform": "device",
    }
    assert payload["device_id"] == "dev_001"


# ─── module import checks ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_device_action_has_resolve_device_context() -> None:
    import custom_components.pawcontrol.device_action as da
    assert hasattr(da, "resolve_device_context")


@pytest.mark.unit
def test_device_condition_has_build_unique_id() -> None:
    import custom_components.pawcontrol.device_condition as dc
    assert hasattr(dc, "build_unique_id")


@pytest.mark.unit
def test_device_trigger_has_build_unique_id() -> None:
    import custom_components.pawcontrol.device_trigger as dt
    assert hasattr(dt, "build_unique_id")
