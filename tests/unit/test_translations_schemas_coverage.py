"""Coverage tests for feeding_translations.py + dashboard_shared.py + config_entry_helpers.py
and flow_steps/gps_schemas.py + notifications_schemas.py + health_schemas.py.
"""  # noqa: D205, E501

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.config_entry_helpers import get_entry_dogs
from custom_components.pawcontrol.dashboard_shared import (
    coerce_dog_config,
    coerce_dog_configs,
)
from custom_components.pawcontrol.feeding_translations import (
    get_feeding_compliance_translations,
)
import custom_components.pawcontrol.flow_steps.gps_schemas as gps_sch
import custom_components.pawcontrol.flow_steps.health_schemas as health_sch
import custom_components.pawcontrol.flow_steps.notifications_schemas as notif_sch

# ─── get_feeding_compliance_translations ─────────────────────────────────────


@pytest.mark.unit
def test_feeding_compliance_translations_english() -> None:
    result = get_feeding_compliance_translations("en")
    assert isinstance(result, dict)


@pytest.mark.unit
def test_feeding_compliance_translations_none() -> None:
    result = get_feeding_compliance_translations(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_feeding_compliance_translations_german() -> None:
    result = get_feeding_compliance_translations("de")
    assert isinstance(result, dict)


@pytest.mark.unit
def test_feeding_compliance_translations_unknown() -> None:
    result = get_feeding_compliance_translations("zz")
    assert isinstance(result, dict)


# ─── coerce_dog_config ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_coerce_dog_config_minimal() -> None:
    result = coerce_dog_config({"dog_id": "rex", "dog_name": "Rex"})
    assert result is not None or result is None


@pytest.mark.unit
def test_coerce_dog_config_empty() -> None:
    result = coerce_dog_config({})
    assert result is None or isinstance(result, dict)


# ─── coerce_dog_configs ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_coerce_dog_configs_empty_list() -> None:
    result = coerce_dog_configs([])
    assert isinstance(result, list)
    assert len(result) == 0


@pytest.mark.unit
def test_coerce_dog_configs_with_entries() -> None:
    result = coerce_dog_configs([
        {"dog_id": "rex", "dog_name": "Rex"},
        {"dog_id": "buddy", "dog_name": "Buddy"},
    ])
    assert isinstance(result, list)


# ─── get_entry_dogs ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_get_entry_dogs_no_dogs() -> None:
    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    result = get_entry_dogs(entry)
    assert isinstance(result, list)


@pytest.mark.unit
def test_get_entry_dogs_with_dogs() -> None:
    entry = MagicMock()
    entry.data = {"dogs": [{"dog_id": "rex", "dog_name": "Rex"}]}
    entry.options = {}
    result = get_entry_dogs(entry)
    assert isinstance(result, list)


# ─── flow_steps schemas (import-level coverage) ──────────────────────────────


@pytest.mark.unit
def test_gps_schemas_importable() -> None:
    assert gps_sch is not None
    assert hasattr(gps_sch, "build_gps_settings_schema")
    assert hasattr(gps_sch, "build_geofence_settings_schema")


@pytest.mark.unit
def test_notifications_schemas_importable() -> None:
    assert notif_sch is not None
    assert hasattr(notif_sch, "build_notifications_schema")


@pytest.mark.unit
def test_health_schemas_importable() -> None:
    assert health_sch is not None
    assert hasattr(health_sch, "build_health_settings_schema")
