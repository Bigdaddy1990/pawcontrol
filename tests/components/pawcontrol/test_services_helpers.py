"""Unit tests for service helper utilities."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context
import pytest

from custom_components.pawcontrol import services
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.exceptions import ServiceValidationError
from custom_components.pawcontrol.service_guard import ServiceGuardResult
from custom_components.pawcontrol.validation import ValidationError


class _ExplodingStr:
    def __str__(self) -> str:
        raise RuntimeError("boom")


class _FakeConfigEntries:
    def __init__(self, entries: list[object]) -> None:
        self._entries = entries

    def async_entries(self, domain: str) -> list[object]:
        assert domain == DOMAIN
        return list(self._entries)


def test_format_expires_in_hours_error_fallback_and_range() -> None:
    assert (
        services._format_expires_in_hours_error(
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
        services._format_expires_in_hours_error(
            ValidationError("expires_in_hours", value=2, constraint="other")
        )
        == "expires_in_hours is invalid"
    )
    assert (
        services._format_expires_in_hours_error(
            ValidationError("expires_in_hours", value="x", constraint="other")
        )
        == "expires_in_hours must be a number"
    )


@pytest.mark.parametrize("value", [True, "yes", "enable", "1", 1])
def test_coerce_service_bool_true_values(value: object) -> None:
    assert services._coerce_service_bool(value, field="enabled") is True


@pytest.mark.parametrize("value", [False, "off", "disable", "0", 0])
def test_coerce_service_bool_false_values(value: object) -> None:
    assert services._coerce_service_bool(value, field="enabled") is False


def test_coerce_service_bool_invalid() -> None:
    with pytest.raises(ServiceValidationError, match="enabled must be a boolean"):
        services._coerce_service_bool("maybe", field="enabled")


def test_service_validation_error_requires_non_empty_message() -> None:
    with pytest.raises(AssertionError, match="non-empty message"):
        services._service_validation_error("   ")

    error = services._service_validation_error("  invalid payload ")
    assert isinstance(error, ServiceValidationError)
    assert str(error) == "invalid payload"


@pytest.mark.parametrize(
    ("error", "unit", "message"),
    [
        (
            ValidationError("gps_update_interval", constraint="gps_update_interval_required"),
            None,
            "gps_update_interval is required",
        ),
        (
            ValidationError("gps_accuracy", constraint="gps_accuracy_not_numeric"),
            None,
            "gps_accuracy must be a number",
        ),
        (
            ValidationError(
                "geofence_radius",
                constraint="geofence_radius_out_of_range",
                min_value=1,
                max_value=500,
            ),
            "m",
            "geofence_radius must be between 1 and 500m",
        ),
        (
            ValidationError("gps_update_interval", constraint="fallback"),
            None,
            "gps_update_interval must be a whole number",
        ),
        (
            ValidationError("other_field", constraint="fallback"),
            None,
            "other_field is invalid",
        ),
    ],
)
def test_format_gps_validation_error_variants(
    error: ValidationError,
    unit: str | None,
    message: str,
) -> None:
    assert services._format_gps_validation_error(error, unit=unit) == message


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            ValidationError("title", constraint="title_required"),
            "title is required",
        ),
        (
            ValidationError("title", constraint="Must be text"),
            "title must be a string",
        ),
        (
            ValidationError("title", constraint="Cannot be empty or whitespace"),
            "title must be a non-empty string",
        ),
        (
            ValidationError("title", constraint="other"),
            "title is invalid",
        ),
    ],
)
def test_format_text_validation_error_variants(
    error: ValidationError,
    message: str,
) -> None:
    assert services._format_text_validation_error(error) == message


def test_normalise_context_identifier_handles_bad_string_conversion() -> None:
    assert services._normalise_context_identifier(None) is None
    assert services._normalise_context_identifier("  id ") == "id"
    assert services._normalise_context_identifier(_ExplodingStr()) is None


def test_extract_service_context_from_mapping() -> None:
    call = SimpleNamespace(context={"id": " ctx ", "parent_id": None, "user_id": "u1"})
    context, metadata = services._extract_service_context(call)

    assert context is not None
    assert context.id == "ctx"
    assert metadata == {"context_id": "ctx", "parent_id": None, "user_id": "u1"}


def test_merge_service_context_metadata_supports_include_none() -> None:
    target: dict[str, object] = {}
    services._merge_service_context_metadata(
        target, {"context_id": "x", "parent_id": None}
    )
    assert target == {"context_id": "x"}

    services._merge_service_context_metadata(
        target, {"parent_id": None}, include_none=True
    )
    assert target["parent_id"] is None


def test_record_delivery_failure_reason_updates_metrics() -> None:
    runtime_data = SimpleNamespace(performance_stats={})
    services._record_delivery_failure_reason(runtime_data, reason="network")
    services._record_delivery_failure_reason(runtime_data, reason=" ", error="boom")

    metrics = runtime_data.performance_stats["rejection_metrics"]
    assert metrics["failure_reasons"]
    assert metrics["last_failure_reason"] in metrics["failure_reasons"]


def test_coordinator_resolver_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    coordinator = SimpleNamespace(
        hass=SimpleNamespace(),
        config_entry=SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="id-1"),
    )
    entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="id-1")
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntries([entry]))

    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda _hass, _entry: SimpleNamespace(coordinator=coordinator),
    )

    resolver = services._CoordinatorResolver(hass)
    assert resolver.resolve() is coordinator
    assert resolver.resolve() is coordinator


def test_coordinator_resolver_error_messages() -> None:
    hass = SimpleNamespace(config_entries=_FakeConfigEntries([]))
    resolver = services._CoordinatorResolver(hass)
    with pytest.raises(ServiceValidationError, match="not set up"):
        resolver.resolve()


def test_capture_cache_diagnostics_normalises_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        services,
        "capture_cache_diagnostics",
        lambda _runtime: {
            "snapshots": {
                "existing": {"error": "x"},
                "bad": object(),
                1: {"skip": True},
            },
            "repair_summary": {"attempted": 1, "repaired": 1, "failed": 0},
        },
    )
    monkeypatch.setattr(
        services,
        "ensure_cache_repair_aggregate",
        lambda value: {"attempted": 1, "repaired": 1, "failed": 0},
    )

    result = services._capture_cache_diagnostics(SimpleNamespace())
    assert result is not None
    assert set(result["snapshots"]) == {"existing", "bad"}
    assert result["repair_summary"]["repaired"] == 1


def test_record_service_result_collects_guard_and_metadata() -> None:
    runtime_data = SimpleNamespace(performance_stats={})

    services._record_service_result(
        runtime_data,
        service="send_notification",
        status="error",
        dog_id="dog-1",
        message="failed",
        diagnostics={"snapshots": {}},
        metadata={"source": "test"},
        details={"kind": "delivery"},
        guard=[
            ServiceGuardResult(
                "notify", "mobile_app", executed=False, reason="offline"
            ),
            ServiceGuardResult("notify", "email", executed=True),
        ],
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["guard"]["skipped"] == 1
    assert result["diagnostics"]["metadata"]["source"] == "test"


@pytest.mark.asyncio
async def test_setup_and_unload_services_registers_handlers(
    mock_hass: SimpleNamespace,
) -> None:
    mock_hass.data = {}
    mock_hass.services.async_register = Mock()
    mock_hass.services.async_remove = Mock()

    with patch(
        "custom_components.pawcontrol.services.async_dispatcher_connect",
        return_value=lambda: None,
    ):
        await services.async_setup_services(mock_hass)

    assert mock_hass.services.async_register.call_count > 10

    await services.async_unload_services(mock_hass)
    assert mock_hass.services.async_remove.call_count > 10


def test_extract_service_context_from_context_instance() -> None:
    ctx = Context(context_id="ctx", parent_id="p", user_id="u")
    call = SimpleNamespace(context=ctx)

    context, metadata = services._extract_service_context(call)
    assert context is ctx
    assert metadata == {"context_id": "ctx", "parent_id": "p", "user_id": "u"}


def test_coordinator_resolver_helper_stores_instance(
    mock_hass: SimpleNamespace,
) -> None:
    mock_hass.data = {}
    resolver = services._coordinator_resolver(mock_hass)
    assert resolver is services._coordinator_resolver(mock_hass)


def test_capture_cache_diagnostics_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(services, "capture_cache_diagnostics", lambda _runtime: None)
    assert services._capture_cache_diagnostics(SimpleNamespace()) is None


def test_normalise_service_details_payloads() -> None:
    set_payload = services._coerce_service_details_value({1, 2})
    assert isinstance(set_payload, list)
    assert sorted(set_payload) == [1, 2]
    assert services._normalise_service_details(["a", 1]) == {"items": ["a", 1]}
    assert services._normalise_service_details("x") == {"value": "x"}


def test_build_error_details_includes_notification_id() -> None:
    details = services._build_error_details(
        reason="network timeout",
        error="gateway timeout",
        notification_id="n-1",
    )
    assert details is not None
    assert details["notification_id"] == "n-1"
    assert "error_classification" in details
