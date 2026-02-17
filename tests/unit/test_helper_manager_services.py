"""Regression tests for helper service payload construction."""

from types import SimpleNamespace
from typing import Any, NotRequired, TypedDict, cast

import pytest
from tests.helpers.payloads import typed_deepcopy

from custom_components.pawcontrol.helper_manager import PawControlHelperManager
from custom_components.pawcontrol.service_guard import ServiceGuardResult
from custom_components.pawcontrol.types import ServiceData


class ServiceCallTargetPayload(TypedDict, total=False):
    """Subset of Home Assistant service target structure used in tests."""  # noqa: E111

    entity_id: NotRequired[str | list[str]]  # noqa: E111
    device_id: NotRequired[str | list[str]]  # noqa: E111
    area_id: NotRequired[str | list[str]]  # noqa: E111


class CapturedServiceCall(TypedDict):
    """Captured service invocation emitted by the helper manager."""  # noqa: E111

    domain: str  # noqa: E111
    service: str  # noqa: E111
    service_data: ServiceData  # noqa: E111
    target: ServiceCallTargetPayload  # noqa: E111
    blocking: bool  # noqa: E111
    description: str | None  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_helper_manager_creates_typed_helper_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Helper creation should emit strictly typed service payloads."""  # noqa: E111

    hass = SimpleNamespace()  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    manager = PawControlHelperManager(hass, entry)  # noqa: E111

    class _DummyRegistry:  # noqa: E111
        def async_get(self, entity_id: str) -> None:
            return None  # noqa: E111

    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.helper_manager.er.async_get",
        lambda hass_instance: _DummyRegistry(),
    )

    captured: list[CapturedServiceCall] = []  # noqa: E111

    async def _capture_service_call(  # noqa: E111
        hass_instance: Any,
        domain: str,
        service: str,
        service_data: ServiceData,
        *,
        target: ServiceCallTargetPayload | None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        target_payload = cast(ServiceCallTargetPayload, dict(target or {}))
        captured.append({
            "domain": domain,
            "service": service,
            "service_data": typed_deepcopy(service_data),
            "target": target_payload,
            "blocking": blocking,
            "description": description,
        })
        return ServiceGuardResult(
            domain=domain,
            service=service,
            executed=True,
            description=description,
        )

    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.helper_manager.async_call_hass_service_if_available",
        _capture_service_call,
    )

    entity_sequence = [  # noqa: E111
        "input_boolean.pawcontrol_demo_flag",
        "input_datetime.pawcontrol_demo_time",
        "input_number.pawcontrol_demo_weight",
        "input_select.pawcontrol_demo_status",
    ]

    await manager._async_create_input_boolean(  # noqa: E111
        entity_sequence[0],
        "Demo Flag",
        icon="mdi:check",
        initial=True,
    )
    await manager._async_create_input_datetime(  # noqa: E111
        entity_sequence[1],
        "Demo Time",
        has_date=False,
        has_time=True,
        initial=None,
    )
    await manager._async_create_input_number(  # noqa: E111
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
    await manager._async_create_input_select(  # noqa: E111
        entity_sequence[3],
        "Demo Status",
        options=["good", "ok"],
        initial="good",
        icon="mdi:list-status",
    )

    assert [call["domain"] for call in captured] == [  # noqa: E111
        "input_boolean",
        "input_datetime",
        "input_number",
        "input_select",
    ]
    assert all(call["service"] == "create" for call in captured)  # noqa: E111
    assert all(call["blocking"] is True for call in captured)  # noqa: E111

    boolean_payload = captured[0]["service_data"]  # noqa: E111
    assert boolean_payload == {  # noqa: E111
        "name": "Demo Flag",
        "initial": True,
        "icon": "mdi:check",
    }

    datetime_payload = captured[1]["service_data"]  # noqa: E111
    assert datetime_payload == {  # noqa: E111
        "name": "Demo Time",
        "has_date": False,
        "has_time": True,
    }

    number_payload = captured[2]["service_data"]  # noqa: E111
    assert number_payload == {  # noqa: E111
        "name": "Demo Weight",
        "min": 0.5,
        "max": 80.0,
        "step": 0.5,
        "mode": "box",
        "unit_of_measurement": "kg",
        "icon": "mdi:weight",
        "initial": 10.0,
    }

    select_payload = captured[3]["service_data"]  # noqa: E111
    assert select_payload == {  # noqa: E111
        "name": "Demo Status",
        "options": ["good", "ok"],
        "initial": "good",
        "icon": "mdi:list-status",
    }

    for expected_entity, call in zip(entity_sequence, captured, strict=True):  # noqa: E111
        assert call["target"] == {"entity_id": expected_entity}
        assert call["description"] == f"creating helper {expected_entity}"

    metrics = manager.guard_metrics  # noqa: E111
    assert metrics["executed"] == 4  # noqa: E111
    assert metrics["skipped"] == 0  # noqa: E111
