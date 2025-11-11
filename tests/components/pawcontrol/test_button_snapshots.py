"""Regression tests for PawControl button attribute snapshots.

These tests validate that button entities expose stable extra attributes and
reuse cached coordinator data when normalising module payloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from unittest.mock import Mock

from custom_components.pawcontrol.button import (
    PawControlFeedMealButton,
    PawControlStartGardenSessionButton,
    PawControlStartWalkButton,
)
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_WALK,
)
from custom_components.pawcontrol.types import (
    WALK_IN_PROGRESS_FIELD,
    ButtonExtraAttributes,
)
from homeassistant.util import dt as dt_util


def _build_coordinator() -> Mock:
    """Return a coordinator stub with typed module payloads."""

    coordinator = Mock()
    coordinator.available = True
    coordinator.config_entry = Mock(entry_id="entry-id")

    now = dt_util.utcnow()
    walk_payload = {
        WALK_IN_PROGRESS_FIELD: False,
        "current_walk_id": "walk-123",
        "current_walk_start": (now - timedelta(hours=1)).isoformat(),
        "last_walk": (now - timedelta(days=1)).isoformat(),
    }
    gps_payload = {
        "latitude": 51.5,
        "longitude": -0.1,
        "accuracy": 3.2,
        "last_fix": now.isoformat(),
    }
    garden_payload = {
        "status": "idle",
        "pending_confirmations": [],
        "sessions_today": 1,
    }

    dog_state = {
        MODULE_WALK: walk_payload,
        MODULE_GPS: gps_payload,
        MODULE_GARDEN: garden_payload,
        "dog_info": {ATTR_DOG_ID: "dog-1", ATTR_DOG_NAME: "Rex"},
    }

    coordinator.data = {"dog-1": dog_state}
    coordinator.get_dog_data = Mock(side_effect=lambda dog_id: coordinator.data[dog_id])

    return coordinator


def test_button_extra_attributes_snapshot() -> None:
    """Button extra attributes expose a typed snapshot of metadata."""

    coordinator = _build_coordinator()
    button = PawControlFeedMealButton(coordinator, "dog-1", "Rex", "breakfast")

    pressed_at = dt_util.utcnow().isoformat()
    button._last_pressed = pressed_at  # Home Assistant sets this attribute at runtime.

    attrs = button.extra_state_attributes
    assert isinstance(attrs, Mapping)

    expected: ButtonExtraAttributes = {
        ATTR_DOG_ID: "dog-1",
        ATTR_DOG_NAME: "Rex",
        "button_type": "feed_breakfast",
        "last_pressed": pressed_at,
        "action_description": "Log breakfast feeding",
    }
    assert attrs == expected


def test_module_payload_snapshots_reuse_cached_dog_data() -> None:
    """Module payload helpers reuse cached coordinator data across lookups."""

    coordinator = _build_coordinator()
    button = PawControlStartWalkButton(coordinator, "dog-1", "Rex")

    walk_payload = button._get_walk_payload()
    gps_payload = button._get_gps_payload()
    garden_payload = button._get_garden_payload()

    assert walk_payload == coordinator.data["dog-1"][MODULE_WALK]
    assert gps_payload == coordinator.data["dog-1"][MODULE_GPS]
    assert garden_payload == coordinator.data["dog-1"][MODULE_GARDEN]
    assert coordinator.get_dog_data.call_count == 1

    # A second call should reuse the cache and avoid re-fetching from the coordinator.
    assert button._get_walk_payload() == walk_payload
    assert coordinator.get_dog_data.call_count == 1


def test_module_payload_snapshots_ignore_non_mappings() -> None:
    """Invalid module payloads are ignored while leaving valid caches intact."""

    coordinator = _build_coordinator()
    button = PawControlStartGardenSessionButton(coordinator, "dog-1", "Rex")

    # Inject a non-mapping payload and ensure the helper falls back to ``None``.
    coordinator.data["dog-1"][MODULE_GARDEN] = ["unexpected"]  # type: ignore[index]

    assert button._get_garden_payload() is None

    # Restoring a mapping should be reflected once the cache expires.
    coordinator.data["dog-1"][MODULE_GARDEN] = {
        "status": "active",
        "pending_confirmations": ["snapshot"],
    }

    # Advance time beyond the cache TTL to force a refresh.
    button._cache_timestamp.clear()
    button._dog_data_cache.clear()

    payload = button._get_garden_payload()
    assert payload == coordinator.data["dog-1"][MODULE_GARDEN]
    assert coordinator.get_dog_data.call_count == 2
