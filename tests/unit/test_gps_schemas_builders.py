"""Tests for GPS schema builder helpers."""

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
    GEOFENCE_LAT_FIELD,
    GEOFENCE_LON_FIELD,
    GEOFENCE_RADIUS_FIELD,
    GPS_ACCURACY_FILTER_FIELD,
    GPS_DISTANCE_FILTER_FIELD,
    GPS_ENABLED_FIELD,
    GPS_UPDATE_INTERVAL_FIELD,
    ROUTE_HISTORY_DAYS_FIELD,
    ROUTE_RECORDING_FIELD,
)


def _markers_by_name(schema: vol.Schema) -> dict[str, vol.Marker]:
    """Map schema marker names to their marker object."""
    return {str(marker.schema): marker for marker in schema.schema}


def test_build_dog_gps_schema_exposes_expected_defaults_and_select_options() -> None:
    """Dog GPS schema should include expected defaults and source options."""
    schema = build_dog_gps_schema({"tracker.main": "Main collar"})
    markers = _markers_by_name(schema)

    assert CONF_GPS_SOURCE in markers
    assert markers["gps_update_interval"].default() == DEFAULT_GPS_UPDATE_INTERVAL
    assert markers["gps_accuracy_filter"].default() == DEFAULT_GPS_ACCURACY_FILTER
    assert markers["enable_geofencing"].default() is True
    assert markers["home_zone_radius"].default() == 50

    gps_source_selector = schema.schema[markers[CONF_GPS_SOURCE]]
    assert gps_source_selector["select"]["mode"] == "dropdown"
    option_values = {
        opt["value"] if isinstance(opt, dict) else opt
        for opt in gps_source_selector["select"]["options"]
    }
    assert option_values >= {"tracker.main", "manual"}


def test_build_gps_settings_schema_prefers_current_options_and_has_fallbacks() -> None:
    """GPS settings schema should use submitted values and preserve defaults."""
    schema = build_gps_settings_schema(
        {
            GPS_ENABLED_FIELD: False,
            GPS_UPDATE_INTERVAL_FIELD: 180,
            GPS_ACCURACY_FILTER_FIELD: 35,
            GPS_DISTANCE_FILTER_FIELD: 21,
            ROUTE_RECORDING_FIELD: False,
            ROUTE_HISTORY_DAYS_FIELD: 7,
            AUTO_TRACK_WALKS_FIELD: False,
        },
    )
    markers = _markers_by_name(schema)

    assert markers[GPS_ENABLED_FIELD].default() is False
    assert markers[GPS_UPDATE_INTERVAL_FIELD].default() == 180
    assert markers[GPS_ACCURACY_FILTER_FIELD].default() == 35
    assert markers[GPS_DISTANCE_FILTER_FIELD].default() == 21
    assert markers[ROUTE_RECORDING_FIELD].default() is False
    assert markers[ROUTE_HISTORY_DAYS_FIELD].default() == 7
    assert markers[AUTO_TRACK_WALKS_FIELD].default() is False

    empty_schema = build_gps_settings_schema({})
    empty_markers = _markers_by_name(empty_schema)
    assert (
        empty_markers[GPS_UPDATE_INTERVAL_FIELD].default()
        == DEFAULT_GPS_UPDATE_INTERVAL
    )
    assert (
        empty_markers[GPS_ACCURACY_FILTER_FIELD].default()
        == DEFAULT_GPS_ACCURACY_FILTER
    )
    assert (
        empty_markers[GPS_DISTANCE_FILTER_FIELD].default()
        == DEFAULT_GPS_DISTANCE_FILTER
    )


def test_build_geofence_settings_schema_normalizes_radius_and_coordinates() -> None:
    """Geofence schema should normalize radius and default lat/lon fallback strings."""
    schema = build_geofence_settings_schema(
        {
            GEOFENCE_RADIUS_FIELD: 155.7,
            GEOFENCE_LAT_FIELD: None,
            GEOFENCE_LON_FIELD: "",
        },
    )
    markers = _markers_by_name(schema)

    assert markers[GEOFENCE_RADIUS_FIELD].default() == 155
    assert markers[GEOFENCE_LAT_FIELD].default() == "52.5200"
    assert markers[GEOFENCE_LON_FIELD].default() == "13.4050"

    non_numeric_radius_schema = build_geofence_settings_schema(
        {
            GEOFENCE_RADIUS_FIELD: "far",
            GEOFENCE_LAT_FIELD: "48.1000",
            GEOFENCE_LON_FIELD: "11.5800",
        },
    )
    non_numeric_markers = _markers_by_name(non_numeric_radius_schema)

    assert non_numeric_markers[GEOFENCE_RADIUS_FIELD].default() == 100
    assert non_numeric_markers[GEOFENCE_LAT_FIELD].default() == "48.1000"
    assert non_numeric_markers[GEOFENCE_LON_FIELD].default() == "11.5800"
