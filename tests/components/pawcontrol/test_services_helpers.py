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


def test_service_validation_error_strips_and_rejects_empty() -> None:
    error = services._service_validation_error("  invalid value  ")
    assert isinstance(error, ServiceValidationError)
    assert str(error) == "invalid value"

    with pytest.raises(
        AssertionError, match="_service_validation_error requires a non-empty message"
    ):
        services._service_validation_error("   ")


def test_format_gps_validation_error_variants() -> None:
    assert (
        services._format_gps_validation_error(
            ValidationError(
                "gps_update_interval", constraint="gps_update_interval_required"
            )
        )
        == "gps_update_interval is required"
    )
    assert (
        services._format_gps_validation_error(
            ValidationError(
                "gps_update_interval",
                constraint="gps_update_interval_out_of_range",
                min_value=30,
                max_value=3600,
            ),  # noqa: E501
            unit="s",
        )
        == "gps_update_interval must be between 30 and 3600s"
    )
    assert (
        services._format_gps_validation_error(
            ValidationError("gps_accuracy", constraint="gps_accuracy_not_numeric")
        )
        == "gps_accuracy must be a number"
    )
    assert (
        services._format_gps_validation_error(
            ValidationError("unknown_field", constraint="other")
        )
        == "unknown_field is invalid"
    )


def test_format_text_validation_error_variants() -> None:
    assert (
        services._format_text_validation_error(
            ValidationError("note", constraint="field_required")
        )
        == "note is required"
    )
    assert (
        services._format_text_validation_error(
            ValidationError("note", constraint="Must be text")
        )
        == "note must be a string"
    )
    assert (
        services._format_text_validation_error(
            ValidationError("note", constraint="Cannot be empty or whitespace")
        )
        == "note must be a non-empty string"
    )
    assert (
        services._format_text_validation_error(
            ValidationError("note", constraint="other")
        )
        == "note is invalid"
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


def test_coordinator_resolver_initializing_and_runtime_not_ready_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loading_entry = SimpleNamespace(state=ConfigEntryState.SETUP_IN_PROGRESS)
    hass = SimpleNamespace(config_entries=_FakeConfigEntries([loading_entry]))
    resolver = services._CoordinatorResolver(hass)
    with pytest.raises(ServiceValidationError, match="still initializing"):
        resolver.resolve()

    loaded_entry = SimpleNamespace(state=ConfigEntryState.LOADED)
    hass_loaded = SimpleNamespace(config_entries=_FakeConfigEntries([loaded_entry]))
    monkeypatch.setattr(services, "get_runtime_data", lambda _hass, _entry: None)
    with pytest.raises(ServiceValidationError, match="runtime data is not ready"):
        services._CoordinatorResolver(hass_loaded).resolve()


def test_coordinator_resolver_accessor_reuses_cached_instance() -> None:
    hass = SimpleNamespace(data={})
    first = services._coordinator_resolver(hass)
    second = services._coordinator_resolver(hass)
    assert first is second
    assert hass.data[DOMAIN]["_service_coordinator_resolver"] is first

    hass.data[DOMAIN]["_service_coordinator_resolver"] = object()
    replaced = services._coordinator_resolver(hass)
    assert isinstance(replaced, services._CoordinatorResolver)


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


def test_capture_cache_diagnostics_handles_empty_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(services, "capture_cache_diagnostics", lambda _runtime: None)
    assert services._capture_cache_diagnostics(SimpleNamespace()) is None


def test_get_runtime_data_for_coordinator_handles_lookup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = SimpleNamespace(
        hass=SimpleNamespace(), config_entry=SimpleNamespace()
    )
    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda _hass, _entry: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert services._get_runtime_data_for_coordinator(coordinator) is None


def test_normalise_service_details_and_error_details_helpers() -> None:
    payload = {"a": 1, "b": {1, 2}, "c": {"nested": object()}}
    normalised = services._normalise_service_details(payload)
    assert normalised is not None
    assert normalised["a"] == 1
    assert isinstance(normalised["b"], list)
    assert "object at" in str(normalised["c"]["nested"])

    assert services._normalise_service_details(("x", 1)) == {"items": ["x", 1]}
    assert services._normalise_service_details("value") == {"value": "value"}

    details = services._build_error_details(
        reason="network",
        error="timeout",
        notification_id="notify-1",
    )
    assert details is not None
    assert details["error_classification"] == "timeout"
    assert details["notification_id"] == "notify-1"


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
