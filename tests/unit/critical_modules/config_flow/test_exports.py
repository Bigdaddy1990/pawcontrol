"""Gate-oriented tests for ``config_flow.py`` export behavior."""

import importlib

import pytest

from custom_components.pawcontrol import config_flow, config_flow_main

# Validation cluster


def test_config_flow_exports_match_main_module() -> None:
    """The entrypoint shim should re-export both flow classes exactly."""
    assert config_flow.ConfigFlow is config_flow_main.ConfigFlow
    assert config_flow.PawControlConfigFlow is config_flow_main.PawControlConfigFlow


# Error-path cluster


def test_config_flow_unknown_export_raises_attribute_error() -> None:
    """Unknown symbols must not silently appear in the shim namespace."""
    with pytest.raises(AttributeError):
        _ = config_flow.NotARealFlow  # type: ignore[attr-defined]


# Recovery cluster


def test_config_flow_reload_keeps_export_aliases_stable() -> None:
    """Module reload should preserve class alias wiring after import recovery."""
    reloaded = importlib.reload(config_flow)
    assert reloaded.ConfigFlow is config_flow_main.ConfigFlow


# Result-persistence cluster


def test_config_flow_exports_tuple_is_stable() -> None:
    """The public export list should stay deterministic for entrypoint tooling."""
    assert config_flow.__all__ == ("ConfigFlow", "PawControlConfigFlow")
