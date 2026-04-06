"""Unit tests for shared test helpers and payload factories."""

from typing import TypedDict

import pytest

from tests.helpers import typed_deepcopy
from tests.helpers.factories import (
    build_coordinator_payload,
    build_coordinator_payload_variant,
)

pytestmark = pytest.mark.unit


class _ExamplePayload(TypedDict):
    """TypedDict that mimics a FeedingManager setup payload snippet."""

    dog_id: str
    modules: dict[str, bool]


def test_typed_deepcopy_returns_fully_detached_clone() -> None:
    """Ensure ``typed_deepcopy`` returns a deep copy that preserves typing."""
    original: _ExamplePayload = {
        "dog_id": "buddy",
        "modules": {"feeding": True, "walk": True},
    }

    clone = typed_deepcopy(original)

    assert clone == original
    assert clone is not original
    assert clone["modules"] is not original["modules"]

    clone["modules"]["walk"] = False

    assert original["modules"]["walk"] is True


@pytest.mark.parametrize(
    ("variant", "status", "state", "zone", "visitor_mode"),
    [
        pytest.param("online_home", "online", "resting", "home", False),
        pytest.param("offline", "offline", "unknown", "home", False),
        pytest.param("visitor_mode", "online", "resting", "home", True),
        pytest.param("outside_home", "online", "walking", "park", False),
    ],
)
def test_coordinator_payload_variant_matrix(
    variant: str,
    status: str,
    state: str,
    zone: str,
    visitor_mode: bool,
) -> None:
    """Coordinator payload factories should emit consistent variant snapshots."""
    payload = build_coordinator_payload_variant(variant)

    assert payload["status"] == status
    assert payload["status_snapshot"]["state"] == state
    assert payload["gps"]["zone"] == zone
    assert payload["visitor_mode_active"] is visitor_mode


def test_coordinator_payload_factory_overrides_fields() -> None:
    """The generic payload factory should support explicit field overrides."""
    payload = build_coordinator_payload(dog_id="max", dog_name="Max", zone="garden")

    assert payload["dog_info"]["dog_id"] == "max"
    assert payload["dog_info"]["dog_name"] == "Max"
    assert payload["gps"]["zone"] == "garden"
