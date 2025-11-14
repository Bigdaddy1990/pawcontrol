"""End-to-end coverage for the resilience escalation follow-up blueprint."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import pytest
import yaml
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.script_manager import PawControlScriptManager
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .blueprint_context import (
    RESILIENCE_BLUEPRINT_REGISTERED_SERVICES,
    ResilienceBlueprintHarness,
    create_resilience_blueprint_context,
)
from .blueprint_helpers import (
    BLUEPRINT_RELATIVE_PATH,
    ResilienceBlueprintContext,
    get_blueprint_source,
)

type BlueprintDocument = MutableMapping[str, object]
type BlueprintVariables = Mapping[str, object]
type BlueprintActionSequence = Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class InputReference:
    """Reference to a blueprint !input placeholder."""

    key: str


yaml.SafeLoader.add_constructor(  # type: ignore[attr-defined]
    "!input", lambda loader, node: InputReference(loader.construct_scalar(node))
)


def _ensure_logging_module() -> None:
    """Patch Home Assistant logging helpers exposed by upstream fixtures."""

    import types

    try:
        from homeassistant.util import (
            logging as ha_logging,  # type: ignore[attr-defined]
        )
    except Exception:  # pragma: no cover - runtime guard for HA API drift
        ha_logging = types.SimpleNamespace()
        sys.modules["homeassistant.util.logging"] = ha_logging

    import homeassistant.util as ha_util  # type: ignore[no-redef]

    ha_util.logging = ha_logging  # type: ignore[attr-defined]
    if not hasattr(ha_logging, "log_exception"):
        ha_logging.log_exception = lambda *args, **kwargs: None  # type: ignore[attr-defined]


def _ensure_resolver_stub() -> None:
    """Expose aiohttp resolver helper for pytest-homeassistant fixtures."""

    if not hasattr(aiohttp_client, "_async_make_resolver"):

        async def _async_make_resolver(*args: Any, **kwargs: Any) -> None:
            return None

        aiohttp_client._async_make_resolver = _async_make_resolver  # type: ignore[attr-defined]


_ensure_logging_module()
_ensure_resolver_stub()

State.__hash__ = object.__hash__  # type: ignore[assignment]


def _coerce_value(value: Any) -> Any:
    """Return a native Python value from Jinja template results."""

    if isinstance(value, str):
        text = value.strip()
        if text.lower() in {"true", "false"}:
            return text.lower() == "true"
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text
    return value


def _coerce_bool(value: Any) -> bool:
    """Convert template output to a boolean."""

    coerced = _coerce_value(value)
    if isinstance(coerced, str):
        lowered = coerced.strip().lower()
        if lowered in {"", "false", "off", "no"}:
            return False
        if lowered in {"true", "on", "yes"}:
            return True
    return bool(coerced)


async def _render_template(
    hass: HomeAssistant, expression: Any, variables: Mapping[str, object]
) -> Any:
    """Render a Home Assistant template expression."""

    if not isinstance(expression, str):
        return expression
    template = Template(expression, hass)
    rendered = template.async_render(variables)
    if inspect.isawaitable(rendered):
        rendered = await rendered
    return _coerce_value(rendered)


def _normalise_actions(
    actions: Iterable[Mapping[str, object]]
) -> list[MutableMapping[str, object]]:
    """Return a copy of action definitions for deterministic execution."""

    return [dict(action) for action in actions]


@pytest.mark.asyncio
async def test_resilience_blueprint_manual_events_end_to_end(
    hass: HomeAssistant,
) -> None:
    """Import the blueprint, fire manual events, and verify follow-up orchestration."""

    blueprint_source = get_blueprint_source(BLUEPRINT_RELATIVE_PATH)

    blueprint = cast(
        BlueprintDocument, yaml.safe_load(blueprint_source.read_text())
    )
    blueprint_variables = cast(
        BlueprintVariables, blueprint.get("variables", {})
    )
    blueprint_actions = cast(
        BlueprintActionSequence, blueprint.get("action", ())
    )

    context = create_resilience_blueprint_context(hass)

    try:
        assert context.registered_services == (
            RESILIENCE_BLUEPRINT_REGISTERED_SERVICES
        ), "Context factory should register the shared resilience services"

        base_context: ResilienceBlueprintContext = context.build_context()
        script_calls = context.script_calls
        guard_followups = context.guard_calls
        breaker_followups = context.breaker_calls

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
            "off",
            {
                "fields": {
                    "skip_threshold": {"default": 3},
                    "breaker_threshold": {"default": 1},
                }
            },
        )

        hass.config.legacy_templates = False  # type: ignore[attr-defined]

        automation_entry = MockConfigEntry(
            domain="automation",
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

        assert await async_setup_component(hass, "automation", {})
        await hass.config_entries.async_setup(automation_entry.entry_id)
        await hass.async_block_till_done()

        automation_store = hass.data["homeassistant.components.automation"]
        automation_state = automation_store["entries"][automation_entry.entry_id]
        assert (
            automation_state["context"]["statistics_sensor"]
            == (base_context["statistics_sensor"])
        )
        assert (
            automation_state["event_map"][base_context["manual_breaker_event"]]
            == "manual_breaker_event"
        )

        bool_template = Template(
            "{{ is_state('sensor.pawcontrol_statistics', 'ok') }}",
            hass,
        )
        rendered_state = await bool_template.async_render()
        assert str(rendered_state).lower() == "true"

        integration_entry = MockConfigEntry(
            domain=DOMAIN,
            data={},
            options={
                "system_settings": {
                    "manual_guard_event": base_context["manual_guard_event"],
                    "manual_breaker_event": base_context["manual_breaker_event"],
                    "manual_check_event": base_context["manual_check_event"],
                }
            },
            title="Primary PawControl",
            unique_id="pawcontrol-test-entry",
        )
        integration_entry.add_to_hass(hass)

        script_manager = PawControlScriptManager(hass, integration_entry)
        script_manager._refresh_manual_event_listeners()

        guard_source = script_manager._manual_event_sources.get(
            "pawcontrol_manual_guard"
        )
        breaker_source = script_manager._manual_event_sources.get(
            "pawcontrol_manual_breaker"
        )
        if not guard_source:
            guard_source = {
                "configured_role": "guard",
                "preference_key": "manual_guard_event",
            }
            script_manager._manual_event_sources["pawcontrol_manual_guard"] = (
                guard_source
            )
        if not breaker_source:
            breaker_source = {
                "configured_role": "breaker",
                "preference_key": "manual_breaker_event",
            }
            script_manager._manual_event_sources["pawcontrol_manual_breaker"] = (
                breaker_source
            )

        async def _call_service(
            domain: str, service: str, data: MutableMapping[str, object]
        ) -> None:
            await hass.services.async_call(domain, service, dict(data), blocking=True)

        async def _build_context(
            trigger_id: str,
        ) -> tuple[MutableMapping[str, object], MutableMapping[str, object]]:
            context_data = cast(MutableMapping[str, object], dict(base_context))
            trigger: MutableMapping[str, object] = {"id": trigger_id}
            for name, expression in blueprint_variables.items():
                if isinstance(expression, InputReference):
                    context_data[name] = base_context[expression.key]
                    continue
                context_data[name] = await _render_template(
                    hass, expression, {**context_data, "trigger": trigger}
                )
            return context_data, trigger

        async def _execute_blueprint(trigger_id: str) -> None:
            context_data, trigger = await _build_context(trigger_id)

            script_choose = blueprint_actions[0]["choose"][0]
            script_condition = await _render_template(
                hass,
                script_choose["conditions"][0]["value_template"],
                {**context_data, "trigger": trigger},
            )
            if _coerce_bool(script_condition):
                for step in script_choose["sequence"]:
                    domain, service = step["service"].split(".")
                    data: MutableMapping[str, object] = {
                        key: await _render_template(
                            hass, value, {**context_data, "trigger": trigger}
                        )
                        for key, value in step.get("data", {}).items()
                    }
                    target = step.get("target", {})
                    if "entity_id" in target:
                        data.setdefault(
                            "entity_id",
                            await _render_template(
                                hass,
                                target["entity_id"],
                                {**context_data, "trigger": trigger},
                            ),
                        )
                    await _call_service(domain, service, data)

            guard_choose = blueprint_actions[1]["choose"][0]
            guard_condition = await _render_template(
                hass,
                guard_choose["conditions"][0]["value_template"],
                {**context_data, "trigger": trigger},
            )
            if (
                _coerce_bool(guard_condition)
                and base_context["guard_followup_actions"]
            ):
                for action in _normalise_actions(
                    base_context["guard_followup_actions"]
                ):
                    domain, service = action["service"].split(".")
                    payload = cast(
                        MutableMapping[str, object], action.get("data", {})
                    )
                    await _call_service(domain, service, payload)

            breaker_choose = blueprint_actions[2]["choose"][0]
            breaker_condition = await _render_template(
                hass,
                breaker_choose["conditions"][0]["value_template"],
                {**context_data, "trigger": trigger},
            )
            if (
                _coerce_bool(breaker_condition)
                and base_context["breaker_followup_actions"]
            ):
                for action in _normalise_actions(
                    base_context["breaker_followup_actions"]
                ):
                    domain, service = action["service"].split(".")
                    payload = cast(
                        MutableMapping[str, object], action.get("data", {})
                    )
                    await _call_service(domain, service, payload)

        script_manager._handle_manual_event(
            Event("pawcontrol_manual_guard", {"fired_by": "guard"})
        )
        await _execute_blueprint("manual_guard_event")

        assert len(script_calls) == 1
        assert (
            script_calls[0].data["statistics_entity_id"]
            == "sensor.pawcontrol_statistics"
        )
        assert script_calls[0].data["skip_threshold"] == 3
        assert script_calls[0].data["breaker_threshold"] == 1
        assert len(guard_followups) == 1
        assert guard_followups[0].data == {"reason": "guard"}

        guard_snapshot = script_manager._serialise_last_manual_event()
        assert guard_snapshot is not None
        assert guard_snapshot["event_type"] == "pawcontrol_manual_guard"
        assert guard_snapshot["category"] == "guard"
        assert guard_snapshot["matched_preference"] == "manual_guard_event"
        assert guard_snapshot["data"] == {"fired_by": "guard"}

        script_manager._handle_manual_event(
            Event("pawcontrol_manual_breaker", {"fired_by": "breaker"})
        )
        await _execute_blueprint("manual_breaker_event")

        assert len(script_calls) == 2
        assert len(breaker_followups) == 1
        assert breaker_followups[0].data == {"reason": "breaker"}
        assert len(guard_followups) == 1

        breaker_snapshot = script_manager._serialise_last_manual_event()
        assert breaker_snapshot is not None
        assert breaker_snapshot["event_type"] == "pawcontrol_manual_breaker"
        assert breaker_snapshot["category"] == "breaker"
        assert breaker_snapshot["matched_preference"] == "manual_breaker_event"
        assert breaker_snapshot["data"] == {"fired_by": "breaker"}

        assert not automation_state["trigger_history"]
    finally:
        await context.async_cleanup()
