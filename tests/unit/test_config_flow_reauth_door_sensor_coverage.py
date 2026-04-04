"""Coverage tests for config_flow_base.py, config_flow_reauth.py,
options_flow_door_sensor.py, config_flow_dashboard_extension.py
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.config_flow_reauth import is_dog_config_payload_valid
from custom_components.pawcontrol.options_flow_door_sensor import (
    ensure_door_sensor_settings_config,
)
from custom_components.pawcontrol.config_flow_dashboard_extension import (
    normalize_dashboard_language,
)
import custom_components.pawcontrol.config_flow_base as cfb_mod
import custom_components.pawcontrol.config_flow_reauth as cfr_mod
import custom_components.pawcontrol.options_flow_door_sensor as ofds_mod
import custom_components.pawcontrol.config_flow_dashboard_extension as cfde_mod


# ─── is_dog_config_payload_valid (config_flow_reauth) ────────────────────────

@pytest.mark.unit
def test_cfr_is_valid_empty() -> None:
    assert is_dog_config_payload_valid({}) is False


@pytest.mark.unit
def test_cfr_is_valid_with_id_and_name() -> None:
    assert is_dog_config_payload_valid({"dog_id": "rex", "dog_name": "Rex"}) is True


@pytest.mark.unit
def test_cfr_is_valid_missing_name() -> None:
    assert is_dog_config_payload_valid({"dog_id": "rex"}) is False


@pytest.mark.unit
def test_cfr_is_valid_missing_id() -> None:
    assert is_dog_config_payload_valid({"dog_name": "Rex"}) is False


# ─── ensure_door_sensor_settings_config ──────────────────────────────────────

@pytest.mark.unit
def test_ensure_door_sensor_empty() -> None:
    result = ensure_door_sensor_settings_config({})
    assert result is not None  # DoorSensorSettingsConfig dataclass


@pytest.mark.unit
def test_ensure_door_sensor_none() -> None:
    result = ensure_door_sensor_settings_config(None)
    assert result is not None


@pytest.mark.unit
def test_ensure_door_sensor_with_values() -> None:
    result = ensure_door_sensor_settings_config({"auto_end_walks": True})
    assert result is not None
    assert hasattr(result, "auto_end_walks")


# ─── normalize_dashboard_language (dashboard_extension) ──────────────────────

@pytest.mark.unit
def test_cfde_normalize_none() -> None:
    assert normalize_dashboard_language(None) == "en"


@pytest.mark.unit
def test_cfde_normalize_de() -> None:
    result = normalize_dashboard_language("de")
    assert isinstance(result, str)


@pytest.mark.unit
def test_cfde_normalize_unknown() -> None:
    result = normalize_dashboard_language("xx")
    assert isinstance(result, str)


# ─── module import checks ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_config_flow_base_importable() -> None:
    assert hasattr(cfb_mod, "ConfigFlowGlobalSettings")
    assert hasattr(cfb_mod, "ensure_dog_modules_mapping")


@pytest.mark.unit
def test_config_flow_reauth_has_placeholders() -> None:
    assert hasattr(cfr_mod, "freeze_placeholders")
    assert hasattr(cfr_mod, "clone_placeholders")


@pytest.mark.unit
def test_options_flow_door_sensor_has_mixin() -> None:
    assert hasattr(ofds_mod, "DoorSensorOptionsMixin")
    assert hasattr(ofds_mod, "ensure_dog_config_data")


@pytest.mark.unit
def test_config_flow_dashboard_extension_has_mixin() -> None:
    assert hasattr(cfde_mod, "DashboardFlowMixin")
    assert hasattr(cfde_mod, "freeze_placeholders")
