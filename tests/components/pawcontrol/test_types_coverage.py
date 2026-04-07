"""Coverage tests for defensive type-normalisation helpers."""

from custom_components.pawcontrol import types


def test_ensure_dog_config_data_rejects_missing_required_fields() -> None:
    """Dog config helper should return ``None`` when required strings are invalid."""
    assert types.ensure_dog_config_data({types.DOG_ID_FIELD: "", types.DOG_NAME_FIELD: "Buddy"}) is None
    assert types.ensure_dog_config_data({types.DOG_ID_FIELD: "dog-1", types.DOG_NAME_FIELD: 7}) is None


def test_ensure_notification_options_uses_defaults_and_ignores_invalid_overrides() -> None:
    """Notification options should keep default booleans when override types are invalid."""
    normalised = types.ensure_notification_options(
        {
            "quiet_hours": object(),
            "priority_notifications": "off",
            "reminder_repeat_min": "bad-int",
        },
        defaults={
            "quiet_hours": True,
            "reminder_repeat_min": 22,
            "priority_notifications": True,
        },
    )

    assert normalised[types.NOTIFICATION_QUIET_HOURS_FIELD] is True
    assert normalised[types.NOTIFICATION_REMINDER_REPEAT_FIELD] == 22
    assert normalised[types.NOTIFICATION_PRIORITY_FIELD] is False


def test_ensure_gps_payload_returns_none_and_handles_satellite_type_errors() -> None:
    """GPS payload helper should return ``None`` for invalid payloads and bad satellites."""
    assert types.ensure_gps_payload(None) is None
    assert types.ensure_gps_payload("not-a-mapping") is None

    payload = types.ensure_gps_payload({"satellites": object(), "latitude": "1.5"})

    assert payload is not None
    assert payload["satellites"] is None
    assert payload["latitude"] == 1.5


def test_cache_diagnostics_snapshot_from_mapping_discards_invalid_repair_summary() -> None:
    """Snapshot factory should ignore malformed repair summaries instead of raising."""
    snapshot = types.CacheDiagnosticsSnapshot.from_mapping(
        {
            "stats": {"hits": 1},
            "diagnostics": {"cache": "ok"},
            "snapshot": {"state": "fresh"},
            "error": 42,
            "repair_summary": {"repair_rate": "not-a-number"},
        }
    )

    assert snapshot.stats == {"hits": 1}
    assert snapshot.diagnostics == {"cache": "ok"}
    assert snapshot.snapshot == {"state": "fresh"}
    assert snapshot.error is None
    assert snapshot.repair_summary is not None
    assert snapshot.repair_summary.severity == "unknown"


def test_daily_stats_from_dict_coerces_numbers_and_defaults_invalid_strings() -> None:
    """Daily stats parser should coerce bools/numbers and fall back on bad strings."""
    parsed = types.DailyStats.from_dict(
        {
            "date": "not-a-date",
            "feedings_count": True,
            "walks_count": " 2.0 ",
            "total_food_amount": False,
            "total_walk_distance": "bad-float",
        }
    )

    assert parsed.feedings_count == 1
    assert parsed.walks_count == 2
    assert parsed.total_food_amount == 0.0
    assert parsed.total_walk_distance == 0.0
