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


def test_ensure_dog_config_data_includes_text_and_non_default_door_sensor_settings(
) -> None:
    """Dog config should include text snapshots and non-default door settings."""
    payload = {
        types.DOG_ID_FIELD: "dog-9",
        types.DOG_NAME_FIELD: "Nori",
        types.CONF_DOOR_SENSOR_SETTINGS: {
            "walk_detection_timeout": 600,
            "minimum_walk_duration": 120,
            "maximum_walk_duration": 4800,
            "door_closed_delay": 10,
            "require_confirmation": False,
            "auto_end_walks": False,
            "confidence_threshold": 0.9,
        },
        types.DOG_TEXT_VALUES_FIELD: {
            "custom_label": "Ready",
            "notes": "Very playful",
        },
        types.DOG_TEXT_METADATA_FIELD: {
            "custom_label": {
                "last_updated": "2026-01-10T10:00:00+00:00",
                "context_id": "ctx-1",
            },
        },
    }

    normalised = types.ensure_dog_config_data(payload)

    assert normalised is not None
    assert normalised["door_sensor_settings"]["walk_detection_timeout"] == 600
    assert normalised[types.DOG_TEXT_VALUES_FIELD]["custom_label"] == "Ready"
    assert (
        normalised[types.DOG_TEXT_METADATA_FIELD]["custom_label"]["context_id"]
        == "ctx-1"
    )


def test_ensure_dog_config_data_drops_default_door_sensor_settings_payload() -> None:
    """Default door sensor settings should not be stored in dog config payloads."""
    payload = {
        types.DOG_ID_FIELD: "dog-10",
        types.DOG_NAME_FIELD: "Yuki",
        types.CONF_DOOR_SENSOR_SETTINGS: {
            "walk_detection_timeout": types.DEFAULT_WALK_DETECTION_TIMEOUT,
            "minimum_walk_duration": types.DEFAULT_MINIMUM_WALK_DURATION,
            "maximum_walk_duration": types.DEFAULT_MAXIMUM_WALK_DURATION,
            "door_closed_delay": types.DEFAULT_DOOR_CLOSED_DELAY,
            "require_confirmation": True,
            "auto_end_walks": True,
            "confidence_threshold": types.DEFAULT_CONFIDENCE_THRESHOLD,
        },
    }

    normalised = types.ensure_dog_config_data(payload)

    assert normalised is not None
    assert "door_sensor_settings" not in normalised


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


def test_ensure_gps_route_snapshot_filters_invalid_points_and_optional_fields() -> None:
    """Route snapshots should keep only valid point mappings and numeric options."""
    snapshot = types.ensure_gps_route_snapshot({
        "id": "route-1",
        "name": "",
        "active": 1,
        "points": [
            {"latitude": "52.5", "longitude": "13.4", "altitude": "45"},
            {"latitude": "bad", "longitude": "13.5"},
            "invalid-point",
            {"latitude": 53.0, "longitude": 13.6, "speed": "3.1"},
        ],
        "distance": "2.75",
        "duration": "42",
        "end_time": " 2025-01-02T04:05:06+00:00 ",
        "last_point_time": "",
    })

    assert snapshot is not None
    assert snapshot["active"] is True
    assert snapshot["name"] == "route-1"
    assert snapshot["point_count"] == 2
    assert snapshot["points"][0]["latitude"] == 52.5
    assert snapshot["points"][0]["altitude"] == 45.0
    assert snapshot["points"][1]["speed"] == 3.1
    assert snapshot["distance"] == 2.75
    assert snapshot["duration"] == 42.0
    assert snapshot["end_time"] == "2025-01-02T04:05:06+00:00"
    assert "last_point_time" not in snapshot


def test_ensure_gps_payload_removes_invalid_current_route_and_keeps_active_route() -> (
    None
):
    """Payload normalisation should drop invalid and build active routes."""
    payload = types.ensure_gps_payload({
        "current_route": [],
        "active_route": {
            "id": "walk-1",
            "points": [{"latitude": 50, "longitude": 8}],
        },
        "status": None,
    })

    assert payload is not None
    assert "current_route" not in payload
    assert payload["active_route"]["id"] == "walk-1"
    assert payload["active_route"]["point_count"] == 1
    assert payload["status"] == "unknown"


def test_ensure_gps_payload_null_satellites_and_trimmed_last_seen() -> None:
    """Explicit satellite nulls and blank timestamps should normalize consistently."""
    payload = types.ensure_gps_payload({
        "satellites": None,
        "last_seen": "   ",
        "latitude": "48.1",
    })

    assert payload is not None
    assert payload["satellites"] is None
    assert payload["last_seen"] is None
    assert payload["latitude"] == 48.1


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


@pytest.mark.parametrize(
    ("value", "current", "fallback", "expected"),
    [
        pytest.param("FULL", None, "balanced", "full", id="explicit-value-normalized"),
        pytest.param("standard", None, "minimal", "balanced", id="alias-value"),
        pytest.param(None, " STANDARD ", "minimal", "balanced", id="alias-current"),
        pytest.param(object(), "unknown", "minimal", "minimal", id="fallback-default"),
    ],
)
def test_normalize_performance_mode_priority_and_aliases(
    value: object,
    current: str | None,
    fallback: types.PerformanceMode,
    expected: str,
) -> None:
    """Performance mode helper should normalize value/current before fallback."""
    assert (
        types.normalize_performance_mode(
            value,
            current=current,
            fallback=fallback,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("weight", "size", "expected"),
    [
        pytest.param(1.0, "toy", True, id="toy-min-boundary"),
        pytest.param(6.1, "toy", False, id="toy-out-of-range"),
        pytest.param(22.0, "large", True, id="large-min-boundary"),
        pytest.param(90.1, "giant", False, id="giant-out-of-range"),
        pytest.param(999.0, "unknown", True, id="unknown-size-accepted"),
    ],
)
def test_validate_dog_weight_for_size_ranges(
    weight: float,
    size: str,
    expected: bool,
) -> None:
    """Weight validation should enforce known ranges and ignore unknown sizes."""
    assert types.validate_dog_weight_for_size(weight, size) is expected


def test_cache_repair_aggregate_from_mapping_coerces_totals_and_collections() -> None:
    """Aggregate parsing should normalize totals and mixed collection payloads."""
    aggregate = types.CacheRepairAggregate.from_mapping({
        "total_caches": "7.0",
        "anomaly_count": True,
        "severity": "high",
        "generated_at": "2026-03-01T00:00:00+00:00",
        "caches_with_errors": ("cache_a", "cache_b", 1),
        "caches_with_override_flags": {"cache_c", "cache_d", 4},
        "totals": {
            "entries": "15.9",
            "hits": 8,
            "misses": False,
            "expired_entries": "bad",
            "active_override_flags": "3",
            "overall_hit_rate": "0.73",
        },
        "issues": [{"cache": "cache_a", "reason": "expired"}, "invalid"],
    })

    assert aggregate.total_caches == 7
    assert aggregate.anomaly_count == 1
    assert aggregate.caches_with_errors == ["cache_a", "cache_b"]
    assert sorted(aggregate.caches_with_override_flags or []) == [
        "cache_c",
        "cache_d",
    ]
    assert aggregate.totals is not None
    assert aggregate.totals.entries == 15
    assert aggregate.totals.misses == 0
    assert aggregate.totals.expired_entries == 0
    assert aggregate.totals.active_override_flags == 3
    assert aggregate.totals.overall_hit_rate == 0.73
    assert aggregate.issues == [{"cache": "cache_a", "reason": "expired"}]


def test_cache_repair_aggregate_to_mapping_omits_empty_optional_sections() -> None:
    """Mapping export should keep required fields and skip empty optional payloads."""
    aggregate = types.CacheRepairAggregate(
        total_caches=0,
        anomaly_count=0,
        severity="normal",
        generated_at="2026-03-01T00:00:00+00:00",
        caches_with_low_hit_rate=[],
        issues=[],
    )

    exported = aggregate.to_mapping()

    assert exported == {
        "total_caches": 0,
        "anomaly_count": 0,
        "severity": "normal",
        "generated_at": "2026-03-01T00:00:00+00:00",
    }


def test_ensure_dog_options_entry_prefers_payload_dog_id_and_normalizes_notifications(
) -> None:
    """Options entry should prefer payload dog_id and apply notification defaults."""
    entry = types.ensure_dog_options_entry(
        {
            types.DOG_ID_FIELD: "dog-in-payload",
            types.CONF_NOTIFICATIONS: {
                "quiet_hours": "off",
            },
            types.DOG_MODULES_FIELD: {
                "feeding": 1,
            },
        },
        dog_id="dog-from-arg",
    )

    assert entry["dog_id"] == "dog-in-payload"
    assert entry["notifications"][types.NOTIFICATION_QUIET_HOURS_FIELD] is False
    assert (
        entry["notifications"][types.NOTIFICATION_REMINDER_REPEAT_FIELD]
        == types.DEFAULT_REMINDER_REPEAT_MIN
    )
    assert entry["modules"]["feeding"] is True
