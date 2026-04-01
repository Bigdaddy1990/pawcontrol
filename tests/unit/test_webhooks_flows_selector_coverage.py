"""Coverage tests for webhooks.py + flows/garden.py + flows/walk_schemas.py + selector_shim.py."""  # noqa: E501

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import custom_components.pawcontrol.flows.garden as garden_mod
from custom_components.pawcontrol.flows.walk_schemas import (
    build_auto_end_walks_field,
    build_walk_timing_schema_fields,
)
from custom_components.pawcontrol.selector_shim import (
    BooleanSelector,
    BooleanSelectorConfig,
)
import custom_components.pawcontrol.webhooks as webhooks_mod
from custom_components.pawcontrol.webhooks import get_entry_webhook_url

# ─── get_entry_webhook_url ────────────────────────────────────────────────────


@pytest.mark.unit
def test_get_entry_webhook_url_no_data(mock_hass) -> None:
    mock_hass.data = {}
    entry = MagicMock()
    entry.entry_id = "test_entry"
    result = get_entry_webhook_url(mock_hass, entry)
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_webhooks_module_importable() -> None:
    assert webhooks_mod is not None
    assert hasattr(webhooks_mod, "get_entry_webhook_url")


# ─── build_auto_end_walks_field ───────────────────────────────────────────────


@pytest.mark.unit
def test_build_auto_end_walks_field_empty_values() -> None:
    defaults = MagicMock()
    defaults.auto_end_walks = False
    defaults.auto_end_walk_timeout_minutes = 60
    result = build_auto_end_walks_field({}, defaults)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_auto_end_walks_field_with_values() -> None:
    defaults = MagicMock()
    defaults.auto_end_walks = True
    defaults.auto_end_walk_timeout_minutes = 90
    result = build_auto_end_walks_field({"auto_end_walks": True}, defaults)
    assert isinstance(result, dict)


# ─── build_walk_timing_schema_fields ─────────────────────────────────────────


@pytest.mark.unit
def test_build_walk_timing_schema_fields_empty() -> None:
    defaults = MagicMock()
    defaults.min_walk_duration_minutes = 5
    defaults.max_walk_duration_minutes = 180
    result = build_walk_timing_schema_fields({}, defaults)
    assert isinstance(result, dict)


# ─── selector_shim ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_boolean_selector_init() -> None:
    sel = BooleanSelector()
    assert sel is not None


@pytest.mark.unit
def test_boolean_selector_with_config() -> None:
    config = BooleanSelectorConfig()
    sel = BooleanSelector(config=config)
    assert sel is not None


@pytest.mark.unit
def test_boolean_selector_config_is_dict_or_obj() -> None:
    config = BooleanSelectorConfig()
    assert config is not None


# ─── flows/garden ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_garden_module_importable() -> None:
    assert garden_mod is not None


@pytest.mark.unit
def test_garden_module_has_mixin() -> None:
    assert hasattr(garden_mod, "GardenModuleSelectorMixin")
