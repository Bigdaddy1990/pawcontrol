"""Tests for GPS flow schema builders."""

import voluptuous as vol

from custom_components.pawcontrol.const import (
    CONF_GPS_SOURCE,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
)
from custom_components.pawcontrol.flow_steps.gps_schemas import (
    build_dog_gps_schema,
    build_geofence_settings_schema,
    build_gps_settings_schema,
)
from custom_components.pawcontrol.types import (
    AUTO_TRACK_WALKS_FIELD,
    GEOFENCE_ALERTS_FIELD,
    GEOFENCE_ENABLED_FIELD,
    GEOFENCE_LAT_FIELD,
    GEOFENCE_LON_FIELD,
    GEOFENCE_RADIUS_FIELD,
    GEOFENCE_RESTRICTED_ZONE_FIELD,
    GEOFENCE_SAFE_ZONE_FIELD,
    GEOFENCE_USE_HOME_FIELD,
    GEOFENCE_ZONE_ENTRY_FIELD,
    GEOFENCE_ZONE_EXIT_FIELD,
    GPS_ACCURACY_FILTER_FIELD,
    GPS_DISTANCE_FILTER_FIELD,
    GPS_ENABLED_FIELD,
    GPS_UPDATE_INTERVAL_FIELD,
    ROUTE_HISTORY_DAYS_FIELD,
    ROUTE_RECORDING_FIELD,
)


def _marker_defaults(schema: vol.Schema) -> dict[str, object]:
    """Return default values keyed by schema marker names."""
    defaults: dict[str, object] = {}
    for key in schema.schema:
        if not isinstance(key, vol.Marker):
            continue
        default = key.default
        if default is vol.UNDEFINED:
            continue
        defaults[str(key.schema)] = default() if callable(default) else default
    return defaults


def _marker_validator(schema: vol.Schema, marker_name: str) -> object:
    """Return the validator mapped to ``marker_name`` from a schema."""
    for key, value in schema.schema.items():
        if isinstance(key, vol.Marker) and str(key.schema) == marker_name:
            return value
    raise AssertionError(f"Marker {marker_name} not found")


def test_build_dog_gps_schema_includes_push_defaults_and_required_fields() -> None:
    """Dog GPS schema should expose source and baseline GPS defaults."""
    schema = build_dog_gps_schema({"ha_tracker": "Home Assistant Tracker"})
    defaults = _marker_defaults(schema)
    source_selector = _marker_validator(schema, CONF_GPS_SOURCE)

    assert isinstance(source_selector, dict)
    assert source_selector["select"]["options"] == {
        "ha_tracker": "Home Assistant Tracker",
        "webhook": "Webhook (Push)",
        "mqtt": "MQTT (Push)",
        "manual": "Manual Location Entry",
    }

    assert defaults["gps_update_interval"] == DEFAULT_GPS_UPDATE_INTERVAL
    assert defaults["gps_accuracy_filter"] == DEFAULT_GPS_ACCURACY_FILTER


def test_build_gps_settings_schema_uses_fallback_defaults_for_missing_options() -> None:
    """GPS settings schema should fallback to documented defaults."""
    defaults = _marker_defaults(build_gps_settings_schema({}))

    assert defaults[GPS_ENABLED_FIELD] is True
    assert defaults[GPS_UPDATE_INTERVAL_FIELD] == DEFAULT_GPS_UPDATE_INTERVAL
    assert defaults[GPS_ACCURACY_FILTER_FIELD] == DEFAULT_GPS_ACCURACY_FILTER
    assert defaults[GPS_DISTANCE_FILTER_FIELD] == DEFAULT_GPS_DISTANCE_FILTER
    assert defaults[ROUTE_RECORDING_FIELD] is True
    assert defaults[ROUTE_HISTORY_DAYS_FIELD] == 30
    assert defaults[AUTO_TRACK_WALKS_FIELD] is True


def test_build_gps_settings_schema_prefers_existing_option_values() -> None:
    """GPS settings schema should preserve explicit option values."""
    defaults = _marker_defaults(
        build_gps_settings_schema({
            GPS_ENABLED_FIELD: False,
            GPS_UPDATE_INTERVAL_FIELD: 45,
            GPS_ACCURACY_FILTER_FIELD: 12,
            GPS_DISTANCE_FILTER_FIELD: 250,
            ROUTE_RECORDING_FIELD: False,
            ROUTE_HISTORY_DAYS_FIELD: 14,
            AUTO_TRACK_WALKS_FIELD: False,
        })
    )

    assert defaults[GPS_ENABLED_FIELD] is False
    assert defaults[GPS_UPDATE_INTERVAL_FIELD] == 45
    assert defaults[GPS_ACCURACY_FILTER_FIELD] == 12
    assert defaults[GPS_DISTANCE_FILTER_FIELD] == 250
    assert defaults[ROUTE_RECORDING_FIELD] is False
    assert defaults[ROUTE_HISTORY_DAYS_FIELD] == 14
    assert defaults[AUTO_TRACK_WALKS_FIELD] is False


def test_build_geofence_settings_schema_normalizes_radius_and_coordinates() -> None:
    """Geofence schema should coerce coordinate/radius defaults when invalid."""
    defaults = _marker_defaults(
        build_geofence_settings_schema({
            GEOFENCE_RADIUS_FIELD: "not-a-number",
            GEOFENCE_LAT_FIELD: "",
            GEOFENCE_LON_FIELD: "",
        })
    )

    assert defaults[GEOFENCE_RADIUS_FIELD] == 100
    assert defaults[GEOFENCE_LAT_FIELD] == "52.5200"
    assert defaults[GEOFENCE_LON_FIELD] == "13.4050"

    numeric_defaults = _marker_defaults(
        build_geofence_settings_schema({GEOFENCE_RADIUS_FIELD: 150.5})
    )
    assert numeric_defaults[GEOFENCE_RADIUS_FIELD] == 150


def test_build_geofence_settings_schema_prefers_explicit_settings() -> None:
    """Geofence schema should keep all explicitly configured values."""
    defaults = _marker_defaults(
        build_geofence_settings_schema({
            GEOFENCE_ENABLED_FIELD: False,
            GEOFENCE_USE_HOME_FIELD: False,
            GEOFENCE_RADIUS_FIELD: 180,
            GEOFENCE_LAT_FIELD: "48.137",
            GEOFENCE_LON_FIELD: "11.576",
            GEOFENCE_ALERTS_FIELD: False,
            GEOFENCE_SAFE_ZONE_FIELD: False,
            GEOFENCE_RESTRICTED_ZONE_FIELD: False,
            GEOFENCE_ZONE_ENTRY_FIELD: False,
            GEOFENCE_ZONE_EXIT_FIELD: False,
        })
    )

    assert defaults[GEOFENCE_ENABLED_FIELD] is False
    assert defaults[GEOFENCE_USE_HOME_FIELD] is False
    assert defaults[GEOFENCE_RADIUS_FIELD] == 180
    assert defaults[GEOFENCE_LAT_FIELD] == "48.137"
    assert defaults[GEOFENCE_LON_FIELD] == "11.576"
    assert defaults[GEOFENCE_ALERTS_FIELD] is False
    assert defaults[GEOFENCE_SAFE_ZONE_FIELD] is False
    assert defaults[GEOFENCE_RESTRICTED_ZONE_FIELD] is False
    assert defaults[GEOFENCE_ZONE_ENTRY_FIELD] is False
    assert defaults[GEOFENCE_ZONE_EXIT_FIELD] is False
