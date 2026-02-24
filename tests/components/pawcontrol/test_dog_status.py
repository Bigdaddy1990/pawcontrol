import pytest

from custom_components.pawcontrol.dog_status import (
    _coerce_mapping,
    _coerce_zone_name,
    _derive_status_state,
    _resolve_safe_zone,
    build_dog_status_snapshot,
)


def test_build_dog_status_snapshot_prefers_walk_state() -> None:
    snapshot = build_dog_status_snapshot(
        "dog-1",
        {
            "feeding": {"is_hungry": True},
            "walk": {"walk_in_progress": True, "needs_walk": True},
            "gps": {"zone": " park ", "geofence_status": {"in_safe_zone": 0}},
        },
    )

    assert snapshot == {
        "dog_id": "dog-1",
        "state": "walking",
        "zone": "park",
        "is_home": False,
        "in_safe_zone": False,
        "on_walk": True,
        "needs_walk": True,
        "is_hungry": True,
    }


@pytest.mark.parametrize(
    ("on_walk", "is_home", "is_hungry", "needs_walk", "zone", "expected"),
    [
        (False, True, True, True, "home", "hungry"),
        (False, True, False, True, "home", "needs_walk"),
        (False, True, False, False, "home", "home"),
        (False, False, False, False, "vet", "at_vet"),
        (False, False, False, False, None, "away"),
    ],
)
def test_derive_status_state_variants(
    on_walk: bool,
    is_home: bool,
    is_hungry: bool,
    needs_walk: bool,
    zone: str | None,
    expected: str,
) -> None:
    assert (
        _derive_status_state(
            on_walk=on_walk,
            is_home=is_home,
            is_hungry=is_hungry,
            needs_walk=needs_walk,
            zone=zone,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("geofence_status", "zone", "expected"),
    [
        ({"in_safe_zone": True}, "outside", True),
        ({"in_safe_zone": 0}, "outside", False),
        ({"in_safe_zone": 3}, "outside", True),
        ({"in_safe_zone": "ignored"}, "home", True),
        ({}, None, True),
        ({}, "friend_house", True),
        ({}, "unknown_zone", False),
    ],
)
def test_resolve_safe_zone_variants(
    geofence_status: dict[str, object], zone: str | None, expected: bool
) -> None:
    assert _resolve_safe_zone(geofence_status, zone) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"a": 1}, {"a": 1}),
        (None, {}),
        ("bad", {}),
    ],
)
def test_coercion_helpers(value: object, expected: dict[str, object]) -> None:
    assert _coerce_mapping(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" home ", "home"),
        ("   ", None),
        (None, None),
        (42, None),
    ],
)
def test_coerce_zone_name(value: object, expected: str | None) -> None:
    assert _coerce_zone_name(value) == expected
