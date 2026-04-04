"""Unit tests for service helper utilities."""

from types import SimpleNamespace
from typing import cast
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


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            ValidationError(
                "expires_in_hours",
                constraint="expires_in_hours_out_of_range",
                min_value=2,
            ),
            "expires_in_hours must be greater than 2",
        ),
        (
            ValidationError(
                "expires_in_hours",
                constraint="expires_in_hours_out_of_range",
                max_value=12,
            ),
            "expires_in_hours must be less than 12",
        ),
        (
            ValidationError(
                "expires_in_hours",
                constraint="expires_in_hours_out_of_range",
            ),
            "expires_in_hours is out of range",
        ),
        (
            ValidationError("expires_in_hours", constraint="expires_in_hours_required"),
            "expires_in_hours is required",
        ),
        (
            ValidationError(
                "expires_in_hours",
                constraint="expires_in_hours_not_numeric",
            ),
            "expires_in_hours must be a number",
        ),
    ],
)
def test_format_expires_in_hours_error_full_branches(
    error: ValidationError,
    expected: str,
) -> None:
    assert services._format_expires_in_hours_error(error) == expected


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
            ),
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
            ValidationError(
                "gps_update_interval", constraint="gps_update_interval_required"
            ),
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
def test_format_gps_validation_error_variants(  # noqa: F811
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
def test_format_text_validation_error_variants(  # noqa: F811
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


def test_coordinator_resolver_invalidate_respects_entry_id() -> None:
    resolver = services._CoordinatorResolver(SimpleNamespace())
    resolver._cached_coordinator = SimpleNamespace()  # type: ignore[attr-defined]
    resolver._cached_entry_id = "entry-1"  # type: ignore[attr-defined]

    resolver.invalidate(entry_id="entry-2")
    assert resolver._cached_coordinator is not None  # type: ignore[attr-defined]

    resolver.invalidate(entry_id="entry-1")
    assert resolver._cached_coordinator is None  # type: ignore[attr-defined]


def test_coordinator_resolver_get_cached_invalid_states() -> None:
    wrong_hass = SimpleNamespace()
    current_hass = SimpleNamespace()
    coordinator = SimpleNamespace(
        hass=wrong_hass,
        config_entry=SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="id"),
    )
    resolver = services._CoordinatorResolver(current_hass)
    resolver._cached_coordinator = coordinator  # type: ignore[attr-defined]
    resolver._cached_entry_id = "id"  # type: ignore[attr-defined]

    assert resolver._get_cached_coordinator() is None  # type: ignore[attr-defined]

    resolver._cached_coordinator = SimpleNamespace(  # type: ignore[attr-defined]
        hass=current_hass,
        config_entry=SimpleNamespace(
            state=ConfigEntryState.SETUP_IN_PROGRESS,
            entry_id="id",
        ),
    )
    resolver._cached_entry_id = "id"  # type: ignore[attr-defined]
    assert resolver._get_cached_coordinator() is None  # type: ignore[attr-defined]


def test_extract_service_context_none_and_passthrough_context_name() -> None:
    call_without_context = SimpleNamespace()
    context, metadata = services._extract_service_context(call_without_context)
    assert context is None
    assert metadata is None

    FakeContext = type("Context", (), {})
    fake_context = FakeContext()
    fake_context.id = "ctx-name"
    fake_context.parent_id = None
    fake_context.user_id = None
    call_with_named_context = SimpleNamespace(context=fake_context)

    context, metadata = services._extract_service_context(call_with_named_context)
    assert context is fake_context
    assert metadata == {
        "context_id": "ctx-name",
        "parent_id": None,
        "user_id": None,
    }


def test_merge_service_context_metadata_ignores_non_string_keys() -> None:
    target: dict[str, object] = {}
    source = cast(dict[str, object], {1: "skip", "context_id": "ctx"})
    services._merge_service_context_metadata(target, source)
    assert target == {"context_id": "ctx"}


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


def test_record_service_result_sets_resilience_summary_when_diagnostics_present() -> (
    None
):
    """Service result should append resilience data onto existing diagnostics."""
    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": {"rejected_call_count": 1}}
    )

    services._record_service_result(
        runtime_data,
        service="send_notification",
        status="error",
        diagnostics={"cache": {"snapshots": {}}},
    )

    diagnostics = runtime_data.performance_stats["last_service_result"]["diagnostics"]
    assert "resilience_summary" in diagnostics
    assert diagnostics["resilience_summary"]["rejected_call_count"] == 1


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


def test_extract_service_context_without_identifiers_returns_none_metadata() -> None:
    """Objects without usable IDs should not fabricate context metadata."""
    call = SimpleNamespace(context=SimpleNamespace(extra="value"))

    context, metadata = services._extract_service_context(call)
    assert context is None
    assert metadata is None


def test_record_delivery_failure_reason_normalises_blank_classification() -> None:
    """Blank classifications should fall back to an explicit unknown bucket."""
    runtime_data = SimpleNamespace(
        performance_stats={"rejection_metrics": {"failure_reasons": "invalid"}}
    )
    blank_context = SimpleNamespace(classification="  ")
    with patch(
        "custom_components.pawcontrol.services.build_error_context",
        return_value=blank_context,
    ):
        services._record_delivery_failure_reason(runtime_data, reason="anything")

    metrics = runtime_data.performance_stats["rejection_metrics"]
    assert metrics["last_failure_reason"] == "unknown"
    assert metrics["failure_reasons"]["unknown"] == 1


def test_normalise_context_identifier_handles_whitespace_stringified_value() -> None:
    """Non-string values that stringify to whitespace should be ignored."""

    class _WhitespaceStr:
        def __str__(self) -> str:
            return "   "

    value = _WhitespaceStr()

    assert services._normalise_context_identifier(value) is None


def test_format_expires_in_hours_error_supports_one_sided_ranges() -> None:
    """Range messaging should handle min-only and max-only payloads."""
    minimum_only = ValidationError(
        "expires_in_hours",
        constraint="expires_in_hours_out_of_range",
        min_value=1.5,
    )
    maximum_only = ValidationError(
        "expires_in_hours",
        constraint="expires_in_hours_out_of_range",
        max_value=8.0,
    )

    assert (
        services._format_expires_in_hours_error(minimum_only)
        == "expires_in_hours must be greater than 1.5"
    )
    assert (
        services._format_expires_in_hours_error(maximum_only)
        == "expires_in_hours must be less than 8"
    )


def test_coordinator_resolver_invalidate_and_stale_cache_paths() -> None:
    """Resolver should preserve unrelated cache invalidations and drop stale cache."""
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntries([]))
    resolver = services._CoordinatorResolver(hass)

    active_coordinator = SimpleNamespace(
        hass=hass,
        config_entry=SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1"),
    )
    resolver._cache_coordinator(active_coordinator)
    resolver.invalidate(entry_id="entry-2")
    assert resolver._get_cached_coordinator() is active_coordinator

    paused_coordinator = SimpleNamespace(
        hass=hass,
        config_entry=SimpleNamespace(
            state=ConfigEntryState.SETUP_IN_PROGRESS,
            entry_id="entry-1",
        ),
    )
    resolver._cache_coordinator(paused_coordinator)
    assert resolver._get_cached_coordinator() is None

    foreign_coordinator = SimpleNamespace(
        hass=SimpleNamespace(),
        config_entry=SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1"),
    )
    resolver._cache_coordinator(foreign_coordinator)
    assert resolver._get_cached_coordinator() is None


def test_extract_service_context_with_class_named_context_and_empty_metadata() -> None:
    """Class-name based context objects should still return context instances."""

    ContextLike = type("Context", (), {})
    context_like = ContextLike()
    context_like.id = "ctx-9"
    context_like.parent_id = " "
    context_like.user_id = None
    call = SimpleNamespace(context=context_like)

    context, metadata = services._extract_service_context(call)
    assert context is context_like
    assert metadata == {"context_id": "ctx-9", "parent_id": None, "user_id": None}


def test_record_service_result_replaces_non_list_service_results() -> None:
    """Legacy non-list result payloads should be replaced with list containers."""
    runtime_data = SimpleNamespace(performance_stats={"service_results": "invalid"})

    services._record_service_result(
        runtime_data,
        service="send_notification",
        status="success",
        metadata={"attempt": 1},
    )

    performance_stats = runtime_data.performance_stats
    assert isinstance(performance_stats["service_results"], list)
    assert performance_stats["service_results"][0]["status"] == "success"
    assert performance_stats["last_service_result"]["diagnostics"]["metadata"] == {
        "attempt": 1
    }
