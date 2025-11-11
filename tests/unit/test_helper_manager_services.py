"""Regression tests for helper service payload construction."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from custom_components.pawcontrol.helper_manager import PawControlHelperManager
from custom_components.pawcontrol.service_guard import ServiceGuardResult


@pytest.mark.unit
@pytest.mark.asyncio
async def test_helper_manager_creates_typed_helper_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Helper creation should emit strictly typed service payloads."""

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={})
    manager = PawControlHelperManager(hass, entry)

    class _DummyRegistry:
        def async_get(self, entity_id: str) -> None:
            return None

    monkeypatch.setattr(
        "custom_components.pawcontrol.helper_manager.er.async_get",
        lambda hass_instance: _DummyRegistry(),
    )

    captured: list[dict[str, Any]] = []

    async def _capture_service_call(
        hass_instance: Any,
        domain: str,
        service: str,
        service_data: dict[str, Any],
        *,
        target: dict[str, Any] | None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        captured.append(
            {
                "domain": domain,
                "service": service,
                "service_data": dict(service_data),
                "target": dict(target or {}),
                "blocking": blocking,
                "description": description,
            }
        )
        return ServiceGuardResult(
            domain=domain,
            service=service,
            executed=True,
            description=description,
        )

    monkeypatch.setattr(
        "custom_components.pawcontrol.helper_manager.async_call_hass_service_if_available",
        _capture_service_call,
    )

    entity_sequence = [
        "input_boolean.pawcontrol_demo_flag",
        "input_datetime.pawcontrol_demo_time",
        "input_number.pawcontrol_demo_weight",
        "input_select.pawcontrol_demo_status",
    ]

    await manager._async_create_input_boolean(
        entity_sequence[0],
        "Demo Flag",
        icon="mdi:check",
        initial=True,
    )
    await manager._async_create_input_datetime(
        entity_sequence[1],
        "Demo Time",
        has_date=False,
        has_time=True,
        initial=None,
    )
    await manager._async_create_input_number(
        entity_sequence[2],
        "Demo Weight",
        min=0.5,
        max=80.0,
        step=0.5,
        unit_of_measurement="kg",
        icon="mdi:weight",
        mode="box",
        initial=10.0,
    )
    await manager._async_create_input_select(
        entity_sequence[3],
        "Demo Status",
        options=["good", "ok"],
        initial="good",
        icon="mdi:list-status",
    )

    assert [call["domain"] for call in captured] == [
        "input_boolean",
        "input_datetime",
        "input_number",
        "input_select",
    ]
    assert all(call["service"] == "create" for call in captured)
    assert all(call["blocking"] is True for call in captured)

    boolean_payload = captured[0]["service_data"]
    assert boolean_payload == {
        "name": "Demo Flag",
        "initial": True,
        "icon": "mdi:check",
    }

    datetime_payload = captured[1]["service_data"]
    assert datetime_payload == {
        "name": "Demo Time",
        "has_date": False,
        "has_time": True,
    }

    number_payload = captured[2]["service_data"]
    assert number_payload == {
        "name": "Demo Weight",
        "min": 0.5,
        "max": 80.0,
        "step": 0.5,
        "mode": "box",
        "unit_of_measurement": "kg",
        "icon": "mdi:weight",
        "initial": 10.0,
    }

    select_payload = captured[3]["service_data"]
    assert select_payload == {
        "name": "Demo Status",
        "options": ["good", "ok"],
        "initial": "good",
        "icon": "mdi:list-status",
    }

    for expected_entity, call in zip(entity_sequence, captured, strict=True):
        assert call["target"] == {"entity_id": expected_entity}
        assert call["description"] == f"creating helper {expected_entity}"

    metrics = manager.guard_metrics
    assert metrics["executed"] == 4
    assert metrics["skipped"] == 0

