"""JSON schemas and validators for PawControl configuration payloads."""

from dataclasses import dataclass
from numbers import Real
from typing import Any, Final

from .const import (
    CONF_AUTO_TRACK_WALKS,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_ENABLED,
    CONF_GPS_SOURCE,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_HOME_ZONE_RADIUS,
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC,
    CONF_PUSH_NONCE_TTL_SECONDS,
    CONF_PUSH_PAYLOAD_MAX_BYTES,
    CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
    CONF_ROUTE_HISTORY_DAYS,
    CONF_ROUTE_RECORDING,
    CONF_WEBHOOK_ENABLED,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_REQUIRE_SIGNATURE,
    CONF_WEBHOOK_SECRET,
)
from .types import (
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
)
from .validation import (
    MAX_GEOFENCE_RADIUS,
    MAX_LATITUDE,
    MAX_LONGITUDE,
    MIN_GEOFENCE_RADIUS,
    MIN_LATITUDE,
    MIN_LONGITUDE,
)


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    """Describe a JSON schema validation issue."""  # noqa: E111

    field: str  # noqa: E111
    value: Any  # noqa: E111
    constraint: str  # noqa: E111


GPS_DOG_CONFIG_JSON_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [CONF_GPS_SOURCE],
    "properties": {
        CONF_GPS_SOURCE: {"type": "string", "minLength": 1},
        CONF_GPS_UPDATE_INTERVAL: {"type": "integer", "minimum": 5, "maximum": 600},
        CONF_GPS_ACCURACY_FILTER: {"type": "number", "minimum": 5, "maximum": 500},
        "enable_geofencing": {"type": "boolean"},
        CONF_HOME_ZONE_RADIUS: {"type": "number", "minimum": 10, "maximum": 500},
    },
}

GPS_OPTIONS_JSON_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        CONF_GPS_ENABLED: {"type": "boolean"},
        CONF_GPS_SOURCE: {
            "type": "string",
            "enum": [
                "manual",
                "device_tracker",
                "person_entity",
                "smartphone",
                "tractive",
                "webhook",
                "mqtt",
            ],
        },
        CONF_WEBHOOK_ENABLED: {"type": "boolean"},
        CONF_WEBHOOK_REQUIRE_SIGNATURE: {"type": "boolean"},
        CONF_WEBHOOK_ID: {"type": "string"},
        CONF_WEBHOOK_SECRET: {"type": "string"},
        CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: {
            "type": "integer",
            "minimum": 1,
            "maximum": 6000,
        },
        CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE: {
            "type": "integer",
            "minimum": 1,
            "maximum": 6000,
        },
        CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE: {
            "type": "integer",
            "minimum": 1,
            "maximum": 6000,
        },
        CONF_PUSH_PAYLOAD_MAX_BYTES: {
            "type": "integer",
            "minimum": 1024,
            "maximum": 262144,
        },
        CONF_PUSH_NONCE_TTL_SECONDS: {
            "type": "integer",
            "minimum": 0,
            "maximum": 86400,
        },
        CONF_MQTT_ENABLED: {"type": "boolean"},
        CONF_MQTT_TOPIC: {"type": "string", "minLength": 1, "maxLength": 256},
        CONF_GPS_UPDATE_INTERVAL: {"type": "integer", "minimum": 5, "maximum": 600},
        CONF_GPS_ACCURACY_FILTER: {"type": "number", "minimum": 5, "maximum": 500},
        CONF_GPS_DISTANCE_FILTER: {"type": "number", "minimum": 1, "maximum": 2000},
        CONF_ROUTE_RECORDING: {"type": "boolean"},
        CONF_ROUTE_HISTORY_DAYS: {"type": "integer", "minimum": 1, "maximum": 365},
        CONF_AUTO_TRACK_WALKS: {"type": "boolean"},
    },
}

GEOFENCE_OPTIONS_JSON_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        GEOFENCE_ENABLED_FIELD: {"type": "boolean"},
        GEOFENCE_USE_HOME_FIELD: {"type": "boolean"},
        GEOFENCE_LAT_FIELD: {
            "type": ["number", "null"],
            "minimum": MIN_LATITUDE,
            "maximum": MAX_LATITUDE,
        },
        GEOFENCE_LON_FIELD: {
            "type": ["number", "null"],
            "minimum": MIN_LONGITUDE,
            "maximum": MAX_LONGITUDE,
        },
        GEOFENCE_RADIUS_FIELD: {
            "type": "integer",
            "minimum": int(MIN_GEOFENCE_RADIUS),
            "maximum": int(MAX_GEOFENCE_RADIUS),
        },
        GEOFENCE_ALERTS_FIELD: {"type": "boolean"},
        GEOFENCE_SAFE_ZONE_FIELD: {"type": "boolean"},
        GEOFENCE_RESTRICTED_ZONE_FIELD: {"type": "boolean"},
        GEOFENCE_ZONE_ENTRY_FIELD: {"type": "boolean"},
        GEOFENCE_ZONE_EXIT_FIELD: {"type": "boolean"},
    },
}


def validate_json_schema_payload(
    payload: Any,
    schema: dict[str, Any],
) -> list[SchemaViolation]:
    """Validate a payload against a JSON schema subset."""  # noqa: E111

    if not isinstance(payload, dict):  # noqa: E111
        return [SchemaViolation(field="payload", value=payload, constraint="type")]

    violations: list[SchemaViolation] = []  # noqa: E111
    properties = schema.get("properties", {})  # noqa: E111
    required = set(schema.get("required", []))  # noqa: E111
    additional_allowed = schema.get("additionalProperties", True)  # noqa: E111

    for key in required:  # noqa: E111
        if key not in payload:
            violations.append(  # noqa: E111
                SchemaViolation(field=key, value=None, constraint="required"),
            )

    for key, value in payload.items():  # noqa: E111
        if key not in properties:
            if not additional_allowed:  # noqa: E111
                violations.append(
                    SchemaViolation(field=key, value=value, constraint="additional"),
                )
            continue  # noqa: E111
        violations.extend(_validate_schema_property(key, value, properties[key]))

    return violations  # noqa: E111


def _validate_schema_property(
    key: str,
    value: Any,
    schema: dict[str, Any],
) -> list[SchemaViolation]:
    violations: list[SchemaViolation] = []  # noqa: E111
    expected_type = schema.get("type")  # noqa: E111
    if expected_type is not None and not _matches_type(value, expected_type):  # noqa: E111
        violations.append(
            SchemaViolation(field=key, value=value, constraint="type"),
        )
        return violations

    if "enum" in schema and value not in schema["enum"]:  # noqa: E111
        violations.append(SchemaViolation(field=key, value=value, constraint="enum"))
        return violations

    if isinstance(value, str):  # noqa: E111
        min_length = schema.get("minLength")
        if min_length is not None and len(value) < min_length:
            violations.append(  # noqa: E111
                SchemaViolation(field=key, value=value, constraint="minLength"),
            )
        max_length = schema.get("maxLength")
        if max_length is not None and len(value) > max_length:
            violations.append(  # noqa: E111
                SchemaViolation(field=key, value=value, constraint="maxLength"),
            )

    if _is_number(value):  # noqa: E111
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            violations.append(  # noqa: E111
                SchemaViolation(field=key, value=value, constraint="minimum"),
            )
        maximum = schema.get("maximum")
        if maximum is not None and value > maximum:
            violations.append(  # noqa: E111
                SchemaViolation(field=key, value=value, constraint="maximum"),
            )

    if _is_integer(value):  # noqa: E111
        multiple_of = schema.get("multipleOf")
        if multiple_of is not None and value % multiple_of != 0:
            violations.append(  # noqa: E111
                SchemaViolation(field=key, value=value, constraint="multipleOf"),
            )

    return violations  # noqa: E111


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):  # noqa: E111
        return any(_matches_type(value, entry) for entry in expected)
    if expected == "number":  # noqa: E111
        return _is_number(value)
    if expected == "integer":  # noqa: E111
        return _is_integer(value)
    if expected == "string":  # noqa: E111
        return isinstance(value, str)
    if expected == "boolean":  # noqa: E111
        return isinstance(value, bool)
    if expected == "null":  # noqa: E111
        return value is None
    return False  # noqa: E111


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)  # noqa: E111


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)  # noqa: E111
