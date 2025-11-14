"""Helpers for building resilience blueprint test contexts."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Final, cast

from homeassistant.components.automation import EVENT_AUTOMATION_TRIGGERED
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    HomeAssistant,
    ServiceCall,
    callback,
)

from .blueprint_helpers import (
    BLUEPRINT_RELATIVE_PATH,
    DEFAULT_RESILIENCE_BLUEPRINT_CONTEXT,
    ResilienceBlueprintContext,
    ResilienceBlueprintOverrides,
    ensure_blueprint_imported,
)

RegisteredService = tuple[str, str]

RESILIENCE_BLUEPRINT_REGISTERED_SERVICES: Final[frozenset[RegisteredService]] = (
    frozenset(
        {
            ("script", "turn_on"),
            ("test", "guard_followup"),
            ("test", "breaker_followup"),
        }
    )
)


@dataclass(slots=True)
class ResilienceBlueprintHarness(
    AbstractContextManager["ResilienceBlueprintHarness"],
    AbstractAsyncContextManager["ResilienceBlueprintHarness"],
):
    """Container describing the shared blueprint automation test context."""

    hass: HomeAssistant
    base_context: ResilienceBlueprintContext
    script_calls: list[ServiceCall] = field(default_factory=list)
    guard_calls: list[ServiceCall] = field(default_factory=list)
    breaker_calls: list[ServiceCall] = field(default_factory=list)
    automation_events: list[Event] = field(default_factory=list)
    registered_services: frozenset[RegisteredService] = field(
        default=RESILIENCE_BLUEPRINT_REGISTERED_SERVICES
    )
    _unsubscribe: CALLBACK_TYPE | None = field(default=None, repr=False)

    def __enter__(self) -> ResilienceBlueprintHarness:  # pragma: no cover - shim
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cleanup()

    async def __aenter__(self) -> ResilienceBlueprintHarness:  # pragma: no cover
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.async_cleanup()

    def cleanup(self) -> None:
        """Release registered callbacks for Home Assistant listeners."""

        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        self.script_calls.clear()
        self.guard_calls.clear()
        self.breaker_calls.clear()
        self.automation_events.clear()

    async def async_cleanup(self) -> None:
        """Release callbacks and unregister test services asynchronously."""

        self.cleanup()
        for domain, service in self.registered_services:
            if not self.hass.services.has_service(domain, service):
                continue
            async_remove = getattr(self.hass.services, "async_remove", None)
            if callable(async_remove):
                await async_remove(domain, service)
                continue
            # Fallback for the lightweight service registry shipped with tests.
            registry = getattr(self.hass.services, "_services", {})
            domain_services = registry.get(domain)
            if isinstance(domain_services, dict):
                domain_services.pop(service, None)

    def build_context(
        self, overrides: ResilienceBlueprintOverrides | None = None
    ) -> ResilienceBlueprintContext:
        """Return a blueprint context merged with the provided overrides."""

        mutable_context = cast(dict[str, object], deepcopy(self.base_context))
        if overrides:
            mutable_context.update(overrides)
        return cast(ResilienceBlueprintContext, mutable_context)


def _register_service_recorders(
    hass: HomeAssistant,
    definitions: Iterable[tuple[str, str, list[ServiceCall]]],
) -> frozenset[RegisteredService]:
    """Register service handlers that record incoming service calls."""

    registered: set[RegisteredService] = set()

    for domain, service, bucket in definitions:

        async def _record(
            call: ServiceCall, bucket: list[ServiceCall] = bucket
        ) -> None:
            bucket.append(call)

        hass.services.async_register(domain, service, _record)
        registered.add((domain, service))

    registered_services = frozenset(registered)
    if registered_services != RESILIENCE_BLUEPRINT_REGISTERED_SERVICES:
        raise AssertionError(
            "Unexpected service registration set for resilience blueprint context",
        )
    return registered_services


def create_resilience_blueprint_context(
    hass: HomeAssistant,
    *,
    overrides: ResilienceBlueprintOverrides | None = None,
    watch_automation_events: bool = False,
) -> ResilienceBlueprintHarness:
    """Return a configured resilience blueprint context for tests."""

    ensure_blueprint_imported(hass, BLUEPRINT_RELATIVE_PATH)

    base_context = _build_base_context(overrides)
    script_calls: list[ServiceCall] = []
    guard_calls: list[ServiceCall] = []
    breaker_calls: list[ServiceCall] = []

    registered_services = _register_service_recorders(
        hass,
        (
            ("script", "turn_on", script_calls),
            ("test", "guard_followup", guard_calls),
            ("test", "breaker_followup", breaker_calls),
        ),
    )

    automation_events: list[Event] = []
    unsubscribe: CALLBACK_TYPE | None = None

    if watch_automation_events:

        @callback
        def _record_event(event: Event) -> None:
            automation_events.append(event)

        unsubscribe = hass.bus.async_listen(EVENT_AUTOMATION_TRIGGERED, _record_event)

    return ResilienceBlueprintHarness(
        hass=hass,
        base_context=base_context,
        script_calls=script_calls,
        guard_calls=guard_calls,
        breaker_calls=breaker_calls,
        automation_events=automation_events,
        registered_services=registered_services,
        _unsubscribe=unsubscribe,
    )


def _build_base_context(
    overrides: ResilienceBlueprintOverrides | None,
) -> ResilienceBlueprintContext:
    base_context = cast(
        dict[str, object], deepcopy(DEFAULT_RESILIENCE_BLUEPRINT_CONTEXT)
    )
    if overrides:
        base_context.update(overrides)
    return cast(ResilienceBlueprintContext, base_context)
