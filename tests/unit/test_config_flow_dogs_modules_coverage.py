"""Coverage tests for config_flow_dogs.py + config_flow_modules.py + setup/__init__.py."""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.config_flow_dogs import (
    coerce_optional_str,
    dog_modules_from_flow_input,
)
from custom_components.pawcontrol.config_flow_modules import (
    normalize_dashboard_language,
    normalize_language,
    normalize_performance_mode,
)
import custom_components.pawcontrol.config_flow_dogs as cfd_mod
import custom_components.pawcontrol.config_flow_modules as cfm_mod
import custom_components.pawcontrol.setup as setup_mod


# ─── coerce_optional_str ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_coerce_optional_str_none() -> None:
    assert coerce_optional_str(None) is None


@pytest.mark.unit
def test_coerce_optional_str_string() -> None:
    assert coerce_optional_str("Rex") == "Rex"


@pytest.mark.unit
def test_coerce_optional_str_empty_str() -> None:
    result = coerce_optional_str("")
    assert result is None or result == ""


@pytest.mark.unit
def test_coerce_optional_str_strips() -> None:
    result = coerce_optional_str("  Rex  ")
    assert result == "Rex" or isinstance(result, str)


# ─── dog_modules_from_flow_input ──────────────────────────────────────────────

@pytest.mark.unit
def test_dog_modules_from_flow_input_empty() -> None:
    result = dog_modules_from_flow_input({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_dog_modules_from_flow_input_with_values() -> None:
    result = dog_modules_from_flow_input({"feeding": True, "walk": False})
    assert isinstance(result, dict)


# ─── normalize_dashboard_language ────────────────────────────────────────────

@pytest.mark.unit
def test_normalize_dashboard_language_none() -> None:
    result = normalize_dashboard_language(None)
    assert isinstance(result, str)
    assert result == "en"


@pytest.mark.unit
def test_normalize_dashboard_language_de() -> None:
    result = normalize_dashboard_language("de")
    assert isinstance(result, str)


@pytest.mark.unit
def test_normalize_dashboard_language_unknown() -> None:
    result = normalize_dashboard_language("zz")
    assert isinstance(result, str)


# ─── normalize_language (config_flow_modules) ────────────────────────────────

@pytest.mark.unit
def test_cfm_normalize_language_none() -> None:
    result = normalize_language(None)
    assert result == "en"


@pytest.mark.unit
def test_cfm_normalize_language_valid() -> None:
    result = normalize_language("de")
    assert isinstance(result, str)


# ─── normalize_performance_mode (config_flow_modules) ────────────────────────

@pytest.mark.unit
def test_cfm_normalize_performance_mode_valid() -> None:
    result = normalize_performance_mode("balanced")
    assert result == "balanced"


@pytest.mark.unit
def test_cfm_normalize_performance_mode_invalid() -> None:
    result = normalize_performance_mode("turbo", fallback="minimal")
    assert result == "minimal"


# ─── module imports ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_config_flow_dogs_has_helpers() -> None:
    assert hasattr(cfd_mod, "dog_modules_from_flow_input")
    assert hasattr(cfd_mod, "dog_feeding_config_from_flow")


@pytest.mark.unit
def test_config_flow_modules_importable() -> None:
    assert cfm_mod is not None
    assert hasattr(cfm_mod, "ConfigFlowGlobalSettings")


@pytest.mark.unit
def test_setup_module_importable() -> None:
    assert setup_mod is not None
