"""Tests for options flow dependency resolver helpers."""

from types import SimpleNamespace
from typing import Any

from custom_components.pawcontrol import options_flow_door_sensor as module


def test_resolve_require_runtime_data_prefers_callable_override(
    monkeypatch: Any,
) -> None:
    """A callable override should be returned when available."""
    patched = object()

    def _patched_runtime_data(hass: Any, entry: Any) -> object:
        return patched

    monkeypatch.setattr(
        module,
        "import_module",
        lambda _: SimpleNamespace(require_runtime_data=_patched_runtime_data),
    )

    resolver = module._resolve_require_runtime_data()

    assert resolver is _patched_runtime_data


def test_resolve_require_runtime_data_falls_back_on_invalid_override(
    monkeypatch: Any,
) -> None:
    """Non-callable overrides should use the module default helper."""
    monkeypatch.setattr(
        module,
        "import_module",
        lambda _: SimpleNamespace(require_runtime_data="not-callable"),
    )

    assert module._resolve_require_runtime_data() is module.require_runtime_data


def test_resolve_async_create_issue_handles_import_failure(monkeypatch: Any) -> None:
    """Import failures should gracefully return the default async issue helper."""

    def _raise(_: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "import_module", _raise)

    assert module._resolve_async_create_issue() is module.async_create_issue
