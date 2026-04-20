"""Coverage tests for GPS flow-step mixins."""

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol.const import (
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_SOURCE,
    CONF_GPS_UPDATE_INTERVAL,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
    MODULE_HEALTH,
)
from custom_components.pawcontrol.exceptions import ValidationError
import custom_components.pawcontrol.flow_steps.gps as gps_module
from custom_components.pawcontrol.flow_steps.gps import (
    DogGPSFlowMixin,
    GPSOptionsMixin,
    GPSOptionsNormalizerMixin,
    _validate_gps_accuracy,
    _validate_gps_update_interval,
)
from custom_components.pawcontrol.types import (
    AUTO_TRACK_WALKS_FIELD,
    DOG_GPS_CONFIG_FIELD,
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    DOG_OPTIONS_FIELD,
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
    GPS_SETTINGS_FIELD,
    GPS_UPDATE_INTERVAL_FIELD,
    ROUTE_HISTORY_DAYS_FIELD,
    ROUTE_RECORDING_FIELD,
)


class _DogGPSFlow(DogGPSFlowMixin):
    def __init__(self, current_dog: dict[str, Any] | None) -> None:
        self.hass = SimpleNamespace()
        self._current_dog_config = current_dog
        self._dogs: list[dict[str, Any]] = []

    def _get_available_device_trackers(self) -> dict[str, str]:
        return {"device_tracker.rex": "Rex Tracker"}

    def _get_available_person_entities(self) -> dict[str, str]:
        return {}

    async def async_step_add_dog(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"type": "add_dog", "data": user_input}

    async def async_step_dog_feeding(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"type": "dog_feeding", "data": user_input}

    async def async_step_dog_health(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"type": "dog_health", "data": user_input}

    async def async_step_add_another_dog(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"type": "add_another", "data": user_input}

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}


class _GPSOptionsFlow(GPSOptionsMixin, GPSOptionsNormalizerMixin):
    def __init__(
        self,
        *,
        options: dict[str, Any] | None = None,
        dog_options: dict[str, Any] | None = None,
        dogs: list[dict[str, Any]] | None = None,
        current_dog: dict[str, Any] | None = None,
    ) -> None:
        self._options = options or {}
        self._dog_options = dog_options or {}
        self._dogs = dogs or []
        self._current_dog = current_dog
        self.init_calls = 0

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._options)

    def _current_dog_options(self) -> dict[str, Any]:
        return self._dog_options

    def _current_options(self) -> dict[str, Any]:
        return self._options

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return options

    def _select_dog_by_id(self, dog_id: str | None) -> dict[str, Any] | None:
        self._current_dog = next(
            (
                dog
                for dog in self._dogs
                if isinstance(dog.get(DOG_ID_FIELD), str)
                and dog[DOG_ID_FIELD] == dog_id
            ),
            None,
        )
        return self._current_dog

    def _require_current_dog(self) -> dict[str, Any] | None:
        return self._current_dog

    def _build_dog_selector_schema(self) -> object:
        return object()

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        self._options = dict(data)
        dog_options = data.get(DOG_OPTIONS_FIELD)
        if isinstance(dog_options, dict):
            self._dog_options = dog_options
        return {"type": "create_entry", "title": title, "data": data}

    async def async_step_init(self) -> dict[str, Any]:
        self.init_calls += 1
        return {"type": "init"}


def _valid_dog_gps_input() -> dict[str, Any]:
    return {
        CONF_GPS_SOURCE: "manual",
        GPS_UPDATE_INTERVAL_FIELD: 60,
        GPS_ACCURACY_FILTER_FIELD: 10.0,
        "enable_geofencing": True,
        "home_zone_radius": 50.0,
    }


def _valid_options_gps_input() -> dict[str, Any]:
    return {
        GPS_ENABLED_FIELD: True,
        GPS_UPDATE_INTERVAL_FIELD: 60,
        GPS_ACCURACY_FILTER_FIELD: 12.0,
        GPS_DISTANCE_FILTER_FIELD: 30.0,
        ROUTE_RECORDING_FIELD: True,
        ROUTE_HISTORY_DAYS_FIELD: 7,
        AUTO_TRACK_WALKS_FIELD: True,
    }


def _valid_geofence_input() -> dict[str, Any]:
    return {
        GEOFENCE_ENABLED_FIELD: True,
        GEOFENCE_USE_HOME_FIELD: False,
        GEOFENCE_RADIUS_FIELD: 120.0,
        GEOFENCE_LAT_FIELD: 48.1371,
        GEOFENCE_LON_FIELD: 11.5754,
        GEOFENCE_ALERTS_FIELD: True,
        GEOFENCE_SAFE_ZONE_FIELD: True,
        GEOFENCE_RESTRICTED_ZONE_FIELD: False,
        GEOFENCE_ZONE_ENTRY_FIELD: True,
        GEOFENCE_ZONE_EXIT_FIELD: True,
    }


def test_required_gps_validators_raise_if_underlying_validator_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive required-value guards should raise ValidationError when validator returns None."""
    monkeypatch.setattr(gps_module, "validate_gps_interval", lambda *_, **__: None)
    with pytest.raises(ValidationError) as interval_error:
        _validate_gps_update_interval(
            30,
            field=GPS_UPDATE_INTERVAL_FIELD,
            minimum=5,
            maximum=600,
        )
    assert interval_error.value.constraint == "gps_update_interval_required"

    monkeypatch.setattr(
        gps_module.InputValidator,
        "validate_gps_accuracy",
        staticmethod(lambda *_, **__: None),
    )
    with pytest.raises(ValidationError) as accuracy_error:
        _validate_gps_accuracy(
            20.0,
            field=GPS_ACCURACY_FILTER_FIELD,
            minimum=5.0,
            maximum=500.0,
        )
    assert accuracy_error.value.constraint == "gps_accuracy_required"


@pytest.mark.asyncio
async def test_dog_gps_step_redirects_when_current_dog_missing() -> None:
    """Dog GPS step should restart add-dog flow if no active dog is set."""
    flow = _DogGPSFlow(current_dog=None)

    result = await flow.async_step_dog_gps()

    assert result["type"] == "add_dog"


@pytest.mark.asyncio
async def test_dog_gps_step_shows_form_without_input() -> None:
    """Dog GPS step should render its form when input is not provided."""
    flow = _DogGPSFlow(current_dog={DOG_NAME_FIELD: "Rex"})

    result = await flow.async_step_dog_gps()

    assert result["type"] == "form"
    assert result["step_id"] == "dog_gps"


@pytest.mark.parametrize(
    ("constraint", "expected_error"),
    [
        ("gps_source_unavailable", "gps_entity_unavailable"),
        ("gps_source_not_found", "gps_entity_not_found"),
        ("unexpected_constraint", "required"),
    ],
)
@pytest.mark.asyncio
async def test_dog_gps_maps_gps_source_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
    constraint: str,
    expected_error: str,
) -> None:
    """Dog GPS step should map source validation constraints to flow error keys."""
    flow = _DogGPSFlow(current_dog={DOG_NAME_FIELD: "Rex"})

    def _raise_source_error(*_args: Any, **_kwargs: Any) -> str:
        raise ValidationError(CONF_GPS_SOURCE, "broken", constraint)

    monkeypatch.setattr(gps_module, "validate_gps_source", _raise_source_error)

    result = await flow.async_step_dog_gps(_valid_dog_gps_input())

    assert result["type"] == "form"
    assert result["errors"][CONF_GPS_SOURCE] == expected_error


@pytest.mark.asyncio
async def test_dog_gps_logs_schema_issues_and_routes_to_health_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema warnings should be logged and health step should be chosen when enabled."""
    flow = _DogGPSFlow(current_dog={DOG_NAME_FIELD: "Rex"})

    monkeypatch.setattr(
        gps_module,
        "validate_json_schema_payload",
        lambda *_args, **_kwargs: [SimpleNamespace(constraint="schema_issue")],
    )
    monkeypatch.setattr(
        gps_module,
        "ensure_dog_modules_config",
        lambda _dog: {MODULE_HEALTH: True},
    )

    result = await flow.async_step_dog_gps(_valid_dog_gps_input())

    assert result["type"] == "dog_health"
    assert DOG_GPS_CONFIG_FIELD in flow._current_dog_config


def test_current_gps_options_handles_per_dog_mapping_and_numeric_legacy_values() -> (
    None
):
    """Per-dog raw GPS settings should merge numeric legacy values."""
    flow = _GPSOptionsFlow(
        options={
            CONF_GPS_UPDATE_INTERVAL: 45,
            CONF_GPS_ACCURACY_FILTER: 15,
            CONF_GPS_DISTANCE_FILTER: 25,
        },
        dog_options={DOG_NAME_FIELD: {GPS_SETTINGS_FIELD: {}}},
    )

    current = flow._current_gps_options(DOG_NAME_FIELD)

    assert current[GPS_UPDATE_INTERVAL_FIELD] == 45
    assert current[GPS_ACCURACY_FILTER_FIELD] == 15.0
    assert current[GPS_DISTANCE_FILTER_FIELD] == 25.0


def test_current_gps_options_converts_float_interval_from_legacy_settings() -> None:
    """Float legacy update intervals should be coerced to integers."""
    flow = _GPSOptionsFlow(
        options={CONF_GPS_UPDATE_INTERVAL: 42.9},
        dog_options={"dog-1": {GPS_SETTINGS_FIELD: {}}},
    )

    current = flow._current_gps_options("dog-1")

    assert current[GPS_UPDATE_INTERVAL_FIELD] == 42


def test_current_gps_options_ignores_invalid_legacy_string_values() -> None:
    """Invalid legacy string values should be ignored without raising."""
    flow = _GPSOptionsFlow(
        options={
            CONF_GPS_UPDATE_INTERVAL: "not-a-number",
            CONF_GPS_ACCURACY_FILTER: "bad",
            CONF_GPS_DISTANCE_FILTER: "bad",
        },
        dog_options={"dog-1": {GPS_SETTINGS_FIELD: {}}},
    )

    current = flow._current_gps_options("dog-1")

    assert current[GPS_UPDATE_INTERVAL_FIELD] == DEFAULT_GPS_UPDATE_INTERVAL
    assert current[GPS_ACCURACY_FILTER_FIELD] == float(DEFAULT_GPS_ACCURACY_FILTER)
    assert current[GPS_DISTANCE_FILTER_FIELD] == 30.0


def test_current_gps_options_skips_unsupported_legacy_value_types() -> None:
    """Unsupported legacy types should be ignored by fallback coercion paths."""
    flow = _GPSOptionsFlow(
        options={
            CONF_GPS_UPDATE_INTERVAL: {"bad": "type"},
            CONF_GPS_ACCURACY_FILTER: ["bad"],
            CONF_GPS_DISTANCE_FILTER: ("bad",),
        },
        dog_options={"dog-1": {GPS_SETTINGS_FIELD: {}}},
    )

    current = flow._current_gps_options("dog-1")

    assert current[GPS_UPDATE_INTERVAL_FIELD] == DEFAULT_GPS_UPDATE_INTERVAL
    assert current[GPS_ACCURACY_FILTER_FIELD] == float(DEFAULT_GPS_ACCURACY_FILTER)
    assert current[GPS_DISTANCE_FILTER_FIELD] == 30.0


def test_current_geofence_options_prefers_per_dog_then_legacy_then_empty() -> None:
    """Geofence option resolution should fall back from per-dog to legacy to empty mapping."""
    flow = _GPSOptionsFlow(
        options={},
        dog_options={"dog-1": {"geofence_settings": {"radius": 75}}},
    )
    assert flow._current_geofence_options("dog-1") == {"radius": 75}

    flow._dog_options = {"dog-1": {"geofence_settings": "invalid"}}
    flow._options = {"geofence_settings": {"radius": 90}}
    assert flow._current_geofence_options("dog-1") == {"radius": 90}

    flow._options = {"geofence_settings": "invalid"}
    assert flow._current_geofence_options("dog-1") == {}


@pytest.mark.asyncio
async def test_select_dog_for_gps_settings_covers_all_navigation_paths() -> None:
    """GPS dog selection should handle empty, invalid, valid and initial-form paths."""
    empty = _GPSOptionsFlow(dogs=[])
    assert await empty.async_step_select_dog_for_gps_settings() == {"type": "init"}
    assert empty.init_calls == 1

    flow = _GPSOptionsFlow(dogs=[{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Rex"}])
    form = await flow.async_step_select_dog_for_gps_settings()
    assert form["type"] == "form"
    assert form["step_id"] == "select_dog_for_gps_settings"

    missing = await flow.async_step_select_dog_for_gps_settings({"dog_id": "missing"})
    assert missing == {"type": "init"}

    selected = await flow.async_step_select_dog_for_gps_settings({"dog_id": "dog-1"})
    assert selected["type"] == "form"
    assert selected["step_id"] == "gps_settings"


@pytest.mark.asyncio
async def test_select_dog_for_geofence_settings_covers_all_navigation_paths() -> None:
    """Geofence dog selection should handle empty, invalid, valid and initial-form paths."""
    empty = _GPSOptionsFlow(dogs=[])
    assert await empty.async_step_select_dog_for_geofence_settings() == {"type": "init"}
    assert empty.init_calls == 1

    flow = _GPSOptionsFlow(dogs=[{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Rex"}])
    form = await flow.async_step_select_dog_for_geofence_settings()
    assert form["type"] == "form"
    assert form["step_id"] == "select_dog_for_geofence_settings"

    missing = await flow.async_step_select_dog_for_geofence_settings({
        "dog_id": "missing"
    })
    assert missing == {"type": "init"}

    selected = await flow.async_step_select_dog_for_geofence_settings({
        "dog_id": "dog-1"
    })
    assert selected["type"] == "form"
    assert selected["step_id"] == "geofence_settings"


@pytest.mark.asyncio
async def test_gps_settings_redirects_for_missing_or_invalid_current_dog() -> None:
    """GPS settings step should redirect when no valid current dog id exists."""
    flow = _GPSOptionsFlow(
        dogs=[{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Rex"}],
        current_dog=None,
    )
    missing = await flow.async_step_gps_settings(_valid_options_gps_input())
    assert missing["type"] == "form"
    assert missing["step_id"] == "select_dog_for_gps_settings"

    flow._current_dog = {DOG_ID_FIELD: 123}
    invalid = await flow.async_step_gps_settings(_valid_options_gps_input())
    assert invalid["type"] == "form"
    assert invalid["step_id"] == "select_dog_for_gps_settings"


@pytest.mark.asyncio
async def test_gps_settings_renders_form_when_input_is_missing() -> None:
    """GPS settings should render form for initial load."""
    flow = _GPSOptionsFlow(current_dog={DOG_ID_FIELD: "dog-1"})

    result = await flow.async_step_gps_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "gps_settings"


@pytest.mark.asyncio
async def test_gps_settings_validation_errors_return_form() -> None:
    """GPS settings should surface update interval, distance and route-history errors."""
    flow = _GPSOptionsFlow(current_dog={DOG_ID_FIELD: "dog-1"})

    result = await flow.async_step_gps_settings({
        GPS_ENABLED_FIELD: True,
        GPS_UPDATE_INTERVAL_FIELD: "bad",
        GPS_ACCURACY_FILTER_FIELD: 15.0,
        GPS_DISTANCE_FILTER_FIELD: "bad",
        ROUTE_RECORDING_FIELD: True,
        ROUTE_HISTORY_DAYS_FIELD: 0,
        AUTO_TRACK_WALKS_FIELD: True,
    })

    assert result["type"] == "form"
    assert GPS_UPDATE_INTERVAL_FIELD in result["errors"]
    assert result["errors"][GPS_DISTANCE_FILTER_FIELD] == "invalid_configuration"
    assert result["errors"][ROUTE_HISTORY_DAYS_FIELD] == "invalid_configuration"


@pytest.mark.asyncio
async def test_gps_settings_persists_per_dog_payload_and_logs_schema_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPS settings should persist under dog_options for explicit selections."""
    flow = _GPSOptionsFlow(
        current_dog={DOG_ID_FIELD: "dog-1"},
        dog_options={"dog-1": {DOG_ID_FIELD: "dog-1"}},
    )
    monkeypatch.setattr(
        gps_module,
        "validate_json_schema_payload",
        lambda *_args, **_kwargs: [SimpleNamespace(constraint="broken_schema")],
    )

    result = await flow.async_step_gps_settings(_valid_options_gps_input())

    assert result["type"] == "create_entry"
    data = result["data"]
    assert GPS_SETTINGS_FIELD in data
    assert DOG_OPTIONS_FIELD in data
    assert data[DOG_OPTIONS_FIELD]["dog-1"][DOG_ID_FIELD] == "dog-1"
    assert GPS_SETTINGS_FIELD in data[DOG_OPTIONS_FIELD]["dog-1"]


@pytest.mark.asyncio
async def test_gps_settings_skips_persist_when_explicit_dog_id_is_not_string() -> None:
    """GPS settings should skip per-dog persistence when explicit dog id is not a string."""
    flow = _GPSOptionsFlow(current_dog={DOG_ID_FIELD: 123}, dog_options={})
    flow._require_current_dog = lambda: {DOG_ID_FIELD: "dog-1"}  # type: ignore[method-assign]

    result = await flow.async_step_gps_settings(_valid_options_gps_input())

    assert result["type"] == "create_entry"
    assert DOG_OPTIONS_FIELD not in result["data"]


@pytest.mark.asyncio
async def test_geofence_settings_renders_form_when_input_is_missing() -> None:
    """Geofence settings should render form on initial call."""
    flow = _GPSOptionsFlow(current_dog={DOG_ID_FIELD: "dog-1"})

    result = await flow.async_step_geofence_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "geofence_settings"


@pytest.mark.asyncio
async def test_geofence_settings_rounds_radius_and_persists_selected_dog() -> None:
    """Geofence settings should round radius and persist per-dog payload for selected dog."""
    flow = _GPSOptionsFlow(
        current_dog={DOG_ID_FIELD: "dog-1"},
        dog_options={"dog-1": {DOG_ID_FIELD: "dog-1"}},
    )
    payload = _valid_geofence_input()
    payload[GEOFENCE_RADIUS_FIELD] = 123.4

    result = await flow.async_step_geofence_settings(payload)

    assert result["type"] == "create_entry"
    data = result["data"]
    assert data["geofence_settings"][GEOFENCE_RADIUS_FIELD] == 123
    assert (
        data[DOG_OPTIONS_FIELD]["dog-1"]["geofence_settings"][GEOFENCE_RADIUS_FIELD]
        == 123
    )
    assert data[DOG_OPTIONS_FIELD]["dog-1"][DOG_ID_FIELD] == "dog-1"


@pytest.mark.asyncio
async def test_geofence_settings_uses_legacy_path_when_explicit_id_is_not_string() -> (
    None
):
    """Geofence settings should use legacy storage path for non-string explicit IDs."""
    flow = _GPSOptionsFlow(
        current_dog={DOG_ID_FIELD: 42},
        options={"geofence_settings": {GEOFENCE_RADIUS_FIELD: 90}},
    )
    flow._require_current_dog = lambda: {DOG_ID_FIELD: "dog-1"}  # type: ignore[method-assign]

    result = await flow.async_step_geofence_settings(_valid_geofence_input())

    assert result["type"] == "create_entry"
    assert DOG_OPTIONS_FIELD not in result["data"]


@pytest.mark.asyncio
async def test_geofence_settings_handles_radius_validation_errors() -> None:
    """Geofence settings should return field errors for invalid radius input."""
    flow = _GPSOptionsFlow(current_dog={DOG_ID_FIELD: "dog-1"})
    payload = _valid_geofence_input()
    payload[GEOFENCE_RADIUS_FIELD] = "bad"

    result = await flow.async_step_geofence_settings(payload)

    assert result["type"] == "form"
    assert GEOFENCE_RADIUS_FIELD in result["errors"]


def test_normalise_gps_settings_uses_defaults_when_validators_raise_and_schema_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPS normaliser should fallback to defaults on validation and schema issues."""
    flow = _GPSOptionsFlow()

    monkeypatch.setattr(
        gps_module,
        "validate_float_range",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValidationError(GPS_DISTANCE_FILTER_FIELD, "bad", "not_numeric")
        ),
    )
    monkeypatch.setattr(
        gps_module,
        "validate_gps_interval",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValidationError(GPS_UPDATE_INTERVAL_FIELD, "bad", "not_numeric")
        ),
    )
    monkeypatch.setattr(
        gps_module,
        "validate_gps_accuracy_value",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValidationError(GPS_ACCURACY_FILTER_FIELD, "bad", "not_numeric")
        ),
    )
    monkeypatch.setattr(
        gps_module,
        "validate_json_schema_payload",
        lambda *_args, **_kwargs: [SimpleNamespace(constraint="invalid_schema")],
    )

    normalised = flow._normalise_gps_settings({
        GPS_ENABLED_FIELD: False,
        GPS_UPDATE_INTERVAL_FIELD: "bad",
        GPS_ACCURACY_FILTER_FIELD: "bad",
        GPS_DISTANCE_FILTER_FIELD: "bad",
        ROUTE_RECORDING_FIELD: False,
        ROUTE_HISTORY_DAYS_FIELD: "bad",
        AUTO_TRACK_WALKS_FIELD: False,
    })

    assert normalised[GPS_ENABLED_FIELD] is True
    assert normalised[GPS_UPDATE_INTERVAL_FIELD] == DEFAULT_GPS_UPDATE_INTERVAL
    assert normalised[GPS_ACCURACY_FILTER_FIELD] == float(DEFAULT_GPS_ACCURACY_FILTER)
    assert normalised[GPS_DISTANCE_FILTER_FIELD] == float(DEFAULT_GPS_DISTANCE_FILTER)
    assert normalised[ROUTE_RECORDING_FIELD] is True
    assert normalised[ROUTE_HISTORY_DAYS_FIELD] == 30
    assert normalised[AUTO_TRACK_WALKS_FIELD] is True


def test_normalise_gps_options_snapshot_updates_dog_ids_and_gps_settings() -> None:
    """GPS snapshot normaliser should coerce per-dog IDs and normalise per-dog GPS payloads."""
    flow = _GPSOptionsFlow()
    mutable: dict[str, Any] = {
        DOG_OPTIONS_FIELD: {
            "42": {
                DOG_ID_FIELD: "legacy-id",
                GPS_SETTINGS_FIELD: {
                    GPS_ENABLED_FIELD: True,
                    GPS_UPDATE_INTERVAL_FIELD: 60,
                    GPS_ACCURACY_FILTER_FIELD: 10.0,
                    GPS_DISTANCE_FILTER_FIELD: 20.0,
                    ROUTE_RECORDING_FIELD: True,
                    ROUTE_HISTORY_DAYS_FIELD: 7,
                    AUTO_TRACK_WALKS_FIELD: True,
                },
            }
        }
    }

    gps_settings = flow._normalise_gps_options_snapshot(mutable)

    assert gps_settings is not None
    dog_entry = mutable[DOG_OPTIONS_FIELD]["42"]
    assert dog_entry[DOG_ID_FIELD] == "42"
    assert isinstance(dog_entry[GPS_SETTINGS_FIELD], dict)


def test_normalise_gps_options_snapshot_handles_non_mapping_payloads() -> None:
    """Snapshot normaliser should safely handle non-mapping dog and GPS payloads."""
    flow = _GPSOptionsFlow()
    mutable: dict[str, Any] = {
        DOG_OPTIONS_FIELD: ["invalid"],
        GPS_SETTINGS_FIELD: "invalid",
    }

    result = flow._normalise_gps_options_snapshot(mutable)

    assert result is None
    assert mutable[DOG_OPTIONS_FIELD] == {}
