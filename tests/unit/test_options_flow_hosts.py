"""Unit tests for options flow host protocols."""

from __future__ import annotations

from typing import get_type_hints

from custom_components.pawcontrol import options_flow_hosts


class _HostImplementation:
    """Minimal implementation matching ``DogOptionsHost`` protocol."""

    _current_dog = None
    _dogs = []

    def _clone_options(self) -> dict[str, object]:
        return {}

    def _current_dog_options(self) -> dict[str, object]:
        return {}

    def _current_options(self) -> dict[str, object]:
        return {}

    def _coerce_bool(self, value: object, default: bool) -> bool:
        return bool(value) if value is not None else default

    def _normalise_options_snapshot(self, options: dict[str, object]) -> dict[str, object]:
        return options

    def _build_dog_selector_schema(self):
        return object()

    def _require_current_dog(self):
        return self._current_dog

    def _select_dog_by_id(self, dog_id: str | None):
        return self._current_dog if dog_id else None

    def async_show_form(self, **kwargs: object):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs: object):
        return {"type": "create_entry", **kwargs}

    async def async_step_init(self):
        return {"type": "form", "step_id": "init"}


def test_dog_options_host_declares_expected_members() -> None:
    """The protocol should keep core host attributes and methods stable."""
    hints = get_type_hints(options_flow_hosts.DogOptionsHost)

    assert "_current_dog" in hints
    assert "_dogs" in hints
    assert hasattr(options_flow_hosts.DogOptionsHost, "_clone_options")
    assert hasattr(options_flow_hosts.DogOptionsHost, "async_step_init")


def test_concrete_host_implements_protocol_surface() -> None:
    """Concrete host stubs should expose all protocol members at runtime."""
    host = _HostImplementation()

    expected_methods = {
        "_clone_options",
        "_current_dog_options",
        "_current_options",
        "_coerce_bool",
        "_normalise_options_snapshot",
        "_build_dog_selector_schema",
        "_require_current_dog",
        "_select_dog_by_id",
        "async_show_form",
        "async_create_entry",
        "async_step_init",
    }

    assert all(callable(getattr(host, method)) for method in expected_methods)
