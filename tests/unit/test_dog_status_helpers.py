"""Additional unit coverage for dog status snapshot helpers."""

from custom_components.pawcontrol.dog_status import build_dog_status_snapshot


def test_build_snapshot_handles_non_mapping_sections_and_blank_zone() -> None:
    """Non-mapping payload sections should gracefully fall back to defaults."""
    snapshot = build_dog_status_snapshot(
        "buddy",
        {
            "feeding": "invalid",
            "walk": 123,
            "gps": {
                "zone": "   ",
                "geofence_status": {"in_safe_zone": "invalid"},
            },
        },
    )

    assert snapshot == {
        "dog_id": "buddy",
        "state": "away",
        "zone": None,
        "is_home": False,
        "in_safe_zone": True,
        "on_walk": False,
        "needs_walk": False,
        "is_hungry": False,
    }


def test_build_snapshot_converts_numeric_flags_and_unknown_zones() -> None:
    """Numeric truthy/falsy values should coerce to bool and zone state should render."""  # noqa: E501
    snapshot = build_dog_status_snapshot(
        "fido",
        {
            "feeding": {"is_hungry": 1},
            "walk": {"walk_in_progress": 0, "needs_walk": 1},
            "gps": {
                "zone": "office",
                "geofence_status": {"in_safe_zone": 0},
            },
        },
    )

    assert snapshot == {
        "dog_id": "fido",
        "state": "at_office",
        "zone": "office",
        "is_home": False,
        "in_safe_zone": False,
        "on_walk": False,
        "needs_walk": True,
        "is_hungry": True,
    }
