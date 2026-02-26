"""Tests for flow_steps package exports and runtime helper resolution."""

from types import SimpleNamespace

from custom_components.pawcontrol import flow_steps
from custom_components.pawcontrol.flow_steps import system_settings


def test_flow_steps_package_exports_expected_mixins() -> None:
    """The package should expose all public flow mixins in __all__."""
    expected_exports = {
        "DogGPSFlowMixin",
        "GPSModuleDefaultsMixin",
        "GPSOptionsMixin",
        "DogHealthFlowMixin",
        "HealthSummaryMixin",
        "HealthOptionsMixin",
        "NotificationOptionsMixin",
        "NotificationOptionsNormalizerMixin",
        "SystemSettingsOptionsMixin",
    }

    assert set(flow_steps.__all__) == expected_exports
    for export_name in expected_exports:
        assert hasattr(flow_steps, export_name)


def test_resolve_get_runtime_data_returns_patched_callable(
    monkeypatch,
) -> None:
    """A callable patch in options_flow_support should be preferred."""
    patched = object()

    def _callable_runtime_data_getter(*_: object) -> object:
        return patched

    monkeypatch.setattr(
        system_settings,
        "import_module",
        lambda _name: SimpleNamespace(get_runtime_data=_callable_runtime_data_getter),
    )

    resolved = system_settings._resolve_get_runtime_data()

    assert resolved is _callable_runtime_data_getter


def test_resolve_get_runtime_data_falls_back_when_patch_missing(
    monkeypatch,
) -> None:
    """Fallback helper should be returned when patched symbol is missing."""
    monkeypatch.setattr(
        system_settings,
        "import_module",
        lambda _name: SimpleNamespace(get_runtime_data="not-callable"),
    )

    resolved = system_settings._resolve_get_runtime_data()

    assert resolved is system_settings._get_runtime_data


def test_resolve_get_runtime_data_falls_back_when_import_fails(
    monkeypatch,
) -> None:
    """Fallback helper should be returned when import_module raises."""

    def _raise_import_error(_name: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(system_settings, "import_module", _raise_import_error)

    resolved = system_settings._resolve_get_runtime_data()

    assert resolved is system_settings._get_runtime_data
