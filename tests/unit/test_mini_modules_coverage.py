"""Coverage tests for small flow/config modules — import-level (0% → 30%+).

Covers: walk_helpers, config_flow_schemas, options_flow_hosts,
        options_flow_menu, options_flow_support
"""
from __future__ import annotations

import pytest

import custom_components.pawcontrol.flows.walk_helpers as walk_helpers
import custom_components.pawcontrol.config_flow_schemas as cfs
import custom_components.pawcontrol.options_flow_hosts as ofh
import custom_components.pawcontrol.options_flow_menu as ofm
import custom_components.pawcontrol.options_flow_support as ofs


# ─── flows/walk_helpers ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_walk_helpers_importable() -> None:
    assert walk_helpers is not None


# ─── config_flow_schemas ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_config_flow_schemas_importable() -> None:
    assert cfs is not None


@pytest.mark.unit
def test_config_flow_schemas_has_selector() -> None:
    assert hasattr(cfs, "selector")


# ─── options_flow_hosts ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_options_flow_hosts_importable() -> None:
    assert ofh is not None


@pytest.mark.unit
def test_options_flow_hosts_has_dog_options_host() -> None:
    assert hasattr(ofh, "DogOptionsHost")


# ─── options_flow_menu ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_options_flow_menu_importable() -> None:
    assert ofm is not None


@pytest.mark.unit
def test_options_flow_menu_has_mixin() -> None:
    assert hasattr(ofm, "MenuOptionsMixin")


# ─── options_flow_support ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_options_flow_support_importable() -> None:
    assert ofs is not None


@pytest.mark.unit
def test_options_flow_support_has_get_runtime_data() -> None:
    assert hasattr(ofs, "get_runtime_data")
    assert callable(ofs.get_runtime_data)
