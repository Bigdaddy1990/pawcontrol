"""Simulate resilience blueprint manual events via Home Assistant event bus."""

from __future__ import annotations

import pytest
from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.const import STATE_OFF
from homeassistant.core import Event, HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .blueprint_context import (
    RESILIENCE_BLUEPRINT_REGISTERED_SERVICES,
    ResilienceBlueprintContext,
    create_resilience_blueprint_context,
)
from .blueprint_helpers import BLUEPRINT_RELATIVE_PATH


@pytest.mark.asyncio
async def test_resilience_blueprint_manual_events_execute(hass: HomeAssistant) -> None:
    """Manual guard/breaker events should execute the blueprint automation."""

    context: ResilienceBlueprintContext = create_resilience_blueprint_context(
        hass, watch_automation_events=True
    )

    assert context.registered_services == RESILIENCE_BLUEPRINT_REGISTERED_SERVICES, (
        "Context factory should register the shared resilience services"
    )

    try:
        base_context = context.base_context

        script_calls = context.script_calls
        guard_calls = context.guard_calls
        breaker_calls = context.breaker_calls
        automation_events = context.automation_events

        hass.states.async_set(
            "sensor.pawcontrol_statistics",
            "ok",
            {
                "service_execution": {
                    "guard_metrics": {"skipped": 1, "executed": 2},
                    "rejection_metrics": {
                        "open_breaker_count": 0,
                        "half_open_breaker_count": 0,
                        "rejection_breaker_count": 0,
                    },
                }
            },
        )
        hass.states.async_set(
            "script.pawcontrol_test_resilience_escalation",
            STATE_OFF,
            {
                "fields": {
                    "skip_threshold": {"default": 3},
                    "breaker_threshold": {"default": 1},
                }
            },
        )

        hass.config.legacy_templates = False  # type: ignore[attr-defined]

        automation_entry = MockConfigEntry(
            domain=AUTOMATION_DOMAIN,
            data={
                "use_blueprint": {
                    "path": BLUEPRINT_RELATIVE_PATH,
                    "input": base_context,
                }
            },
            title="Resilience escalation follow-up",
            unique_id="automation-resilience-followup",
        )
        automation_entry.add_to_hass(hass)

        assert await async_setup_component(hass, AUTOMATION_DOMAIN, {})
        await hass.async_block_till_done()

        await hass.config_entries.async_setup(automation_entry.entry_id)
        await hass.async_block_till_done()

        guard_event = {"fired_by": "guard"}
        hass.bus.async_fire(base_context["manual_guard_event"], guard_event)
        await hass.async_block_till_done()

        assert len(script_calls) == 1
        assert (
            script_calls[0].data["statistics_entity_id"]
            == "sensor.pawcontrol_statistics"
        )
        assert script_calls[0].data["skip_threshold"] == 3
        assert script_calls[0].data["breaker_threshold"] == 1
        assert len(guard_calls) == 1
        assert guard_calls[0].data == {"reason": "guard"}
        assert not breaker_calls

        assert automation_events, "Automation should emit triggered events"
        guard_event_data = automation_events[-1].data
        assert guard_event_data.get("entity_id", "").startswith("automation.")
        assert guard_event_data.get("trigger") == "manual_guard_event"

        breaker_event = {"fired_by": "breaker"}
        hass.bus.async_fire(base_context["manual_breaker_event"], breaker_event)
        await hass.async_block_till_done()

        assert len(script_calls) == 2
        assert len(breaker_calls) == 1
        assert breaker_calls[0].data == {"reason": "breaker"}
        assert len(guard_calls) == 1

        assert len(automation_events) >= 2
        breaker_event_data = automation_events[-1].data
        assert breaker_event_data.get("entity_id", "").startswith("automation.")
        assert breaker_event_data.get("trigger") == "manual_breaker_event"
    finally:
        context.cleanup()
