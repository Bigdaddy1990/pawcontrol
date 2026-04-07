"""Coverage tests for defensive type-normalisation helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol import types


@pytest.mark.parametrize(
    ("payload", "expected_none"),
    [
        pytest.param({}, True, id="empty-mapping"),
        pytest.param(
            {types.DOG_ID_FIELD: "", types.DOG_NAME_FIELD: "Buddy"},
            True,
            id="missing-dog-id",
        ),
        pytest.param(
            {types.DOG_ID_FIELD: "dog-1", types.DOG_NAME_FIELD: 7},
            True,
            id="invalid-dog-name-type",
        ),
        pytest.param(
            {types.DOG_ID_FIELD: "dog-1", types.DOG_NAME_FIELD: "Buddy"},
            False,
            id="required-fields-present",
        ),
    ],
)
def test_ensure_dog_config_data_required_fields(
    payload: dict[str, object],
    expected_none: bool,
) -> None:
    """Dog config helper returns ``None`` until mandatory string fields exist."""
    normalised = types.ensure_dog_config_data(payload)

    assert (normalised is None) is expected_none


def test_ensure_dog_config_data_normalises_optional_fields_and_trims_sensor() -> None:
    """Optional dog fields are retained only when their value types are accepted."""
    payload = {
        types.DOG_ID_FIELD: "dog-42",
        types.DOG_NAME_FIELD: "Mochi",
        types.DOG_BREED_FIELD: "Shiba",
        types.DOG_AGE_FIELD: 4,
        types.DOG_WEIGHT_FIELD: 12,
        types.DOG_COLOR_FIELD: "red",
        types.DOG_MICROCHIP_ID_FIELD: "chip-1",
        types.DOG_VET_CONTACT_FIELD: "vet@example.com",
        types.DOG_EMERGENCY_CONTACT_FIELD: "123456",
        types.CONF_DOOR_SENSOR: "  binary_sensor.back_door  ",
        "feeding": {"enabled": True},
        "walk": {"enabled": True},
    }

    normalised = types.ensure_dog_config_data(payload)

    assert normalised is not None
    assert normalised[types.DOG_WEIGHT_FIELD] == 12.0
    assert normalised[types.CONF_DOOR_SENSOR] == "binary_sensor.back_door"
    assert normalised["feeding"] == {"enabled": True}
    assert normalised["walk"] == {"enabled": True}


@pytest.mark.parametrize(
    ("value", "defaults", "expected"),
    [
        pytest.param(
            {"quiet_hours": "off"},
            {"quiet_hours": True},
            False,
            id="string-override-wins-over-default",
        ),
        pytest.param(
            {"quiet_hours": object()},
            {"quiet_hours": True},
            True,
            id="invalid-override-falls-back-to-default",
        ),
        pytest.param(
            {"quiet_hours": 0},
            None,
            False,
            id="numeric-bool-coercion",
        ),
    ],
)
def test_ensure_notification_options_bool_and_fallback_semantics(
    value: dict[str, object],
    defaults: dict[str, object] | None,
    expected: bool,
) -> None:
    """Boolean coercion should prefer valid overrides and otherwise keep defaults."""
    normalised = types.ensure_notification_options(value, defaults=defaults)

    assert normalised[types.NOTIFICATION_QUIET_HOURS_FIELD] is expected


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        pytest.param("", None, id="empty-string-ignored"),
        pytest.param(" 6 ", 6, id="string-int-coerced"),
        pytest.param(4, 5, id="minimum-clamped"),
        pytest.param(500, 180, id="maximum-clamped"),
    ],
)
def test_ensure_notification_options_interval_handling(
    interval: object,
    expected: int | None,
) -> None:
    """Reminder intervals are clamped and invalid values are ignored."""
    normalised = types.ensure_notification_options({"reminder_repeat_min": interval})

    if expected is None:
        assert types.NOTIFICATION_REMINDER_REPEAT_FIELD not in normalised
    else:
        assert normalised[types.NOTIFICATION_REMINDER_REPEAT_FIELD] == expected


@pytest.mark.parametrize(
    ("payload", "expect_none"),
    [
        pytest.param(None, True, id="none"),
        pytest.param("not-a-mapping", True, id="non-mapping"),
        pytest.param({}, True, id="empty-mapping"),
    ],
)
def test_ensure_gps_payload_rejects_empty_or_non_mapping_inputs(
    payload: object,
    expect_none: bool,
) -> None:
    """GPS payload helper returns ``None`` for absent or unusable payloads."""
    normalised = types.ensure_gps_payload(payload)

    assert (normalised is None) is expect_none


@pytest.mark.parametrize(
    ("satellites", "expected"),
    [
        pytest.param("9", 9, id="string-int"),
        pytest.param("not-int", None, id="string-valueerror"),
        pytest.param(object(), None, id="object-typeerror"),
    ],
)
def test_ensure_gps_payload_satellite_type_paths(
    satellites: object,
    expected: int | None,
) -> None:
    """Satellite coercion handles valid ints and both error paths."""
    payload = types.ensure_gps_payload({"satellites": satellites, "latitude": "1.5"})

    assert payload is not None
    assert payload["satellites"] == expected
    assert payload["latitude"] == 1.5


def test_ensure_gps_payload_float_and_timestamp_normalisation() -> None:
    """Coerce numeric/timestamp fields and keep invalid GPS values as ``None``."""
    payload = types.ensure_gps_payload({
        "last_seen": datetime(2025, 1, 1, tzinfo=UTC),
        "last_update": " 2025-01-02T03:04:05+00:00 ",
        "longitude": True,
        "speed": "4.2",
        "status": " tracking ",
        "current_route": {},
    })

    assert payload is not None
    assert payload["last_seen"].startswith("2025-01-01T")
    assert payload["last_update"] == "2025-01-02T03:04:05+00:00"
    assert payload["longitude"] is None
    assert payload["speed"] == 4.2
    assert payload["status"] == " tracking "
    assert payload["current_route"]["point_count"] == 0


def test_cache_diagnostics_snapshot_from_mapping_uses_mapping_and_typed_instances() -> (
    None
):
    """Snapshot factory should accept both plain mappings and typed summaries."""
    summary = types.CacheRepairAggregate.from_mapping({
        "severity": "minor",
        "repair_rate": 0.5,
    })

    snapshot = types.CacheDiagnosticsSnapshot.from_mapping({
        "stats": {"hits": 1},
        "diagnostics": {"cache": "ok"},
        "snapshot": {"state": "fresh"},
        "error": "broken",
        "repair_summary": summary,
    })

    assert snapshot.stats == {"hits": 1}
    assert snapshot.diagnostics == {"cache": "ok"}
    assert snapshot.snapshot == {"state": "fresh"}
    assert snapshot.error == "broken"
    assert snapshot.repair_summary is summary


def test_cache_diagnostics_snapshot_from_mapping_discards_invalid_repair_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot factory should swallow defensive parse failures from nested payloads."""

    def _raise(*_: object, **__: object) -> types.CacheRepairAggregate:
        raise RuntimeError("boom")

    monkeypatch.setattr(types.CacheRepairAggregate, "from_mapping", _raise)

    snapshot = types.CacheDiagnosticsSnapshot.from_mapping({
        "stats": {"hits": 1},
        "diagnostics": {"cache": "ok"},
        "snapshot": {"state": "fresh"},
        "error": 42,
        "repair_summary": {"repair_rate": "not-a-number"},
    })

    assert snapshot.stats == {"hits": 1}
    assert snapshot.diagnostics == {"cache": "ok"}
    assert snapshot.snapshot == {"state": "fresh"}
    assert snapshot.error is None
    assert snapshot.repair_summary is None


@pytest.mark.parametrize(
    ("payload", "expected_feedings", "expected_walks", "expected_food"),
    [
        pytest.param(
            {
                "date": "not-a-date",
                "feedings_count": True,
                "walks_count": " 2.0 ",
                "total_food_amount": False,
            },
            1,
            2,
            0.0,
            id="bool-and-float-string-coercion",
        ),
        pytest.param(
            {"feedings_count": "bad", "walks_count": "", "total_food_amount": "bad"},
            0,
            0,
            0.0,
            id="invalid-strings-default",
        ),
    ],
)
def test_daily_stats_from_dict_number_default_paths(
    payload: dict[str, object],
    expected_feedings: int,
    expected_walks: int,
    expected_food: float,
) -> None:
    """Daily stats conversion should apply typed defaults across bad payloads."""
    parsed = types.DailyStats.from_dict(payload)

    assert parsed.feedings_count == expected_feedings
    assert parsed.walks_count == expected_walks
    assert parsed.total_food_amount == expected_food


def test_daily_stats_from_dict_parses_datetime_objects_and_strings() -> None:
    """Datetime fields accept both concrete datetime values and ISO strings."""
    payload = {
        "date": datetime(2026, 1, 1, tzinfo=UTC),
        "last_feeding": "2026-01-02T00:00:00+00:00",
        "last_walk": datetime(2026, 1, 3, tzinfo=UTC),
        "last_health_event": "not-a-date",
    }

    parsed = types.DailyStats.from_dict(payload)

    assert parsed.date.tzinfo is not None
    assert parsed.last_feeding is not None
    assert parsed.last_walk is not None
    assert parsed.last_health_event is None
