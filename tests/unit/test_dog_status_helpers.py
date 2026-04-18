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
    """Numeric truthy/falsy values should coerce to bool and zone state should render."""
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


def test_build_snapshot_home_state_variants() -> None:
    """Home-zone snapshots should derive hungry/needs-walk/home states."""
    hungry = build_dog_status_snapshot(
        "buddy",
        {
            "feeding": {"is_hungry": True},
            "walk": {"needs_walk": False},
            "gps": {"zone": "home", "geofence_status": {}},
        },
    )
    assert hungry["state"] == "hungry"
    assert hungry["is_home"] is True

    needs_walk = build_dog_status_snapshot(
        "buddy",
        {
            "feeding": {"is_hungry": False},
            "walk": {"needs_walk": True},
            "gps": {"zone": "home", "geofence_status": {}},
        },
    )
    assert needs_walk["state"] == "needs_walk"
    assert needs_walk["is_home"] is True

    home = build_dog_status_snapshot(
        "buddy",
        {
            "feeding": {"is_hungry": False},
            "walk": {"needs_walk": False},
            "gps": {"zone": "home", "geofence_status": {}},
        },
    )
    assert home["state"] == "home"
    assert home["is_home"] is True


def test_build_snapshot_safe_zone_resolution_bool_and_default_membership() -> None:
    """Safe-zone resolution should honor explicit bool flags and zone defaults."""
    explicit = build_dog_status_snapshot(
        "buddy",
        {
            "gps": {"zone": "office", "geofence_status": {"in_safe_zone": True}},
        },
    )
    assert explicit["in_safe_zone"] is True

    from_zone = build_dog_status_snapshot(
        "buddy",
        {
            "gps": {"zone": "park", "geofence_status": {"in_safe_zone": "invalid"}},
        },
    )
    assert from_zone["in_safe_zone"] is True
