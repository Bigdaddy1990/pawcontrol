"""Tests for geofence option validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "pawcontrol" / "__init__.py"
)
spec = importlib.util.spec_from_file_location("custom_components.pawcontrol", MODULE_PATH)
comp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(comp)

pytestmark = pytest.mark.asyncio


async def test_invalid_geofence_creates_issue(hass) -> None:
    """Invalid radius should create a Repairs issue."""
    import custom_components.pawcontrol as comp
    from homeassistant.helpers import issue_registry as ir

    entry = MockConfigEntry(
        domain=comp.DOMAIN,
        data={},
        options={"geofence": {"radius_m": 0, "lat": 50.0, "lon": 8.0}},
        entry_id="g1",
    )
    entry.add_to_hass(hass)

    comp._check_geofence_options(hass, entry)

    reg = ir.async_get(hass)
    issues = [
        i
        for i in reg.issues.values()
        if i.domain == comp.DOMAIN and i.issue_id == "invalid_geofence"
    ]
    assert issues, "Expected invalid_geofence issue"


async def test_invalid_latitude_range_creates_issue(hass) -> None:
    """Latitude outside valid range should create a Repairs issue."""
    import custom_components.pawcontrol as comp
    from homeassistant.helpers import issue_registry as ir

    entry = MockConfigEntry(
        domain=comp.DOMAIN,
        data={},
        options={"geofence": {"radius_m": 100, "lat": 95.0, "lon": 10.0}},
        entry_id="g2",
    )
    entry.add_to_hass(hass)

    comp._check_geofence_options(hass, entry)

    reg = ir.async_get(hass)
    issues = [
        i
        for i in reg.issues.values()
        if i.domain == comp.DOMAIN and i.issue_id == "invalid_geofence"
    ]
    assert issues, "Expected invalid_geofence issue"


async def test_valid_geofence_no_issue(hass) -> None:
    """Valid geofence settings should not create an issue."""
    import custom_components.pawcontrol as comp
    from homeassistant.helpers import issue_registry as ir

    entry = MockConfigEntry(
        domain=comp.DOMAIN,
        data={},
        options={"geofence": {"radius_m": 100, "lat": 10.0, "lon": 20.0}},
        entry_id="g3",
    )
    entry.add_to_hass(hass)

    comp._check_geofence_options(hass, entry)

    reg = ir.async_get(hass)
    issues = [
        i
        for i in reg.issues.values()
        if i.domain == comp.DOMAIN and i.issue_id == "invalid_geofence"
    ]
    assert not issues, "Did not expect invalid_geofence issue"

