"""Coverage tests for options_flow_feeding.py + options_flow_main.py + config_flow_main.py."""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.options_flow_main import (
    ensure_advanced_options,
    ensure_json_mapping,
)
from custom_components.pawcontrol.config_flow_main import (
    build_profile_summary_text,
    coerce_dog_modules_config,
)
import custom_components.pawcontrol.options_flow_feeding as off_mod
import custom_components.pawcontrol.options_flow_main as ofm_mod
import custom_components.pawcontrol.config_flow_main as cfm_mod


# ─── ensure_json_mapping (options_flow_main) ─────────────────────────────────

@pytest.mark.unit
def test_ofm_ensure_json_mapping_none() -> None:
    result = ensure_json_mapping(None)
    assert isinstance(result, dict)
    assert len(result) == 0


@pytest.mark.unit
def test_ofm_ensure_json_mapping_with_data() -> None:
    result = ensure_json_mapping({"key": "value", "num": 42})
    assert result["key"] == "value"

# ─── ensure_advanced_options (options_flow_main) ─────────────────────────────

@pytest.mark.unit
def test_ofm_ensure_advanced_options_empty() -> None:
    result = ensure_advanced_options({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ofm_ensure_advanced_options_with_defaults() -> None:
    result = ensure_advanced_options({}, defaults={"debug_mode": False})
    assert isinstance(result, dict)


# ─── build_profile_summary_text (config_flow_main) ───────────────────────────

@pytest.mark.unit
def test_cfm_build_profile_summary_text_returns_str() -> None:
    result = build_profile_summary_text()
    assert isinstance(result, str)


# ─── coerce_dog_modules_config (config_flow_main) ────────────────────────────

@pytest.mark.unit
def test_cfm_coerce_dog_modules_config_none() -> None:
    result = coerce_dog_modules_config(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_cfm_coerce_dog_modules_config_empty() -> None:
    result = coerce_dog_modules_config({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_cfm_coerce_dog_modules_config_with_values() -> None:
    result = coerce_dog_modules_config({"feeding": True, "walk": False})
    assert isinstance(result, dict)


# ─── module import checks ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_options_flow_feeding_importable() -> None:
    assert off_mod is not None
    assert hasattr(off_mod, "FeedingOptionsMixin")
    assert hasattr(off_mod, "FeedingOptions")


@pytest.mark.unit
def test_options_flow_feeding_has_ensure_entry() -> None:
    assert hasattr(off_mod, "ensure_dog_options_entry")
    assert callable(off_mod.ensure_dog_options_entry)


@pytest.mark.unit
def test_options_flow_main_has_ensure_dog_config() -> None:
    assert hasattr(ofm_mod, "ensure_dog_config_data")
    assert hasattr(ofm_mod, "DogManagementOptionsMixin")


@pytest.mark.unit
def test_config_flow_main_has_config_flow() -> None:
    assert hasattr(cfm_mod, "ConfigFlow")
    assert hasattr(cfm_mod, "clone_placeholders")
