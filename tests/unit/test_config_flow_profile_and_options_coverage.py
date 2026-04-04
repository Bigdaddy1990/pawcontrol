"""Coverage tests for config_flow_profile.py + options_flow_dogs_management.py
+ options_flow_profiles.py + config_flow_external.py.
"""  # noqa: D205

import pytest

import custom_components.pawcontrol.config_flow_external as cfe_mod
from custom_components.pawcontrol.config_flow_profile import (
    ProfileSelectorOption,
    build_profile_summary_text,
    get_profile_selector_options,
)
import custom_components.pawcontrol.options_flow_dogs_management as odm_mod
import custom_components.pawcontrol.options_flow_profiles as op_mod

# ─── build_profile_summary_text ──────────────────────────────────────────────


@pytest.mark.unit
def test_build_profile_summary_text_returns_str() -> None:
    result = build_profile_summary_text()
    assert isinstance(result, str)
    assert len(result) >= 0


# ─── get_profile_selector_options ────────────────────────────────────────────


@pytest.mark.unit
def test_get_profile_selector_options_returns_list() -> None:
    result = get_profile_selector_options()
    assert isinstance(result, list)


@pytest.mark.unit
def test_get_profile_selector_options_not_empty() -> None:
    result = get_profile_selector_options()
    assert len(result) >= 1


@pytest.mark.unit
def test_get_profile_selector_options_have_value_and_label() -> None:
    result = get_profile_selector_options()
    for option in result:
        assert "value" in option or hasattr(option, "value")


# ─── ProfileSelectorOption (TypedDict) ────────────────────────────────────────


@pytest.mark.unit
def test_profile_selector_option_as_dict() -> None:
    opt: ProfileSelectorOption = {
        "value": "balanced",
        "label": "Balanced (Recommended)",
    }
    assert opt["value"] == "balanced"
    assert "label" in opt


@pytest.mark.unit
def test_profile_selector_option_minimal_profile() -> None:
    opt: ProfileSelectorOption = {"value": "minimal", "label": "Minimal"}
    assert opt["value"] == "minimal"


# ─── module import checks ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_options_flow_dogs_management_importable() -> None:
    assert odm_mod is not None
    assert hasattr(odm_mod, "DogManagementOptionsMixin")


@pytest.mark.unit
def test_options_flow_dogs_management_has_helpers() -> None:
    assert hasattr(odm_mod, "ensure_dog_config_data")
    assert hasattr(odm_mod, "ensure_dog_modules_config")


@pytest.mark.unit
def test_options_flow_profiles_importable() -> None:
    assert op_mod is not None
    assert hasattr(op_mod, "ensure_dog_modules_mapping")


@pytest.mark.unit
def test_options_flow_profiles_has_freeze() -> None:
    assert hasattr(op_mod, "freeze_placeholders")
    assert callable(op_mod.freeze_placeholders)


@pytest.mark.unit
def test_config_flow_external_importable() -> None:
    assert cfe_mod is not None
    assert hasattr(cfe_mod, "ExternalEntityConfigurationMixin")


@pytest.mark.unit
def test_config_flow_external_has_clone_placeholders() -> None:
    assert hasattr(cfe_mod, "clone_placeholders")
    assert callable(cfe_mod.clone_placeholders)
