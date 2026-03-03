"""Unit tests for service helper utilities."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context
import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.exceptions import (
    ServiceValidationError,
    ValidationError,
)
from custom_components.pawcontrol.service_guard import ServiceGuardResult
from custom_components.pawcontrol.services import (
    _build_error_details,
    _capture_cache_diagnostics,
    _coerce_service_bool,
    _coerce_service_details_value,
    _coordinator_resolver,
    _CoordinatorResolver,
    _extract_service_context,
    _format_expires_in_hours_error,
    _format_gps_validation_error,
    _format_text_validation_error,
    _merge_service_context_metadata,
    _normalise_context_identifier,
    _normalise_service_details,
    _record_delivery_failure_reason,
    _record_service_result,
    _service_validation_error,
)


def test_service_validation_error_requires_text() -> None:
    """Validation helper should enforce a non-empty message."""
    with pytest.raises(AssertionError):
        _service_validation_error("   ")

    error = _service_validation_error(" bad request ")
    assert isinstance(error, ServiceValidationError)
    assert str(error) == "bad request"


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("gps_update_interval_required", "gps_update_interval is required"),
        ("gps_accuracy_required", "gps_update_interval is required"),
        ("geofence_radius_required", "gps_update_interval is required"),
        (
            "gps_update_interval_not_numeric",
            "gps_update_interval must be a whole number",
        ),
        ("gps_accuracy_not_numeric", "gps_update_interval must be a number"),
        ("geofence_radius_not_numeric", "gps_update_interval must be a number"),
    ],
)
def test_format_gps_validation_error_simple_branches(
    constraint: str,
    expected: str,
) -> None:
    """GPS validation formatter should map known constraints to stable messages."""
    error = ValidationError("gps_update_interval", constraint=constraint)
    assert _format_gps_validation_error(error) == expected


def test_format_gps_validation_error_ranges_and_fallbacks() -> None:
    """Range and fallback branches should include field-specific wording."""
    range_error = ValidationError(
        "gps_accuracy",
        constraint="gps_accuracy_out_of_range",
        min_value=1,
        max_value=10,
    )
    assert _format_gps_validation_error(range_error, unit="m") == (
        "gps_accuracy must be between 1 and 10m"
    )

    interval_error = ValidationError("gps_update_interval", constraint="unknown")
    assert (
        _format_gps_validation_error(interval_error)
        == "gps_update_interval must be a whole number"
    )

    radius_error = ValidationError("geofence_radius", constraint="unknown")
    assert (
        _format_gps_validation_error(radius_error) == "geofence_radius must be a number"
    )

    other_error = ValidationError("anything_else", constraint="unknown")
    assert _format_gps_validation_error(other_error) == "anything_else is invalid"


def test_format_text_validation_error_branches() -> None:
    """Text validation formatter should cover required/string/empty/fallback paths."""
    required = ValidationError("field", constraint="something_required")
    assert _format_text_validation_error(required) == "field is required"

    as_text = ValidationError("field", constraint="Must be text")
    assert _format_text_validation_error(as_text) == "field must be a string"

    non_empty = ValidationError("field", constraint="Cannot be empty or whitespace")
    assert (
        _format_text_validation_error(non_empty) == "field must be a non-empty string"
    )

    generic = ValidationError("field", constraint="other")
    assert _format_text_validation_error(generic) == "field is invalid"


@pytest.mark.parametrize("value", [True, "true", "Enabled", "1", 1, " yes ", "on"])
def test_coerce_service_bool_truthy(value: object) -> None:
    """Truthy service values should map to True."""
    assert _coerce_service_bool(value, field="enabled") is True


@pytest.mark.parametrize("value", [False, "false", "Disabled", "0", 0, " no ", "off"])
def test_coerce_service_bool_falsey(value: object) -> None:
    """Falsey service values should map to False."""
    assert _coerce_service_bool(value, field="enabled") is False


def test_coerce_service_bool_rejects_invalid() -> None:
    """Unexpected values should raise ServiceValidationError."""
    with pytest.raises(ServiceValidationError, match="enabled must be a boolean"):
        _coerce_service_bool(object(), field="enabled")


def test_format_expires_in_hours_error_variants() -> None:
    """Expiry formatter should produce precise messages for all constraint branches."""
    assert (
        _format_expires_in_hours_error(
            ValidationError("expires_in_hours", constraint="expires_in_hours_required")
        )
        == "expires_in_hours is required"
    )

    assert (
        _format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours", constraint="expires_in_hours_not_numeric"
            )
        )
        == "expires_in_hours must be a number"
    )

    assert (
        _format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours",
                constraint="expires_in_hours_out_of_range",
                min_value=0.0,
                max_value=24.0,
            )
        )
        == "expires_in_hours must be between 0 and 24"
    )

    assert (
        _format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours",
                constraint="expires_in_hours_out_of_range",
                min_value=1,
            )
        )
        == "expires_in_hours must be greater than 1"
    )

    assert (
        _format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours",
                constraint="expires_in_hours_out_of_range",
                max_value=12,
            )
        )
        == "expires_in_hours must be less than 12"
    )

    assert (
        _format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours", constraint="expires_in_hours_out_of_range"
            )
        )
        == "expires_in_hours is out of range"
    )

    assert (
        _format_expires_in_hours_error(
            ValidationError("expires_in_hours", value=4, constraint="other")
        )
        == "expires_in_hours is invalid"
    )

    assert (
        _format_expires_in_hours_error(
            ValidationError("expires_in_hours", value="x", constraint="other")
        )
        == "expires_in_hours must be a number"
    )


class _ExplodingStr:
    def __str__(self) -> str:
        raise RuntimeError("boom")


def test_normalise_context_identifier() -> None:
    """Context identifiers should be trimmed and safely normalized."""
    assert _normalise_context_identifier(None) is None
    assert _normalise_context_identifier("  abc  ") == "abc"
    assert _normalise_context_identifier("   ") is None
    assert _normalise_context_identifier(42) == "42"
    assert _normalise_context_identifier(_ExplodingStr()) is None


def test_service_details_normalisation_and_error_details() -> None:
    """Service detail payloads should become JSON-safe in all supported forms."""
    payload = {
        "nested": {1: {"ok": True}},
        "values": {1, 2},
        "custom": object(),
    }
    normalised = _normalise_service_details(payload)
    assert normalised is not None
    assert normalised["nested"] == {"1": {"ok": True}}
    assert sorted(normalised["values"]) == [1, 2]
    assert isinstance(normalised["custom"], str)

    assert _normalise_service_details([1, "a"]) == {"items": [1, "a"]}
    assert _normalise_service_details("x") == {"value": "x"}
    assert _normalise_service_details(None) is None

    details = _build_error_details(
        reason="timeout", error=RuntimeError("late"), notification_id="n1"
    )
    assert details is not None
    assert details["notification_id"] == "n1"
    assert "error_classification" in details
    assert details["error_message"]


def test_extract_service_context_and_metadata_merge() -> None:
    """Service context extraction should support mappings and context-like objects."""
    mapping_call = SimpleNamespace(
        context={"id": " abc ", "parent_id": None, "user_id": "u1"}
    )
    context, metadata = _extract_service_context(mapping_call)
    assert context is not None
    assert context.id == "abc"
    assert metadata == {"context_id": "abc", "parent_id": None, "user_id": "u1"}

    real_context = Context(context_id="ctx", parent_id="p", user_id="u")
    real_call = SimpleNamespace(context=real_context)
    context2, metadata2 = _extract_service_context(real_call)
    assert context2 is real_context
    assert metadata2 == {"context_id": "ctx", "parent_id": "p", "user_id": "u"}

    target: dict[str, object] = {}
    _merge_service_context_metadata(target, metadata2)
    assert target == {"context_id": "ctx", "parent_id": "p", "user_id": "u"}

    target_with_none: dict[str, object] = {}
    _merge_service_context_metadata(target_with_none, {"x": None}, include_none=True)
    assert "x" in target_with_none


def test_capture_cache_diagnostics_normalisation() -> None:
    """Cache diagnostics should normalize invalid payloads and summary values."""
    capture = {
        "snapshots": {
            "good": {"size": 1},
            "bad": object(),
            2: {"ignored": True},
        },
        "repair_summary": {"attempts": 1},
    }
    with patch(
        "custom_components.pawcontrol.services.capture_cache_diagnostics",
        return_value=capture,
    ):
        data = _capture_cache_diagnostics(SimpleNamespace())

    assert data is not None
    assert set(data["snapshots"].keys()) == {"good", "bad"}
    assert dict(data["snapshots"]["good"]) == {}
    assert "error" in data["snapshots"]["bad"]
    assert "repair_summary" not in data

    with patch(
        "custom_components.pawcontrol.services.capture_cache_diagnostics",
        return_value=None,
    ):
        assert _capture_cache_diagnostics(SimpleNamespace()) is None


def test_record_delivery_failure_reason() -> None:
    """Delivery failures should increment rejection reason metrics."""
    runtime_data = SimpleNamespace(performance_stats={})
    _record_delivery_failure_reason(runtime_data, reason=" transport_error ")
    _record_delivery_failure_reason(runtime_data, reason="transport_error")

    metrics = runtime_data.performance_stats["rejection_metrics"]
    assert sum(metrics["failure_reasons"].values()) == 2
    assert metrics["last_failure_reason"] in metrics["failure_reasons"]


def test_record_service_result_with_guard_and_resilience() -> None:
    """Service result recorder should persist diagnostics, details,.

    and guard metrics.
    """
    runtime_data = SimpleNamespace(performance_stats={})
    runtime_data.performance_stats["resilience_summary"] = {
        "rejected_call_count": 2,
        "rejection_breaker_count": 1,
    }

    guard = ServiceGuardResult(
        domain="pawcontrol",
        service="service",
        executed=True,
        reason="ok",
    )

    _record_service_result(
        runtime_data,
        service="feed",
        status="success",
        dog_id="dog",
        message="done",
        diagnostics={"snapshots": {}},
        metadata={"number": 1, "values": {1, 2}},
        details={"extra": "value"},
        guard=[guard],
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == "feed"
    assert result["dog_id"] == "dog"
    assert result["diagnostics"]["metadata"]["number"] == 1
    assert sorted(result["diagnostics"]["metadata"]["values"]) == [1, 2]
    assert result["details"]["extra"] == "value"
    assert "resilience" in result["details"]
    assert result["guard"]["executed"] == 1
    assert runtime_data.performance_stats["service_guard_metrics"]["executed"] == 1


def test_record_service_result_ignores_missing_runtime() -> None:
    """Recorder should no-op when runtime data or stats are unavailable."""
    _record_service_result(None, service="x", status="error")
    _record_service_result(
        SimpleNamespace(performance_stats=None), service="x", status="error"
    )


def test_coordinator_resolver_paths() -> None:
    """Coordinator resolver should cache and invalidate as config.

    Entry state changes should refresh cache lookups.
    """
    hass = SimpleNamespace()
    hass.data = {}
    entry_loaded = SimpleNamespace(entry_id="1", state=ConfigEntryState.LOADED)
    entry_not_loaded = SimpleNamespace(entry_id="2", state=ConfigEntryState.NOT_LOADED)
    coordinator = SimpleNamespace(hass=hass, config_entry=entry_loaded)
    hass.config_entries = SimpleNamespace(
        async_entries=lambda _domain: [entry_not_loaded, entry_loaded]
    )

    with patch(
        "custom_components.pawcontrol.services.get_runtime_data",
        return_value=SimpleNamespace(coordinator=coordinator),
    ):
        resolver = _CoordinatorResolver(hass)
        resolved = resolver.resolve()
        assert resolved is coordinator
        assert resolver.resolve() is coordinator

        entry_loaded.state = ConfigEntryState.SETUP_IN_PROGRESS
        assert resolver._get_cached_coordinator() is None

    hass2 = SimpleNamespace(data={DOMAIN: {}}, config_entries=hass.config_entries)
    with patch(
        "custom_components.pawcontrol.services.get_runtime_data",
        return_value=SimpleNamespace(coordinator=coordinator),
    ):
        wrapper = _coordinator_resolver(hass2)
        assert _coordinator_resolver(hass2) is wrapper


def test_coordinator_resolver_error_messages() -> None:
    """Source resolver should raise user-facing validation errors for bad states."""
    hass = SimpleNamespace(data={})
    resolver = _CoordinatorResolver(hass)

    hass.config_entries = SimpleNamespace(async_entries=lambda _domain: [])
    with pytest.raises(ServiceValidationError, match="not set up"):
        resolver._resolve_from_sources()

    entry = SimpleNamespace(state=ConfigEntryState.NOT_LOADED)
    hass.config_entries = SimpleNamespace(async_entries=lambda _domain: [entry])
    with pytest.raises(ServiceValidationError, match="still initializing"):
        resolver._resolve_from_sources()

    entry2 = SimpleNamespace(state=ConfigEntryState.LOADED)
    hass.config_entries = SimpleNamespace(async_entries=lambda _domain: [entry2])
    with patch(
        "custom_components.pawcontrol.services.get_runtime_data", return_value=None
    ), pytest.raises(ServiceValidationError, match="runtime data is not ready"):
        resolver._resolve_from_sources()


@pytest.mark.asyncio
async def test_setup_and_unload_services_registers_handlers(
    mock_hass: SimpleNamespace,
) -> None:
    """Service setup should register handlers and unload should remove them."""
    mock_hass.data = {}
    mock_hass.services.async_register = Mock()
    mock_hass.services.async_remove = Mock()

    with patch(
        "custom_components.pawcontrol.services.async_dispatcher_connect",
        return_value=lambda: None,
    ):
        from custom_components.pawcontrol.services import (
            async_setup_services,
            async_unload_services,
        )

        await async_setup_services(mock_hass)

    assert mock_hass.services.async_register.call_count > 10

    await async_unload_services(mock_hass)
    assert mock_hass.services.async_remove.call_count > 10
