"""Simulate resilience blueprint manual events via Home Assistant event bus."""

from __future__ import annotations

import pytest
from homeassistant.components.automation import (
    DOMAIN as AUTOMATION_DOMAIN,
)
from homeassistant.components.automation import (
    EVENT_AUTOMATION_TRIGGERED,
)
from homeassistant.const import STATE_OFF
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .blueprint_context import (
    RESILIENCE_BLUEPRINT_REGISTERED_SERVICES,
    ResilienceBlueprintHarness,
    create_resilience_blueprint_context,
)
from .blueprint_helpers import BLUEPRINT_RELATIVE_PATH, ResilienceBlueprintContext


@pytest.mark.asyncio
async def test_resilience_blueprint_manual_events_execute(hass: HomeAssistant) -> None:
    """Manual guard/breaker events should execute the blueprint automation."""

    context = create_resilience_blueprint_context(hass, watch_automation_events=True)

    assert context.registered_services == (RESILIENCE_BLUEPRINT_REGISTERED_SERVICES), (
        "Context factory should register the shared resilience services"
    )

    try:
        base_context: ResilienceBlueprintContext = context.build_context()

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

        automation_store = hass.data["homeassistant.components.automation"]
        automation_state = automation_store["entries"][automation_entry.entry_id]
        assert automation_state["entity_id"].startswith("automation.")
        assert (
            automation_state["event_map"][base_context["manual_guard_event"]]
            == "manual_guard_event"
        )
        assert automation_state["blueprint_path"].endswith(BLUEPRINT_RELATIVE_PATH)

        skip_threshold_template = Template(
            "{{ state_attr('script.pawcontrol_test_resilience_escalation', 'fields')[\n"
            "  'skip_threshold']['default'] }}",
            hass,
        )
        assert int(skip_threshold_template.render()) == 3

        guard_event = {"fired_by": "guard"}
        await hass.bus.async_fire(base_context["manual_guard_event"], guard_event)
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

        automation_history = automation_state["trigger_history"]
        assert automation_history
        guard_history = automation_history[-1]
        assert guard_history["trigger_id"] == "manual_guard_event"
        assert guard_history["script_call"]["statistics_entity_id"] == (
            "sensor.pawcontrol_statistics"
        )
        assert guard_history["followup_calls"]

        assert automation_events, "Automation should emit triggered events"
        guard_event_data = automation_events[-1].data
        assert guard_event_data.get("entity_id", "").startswith("automation.")
        assert guard_event_data.get("trigger") == "manual_guard_event"

        breaker_event = {"fired_by": "breaker"}
        await hass.bus.async_fire(base_context["manual_breaker_event"], breaker_event)
        await hass.async_block_till_done()

        assert len(script_calls) == 2
        assert len(breaker_calls) == 1
        assert breaker_calls[0].data == {"reason": "breaker"}
        assert len(guard_calls) == 1

        breaker_history = automation_state["trigger_history"][-1]
        assert breaker_history["trigger_id"] == "manual_breaker_event"
        assert breaker_history["followup_calls"]
        assert breaker_history["followup_calls"][0]["category"] == "breaker"

        assert len(automation_events) >= 2
        breaker_event_data = automation_events[-1].data
        assert breaker_event_data.get("entity_id", "").startswith("automation.")
        assert breaker_event_data.get("trigger") == "manual_breaker_event"
        automation_triggers = [
            event
            for event in hass.bus._events
            if event.event_type == EVENT_AUTOMATION_TRIGGERED
        ]
        assert len(automation_triggers) >= 2
    finally:
        await context.async_cleanup()


@pytest.mark.asyncio
async def test_resilience_blueprint_context_overrides(hass: HomeAssistant) -> None:
    """Blueprint context factory should merge overrides into the base payload."""

    context = create_resilience_blueprint_context(
        hass,
        overrides={
            "manual_guard_event": "custom_manual_guard",
            "watchdog_interval_minutes": 15,
        },
    )

    try:
        base_context = context.build_context()
        assert base_context["manual_guard_event"] == "custom_manual_guard"
        assert base_context["watchdog_interval_minutes"] == 15
        assert base_context["manual_breaker_event"] == "pawcontrol_manual_breaker"
    finally:
        await context.async_cleanup()
