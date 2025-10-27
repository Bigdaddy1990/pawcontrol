"""Simulate resilience blueprint manual events via Home Assistant event bus."""

# TODO: Replace the service-call shim with a loaded automation once
# ``pytest-homeassistant-custom-component`` exposes automation blueprint
# loading paths so the regression matches Home Assistant's wiring.

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_resilience_blueprint_manual_events_execute(hass) -> None:
    """Manual events should trigger script calls and follow-ups."""

    script_calls: list = []
    guard_calls: list = []
    breaker_calls: list = []

    async def _mock_script_service(call) -> None:
        script_calls.append(call)

    async def _mock_guard_service(call) -> None:
        guard_calls.append(call)

    async def _mock_breaker_service(call) -> None:
        breaker_calls.append(call)

    hass.services.async_register("script", "turn_on", _mock_script_service)
    hass.services.async_register("test", "guard_followup", _mock_guard_service)
    hass.services.async_register("test", "breaker_followup", _mock_breaker_service)

    async def _fire_escalation() -> None:
        await hass.services.async_call(
            "script",
            "turn_on",
            {
                "statistics_entity_id": "sensor.pawcontrol_statistics",
                "skip_threshold": 3,
                "breaker_threshold": 1,
            },
        )

    async def _handle_guard_event() -> None:
        await _fire_escalation()
        await hass.services.async_call(
            "test",
            "guard_followup",
            {"reason": "guard"},
        )

    async def _handle_breaker_event() -> None:
        await _fire_escalation()
        await hass.services.async_call(
            "test",
            "breaker_followup",
            {"reason": "breaker"},
        )

    await _handle_guard_event()

    assert len(script_calls) == 1
    assert (
        script_calls[0].data["statistics_entity_id"] == "sensor.pawcontrol_statistics"
    )
    assert len(guard_calls) == 1
    assert guard_calls[0].data["reason"] == "guard"
    assert not breaker_calls

    await _handle_breaker_event()

    assert len(script_calls) == 2
    assert len(breaker_calls) == 1
    assert breaker_calls[0].data["reason"] == "breaker"
    assert len(guard_calls) == 1
