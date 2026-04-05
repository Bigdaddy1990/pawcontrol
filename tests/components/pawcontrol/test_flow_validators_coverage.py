"""Coverage tests for flow validator wrapper helpers."""

from custom_components.pawcontrol import flow_validators


def test_flow_validator_wrappers_delegate_to_validation_backends(monkeypatch) -> None:
    """Each wrapper should call the matching validation backend with kwargs."""
    recorded: dict[str, tuple[tuple, dict]] = {}

    def _stub(name: str, result):
        def _inner(*args, **kwargs):
            recorded[name] = (args, kwargs)
            return result

        return _inner

    monkeypatch.setattr(
        flow_validators,
        "validate_dog_name",
        _stub("dog_name", "Luna"),
    )
    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_gps_coordinates",
        _stub("gps_coordinates", (51.5, -0.1)),
    )
    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_gps_accuracy",
        _stub("gps_accuracy", 7.5),
    )
    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_geofence_radius",
        _stub("geofence_radius", 120.0),
    )
    monkeypatch.setattr(
        flow_validators,
        "validate_gps_interval",
        _stub("gps_interval", 15),
    )
    monkeypatch.setattr(
        flow_validators,
        "validate_interval",
        _stub("timer_interval", 30),
    )
    monkeypatch.setattr(
        flow_validators,
        "validate_time_window",
        _stub("time_window", ("08:00", "18:00")),
    )

    assert flow_validators.validate_flow_dog_name(" Luna ", required=False) == "Luna"
    assert flow_validators.validate_flow_gps_coordinates(
        "51.5",
        "-0.1",
        latitude_field="lat",
        longitude_field="lon",
    ) == (51.5, -0.1)
    assert (
        flow_validators.validate_flow_gps_accuracy(
            "7.5",
            field="accuracy",
            min_value=1,
            max_value=50,
            required=False,
        )
        == 7.5
    )
    assert (
        flow_validators.validate_flow_geofence_radius(
            "120",
            field="radius",
            min_value=10,
            max_value=300,
        )
        == 120.0
    )
    assert (
        flow_validators.validate_flow_gps_interval(
            "15",
            field="gps_update_interval",
            minimum=5,
            maximum=60,
            default=10,
            clamp=True,
            required=True,
        )
        == 15
    )
    assert (
        flow_validators.validate_flow_timer_interval(
            "30",
            field="timer_interval",
            minimum=10,
            maximum=120,
            default=20,
        )
        == 30
    )
    assert flow_validators.validate_flow_time_window(
        "08:00",
        "18:00",
        start_field="start",
        end_field="end",
        default_start="07:00",
        default_end="19:00",
    ) == ("08:00", "18:00")

    assert recorded["dog_name"][0] == (" Luna ",)
    assert recorded["dog_name"][1] == {
        "field": flow_validators.CONF_DOG_NAME,
        "required": False,
    }
    assert recorded["gps_coordinates"][0] == ("51.5", "-0.1")
    assert recorded["gps_coordinates"][1] == {
        "latitude_field": "lat",
        "longitude_field": "lon",
    }
    assert recorded["gps_accuracy"][1] == {
        "field": "accuracy",
        "min_value": 1,
        "max_value": 50,
        "required": False,
    }
    assert recorded["geofence_radius"][1] == {
        "field": "radius",
        "min_value": 10,
        "max_value": 300,
        "required": True,
    }
    assert recorded["gps_interval"][1] == {
        "field": "gps_update_interval",
        "minimum": 5,
        "maximum": 60,
        "default": 10,
        "clamp": True,
        "required": True,
    }
    assert recorded["timer_interval"][1] == {
        "field": "timer_interval",
        "minimum": 10,
        "maximum": 120,
        "default": 20,
        "clamp": False,
        "required": False,
    }
    assert recorded["time_window"][1] == {
        "start_field": "start",
        "end_field": "end",
        "default_start": "07:00",
        "default_end": "19:00",
    }


def test_module_exports_include_validation_error() -> None:
    """The module should re-export ValidationError for flow modules."""
    assert "ValidationError" in flow_validators.__all__
    assert flow_validators.ValidationError.__name__ == "ValidationError"
