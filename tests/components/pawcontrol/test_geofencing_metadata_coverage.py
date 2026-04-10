"""Coverage tests for geofencing metadata sanitization and serialization."""

from datetime import UTC, datetime, timezone

from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol.geofencing import (
    GeofenceType,
    GeofenceZone,
    _sanitize_zone_metadata,
)


def test_sanitize_zone_metadata_returns_empty_mapping_for_none() -> None:
    """None metadata should normalize to an empty typed mapping."""
    assert _sanitize_zone_metadata(None) == {}


def test_sanitize_zone_metadata_filters_invalid_and_converts_tags() -> None:
    """Only supported metadata keys and value types should survive sanitization."""
    metadata = {
        "auto_created": True,
        "color": "blue",
        "created_by": None,
        "notes": "safe zone",
        "tags": {"a": "park", "b": 5},
        "ignored": "value",
    }

    assert _sanitize_zone_metadata(metadata) == {
        "auto_created": True,
        "color": "blue",
        "created_by": None,
        "notes": "safe zone",
        "tags": ["park"],
    }


@pytest.mark.parametrize(
    ("tags_value", "expected"),
    [
        pytest.param("garden", ["garden"], id="string-tag"),
        pytest.param(("yard", 1, "home"), ["yard", "home"], id="iterable-tags"),
        pytest.param([], None, id="empty-tags-removed"),
    ],
)
def test_sanitize_zone_metadata_tag_variants(
    tags_value: object,
    expected: list[str] | None,
) -> None:
    """Tags should be normalized across accepted and rejected input shapes."""
    result = _sanitize_zone_metadata({"tags": tags_value})

    if expected is None:
        assert "tags" not in result
    else:
        assert result["tags"] == expected


def test_geofence_zone_to_storage_payload_copies_tags_list() -> None:
    """Serializing a zone should not expose mutable metadata lists by reference."""
    zone = GeofenceZone(
        id="zone-1",
        name="Backyard",
        type=GeofenceType.SAFE_ZONE,
        latitude=52.5,
        longitude=13.4,
        radius=100,
        metadata={"tags": ["home"]},
    )

    payload = zone.to_storage_payload()
    assert payload["metadata"]["tags"] == ["home"]

    payload["metadata"]["tags"].append("new")
    assert zone.metadata["tags"] == ["home"]


def test_geofence_zone_from_storage_payload_uses_fallback_timestamps() -> None:
    """Invalid persisted timestamps should gracefully fall back to utcnow values."""
    frozen_now = datetime(2026, 4, 10, tzinfo=UTC)
    data = {
        "id": "zone-2",
        "name": "Vet",
        "type": "point_of_interest",
        "latitude": 40.0,
        "longitude": -73.0,
        "radius": 120,
        "created_at": "invalid",
        "updated_at": "invalid",
        "metadata": "not-a-mapping",
    }

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(dt_util, "utcnow", lambda: frozen_now)
        zone = GeofenceZone.from_storage_payload(data)

    assert zone.created_at == frozen_now
    assert zone.updated_at == frozen_now
    assert zone.metadata == {}


def test_geofence_zone_from_storage_payload_parses_valid_timestamps() -> None:
    """Valid persisted timestamps should be parsed and used directly."""
    created = "2025-03-01T12:00:00+00:00"
    updated = "2025-03-02T12:00:00+00:00"

    zone = GeofenceZone.from_storage_payload({
        "id": "zone-3",
        "name": "Office",
        "type": "restricted_area",
        "latitude": 41.0,
        "longitude": -72.0,
        "radius": 200,
        "created_at": created,
        "updated_at": updated,
        "metadata": {"color": "red"},
    })

    assert zone.created_at == dt_util.parse_datetime(created)
    assert zone.updated_at == dt_util.parse_datetime(updated)
    assert zone.metadata == {"color": "red"}
