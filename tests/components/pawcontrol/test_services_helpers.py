from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context
import pytest

from custom_components.pawcontrol import services
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.exceptions import (
    ServiceValidationError,
    ValidationError,
)
from custom_components.pawcontrol.service_guard import ServiceGuardResult


class _ExplodingStr:
    def __str__(self) -> str:
        raise RuntimeError("boom")


class _FakeConfigEntries:
    def __init__(self, entries: list[object]) -> None:
        self._entries = entries

    def async_entries(self, domain: str) -> list[object]:
        assert domain == DOMAIN
        return list(self._entries)


def test_service_validation_error_trims_and_rejects_empty() -> None:
    error = services._service_validation_error("  bad input  ")
    assert isinstance(error, ServiceValidationError)
    assert str(error) == "bad input"

    with pytest.raises(AssertionError):
        services._service_validation_error("   ")


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("gps_update_interval_required", "gps_update_interval is required"),
        (
            "gps_update_interval_not_numeric",
            "gps_update_interval must be a whole number",
        ),
        ("gps_accuracy_not_numeric", "gps_update_interval must be a number"),
        (
            "gps_update_interval_out_of_range",
            "gps_update_interval must be between 1 and 10s",
        ),
        ("something_else", "gps_update_interval must be a whole number"),
    ],
)
def test_format_gps_validation_error(constraint: str, expected: str) -> None:
    err = ValidationError(
        "gps_update_interval",
        "x",
        constraint,
        min_value=1,
        max_value=10,
    )
    assert services._format_gps_validation_error(err, unit="s") == expected


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("name_required", "name is required"),
        ("Must be text", "name must be a string"),
        ("Cannot be empty or whitespace", "name must be a non-empty string"),
        ("other", "name is invalid"),
    ],
)
def test_format_text_validation_error(constraint: str, expected: str) -> None:
    assert (
        services._format_text_validation_error(
            ValidationError("name", "", constraint),
        )
        == expected
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


def test_format_expires_in_hours_error_variants() -> None:
    assert (
        services._format_expires_in_hours_error(
            ValidationError("expires_in_hours", None, "expires_in_hours_required"),
        )
        == "expires_in_hours is required"
    )
    assert (
        services._format_expires_in_hours_error(
            ValidationError("expires_in_hours", "x", "expires_in_hours_not_numeric"),
        )
        == "expires_in_hours must be a number"
    )
    assert (
        services._format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours",
                "x",
                "expires_in_hours_out_of_range",
                min_value=1,
                max_value=4,
            ),
        )
        == "expires_in_hours must be between 1 and 4"
    )
    assert (
        services._format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours",
                "x",
                "expires_in_hours_out_of_range",
                min_value=1,
            ),
        )
        == "expires_in_hours must be greater than 1"
    )
    assert (
        services._format_expires_in_hours_error(
            ValidationError(
                "expires_in_hours",
                "x",
                "expires_in_hours_out_of_range",
                max_value=4,
            ),
        )
        == "expires_in_hours must be less than 4"
    )
    assert (
        services._format_expires_in_hours_error(
            ValidationError("expires_in_hours", "x", "expires_in_hours_out_of_range"),
        )
        == "expires_in_hours is out of range"
    )
    assert (
        services._format_expires_in_hours_error(
            ValidationError("expires_in_hours", 3, "other"),
        )
        == "expires_in_hours is invalid"
    )


def test_format_expires_in_hours_error_non_numeric_fallback() -> None:
    assert (
        services._format_expires_in_hours_error(
            ValidationError("expires_in_hours", "x", "other"),
        )
        == "expires_in_hours must be a number"
    )


def test_coordinator_resolver_reuses_hass_domain_store() -> None:
    hass = SimpleNamespace(data={})
    first = services._coordinator_resolver(hass)
    second = services._coordinator_resolver(hass)
    assert first is second


def test_coordinator_resolver_uses_cache_and_invalidation() -> None:
    hass_instance = SimpleNamespace()
    coordinator = SimpleNamespace(
        hass=hass_instance,
        config_entry=SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="id-1"),
    )
    resolver = services._CoordinatorResolver(hass_instance)
    resolver._cache_coordinator(coordinator)
    assert resolver._get_cached_coordinator() is coordinator

    resolver._cached_coordinator = SimpleNamespace(
        hass="other",
        config_entry=SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="id-1"),
    )
    assert resolver._get_cached_coordinator() is None

    resolver._cache_coordinator(
        SimpleNamespace(
            hass=resolver._hass,
            config_entry=SimpleNamespace(
                state=ConfigEntryState.SETUP_ERROR, entry_id="id-1"
            ),
        ),
    )
    assert resolver._get_cached_coordinator() is None


def test_resolve_from_sources_runtime_data_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = SimpleNamespace(config_entry=SimpleNamespace(entry_id="id"))
    entry = SimpleNamespace(state=ConfigEntryState.LOADED)
    hass = SimpleNamespace(config_entries=_FakeConfigEntries([entry]))

    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda _hass, _entry: SimpleNamespace(coordinator=coordinator),
    )

    resolver = services._CoordinatorResolver(hass)
    assert resolver.resolve() is coordinator


def test_resolve_from_sources_runtime_data_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = SimpleNamespace(state=ConfigEntryState.LOADED)
    hass = SimpleNamespace(config_entries=_FakeConfigEntries([entry]))
    monkeypatch.setattr(services, "get_runtime_data", lambda _hass, _entry: None)

    resolver = services._CoordinatorResolver(hass)
    with pytest.raises(ServiceValidationError, match="runtime data is not ready"):
        resolver.resolve()


def test_resolve_from_sources_initializing(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = SimpleNamespace(state=ConfigEntryState.SETUP_IN_PROGRESS)
    hass = SimpleNamespace(config_entries=_FakeConfigEntries([entry]))
    monkeypatch.setattr(services, "get_runtime_data", lambda _hass, _entry: None)

    resolver = services._CoordinatorResolver(hass)
    with pytest.raises(ServiceValidationError, match="still initializing"):
        resolver.resolve()


def test_resolve_from_sources_not_setup() -> None:
    hass = SimpleNamespace(config_entries=_FakeConfigEntries([]))
    resolver = services._CoordinatorResolver(hass)

    with pytest.raises(ServiceValidationError, match="not set up"):
        resolver.resolve()


def test_capture_cache_diagnostics_normalises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        services,
        "capture_cache_diagnostics",
        lambda _runtime: {
            "snapshots": {
                "existing": {"error": "x"},
                "bad": object(),
                1: {"error": "skip"},
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
    assert "existing" in result["snapshots"]
    assert result["snapshots"]["bad"].error
    assert "repair_summary" in result


def test_get_runtime_data_for_coordinator_handles_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = SimpleNamespace(hass=object(), config_entry=object())
    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda _hass, _entry: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert services._get_runtime_data_for_coordinator(coordinator) is None


def test_coerce_and_normalise_service_details() -> None:
    assert services._coerce_service_details_value({"x": {1, 2}})["x"]
    assert services._normalise_service_details(None) is None
    assert services._normalise_service_details(["a", 1]) == {"items": ["a", 1]}
    assert services._normalise_service_details("x") == {"value": "x"}


def test_build_error_details_includes_classification_and_notification_id() -> None:
    details = services._build_error_details(
        reason="network timeout",
        error=RuntimeError("down"),
        notification_id="abc",
    )
    assert details is not None
    assert details["notification_id"] == "abc"
    assert "error_classification" in details


def test_record_service_result_collects_diagnostics() -> None:
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
    assert result["service"] == "send_notification"
    assert result["status"] == "error"
    assert result["guard"]["skipped"] == 1
    assert result["diagnostics"]["metadata"]["source"] == "test"


def test_record_delivery_failure_reason_updates_metrics() -> None:
    runtime_data = SimpleNamespace(performance_stats={})
    services._record_delivery_failure_reason(runtime_data, reason="  ", error=None)
    services._record_delivery_failure_reason(
        runtime_data, reason="network", error="boom"
    )

    metrics = runtime_data.performance_stats["rejection_metrics"]
    assert metrics["last_failure_reason"]
    assert metrics["failure_reasons"]


def test_normalise_context_identifier_handles_bad_string_conversion() -> None:
    assert services._normalise_context_identifier(None) is None
    assert services._normalise_context_identifier("  id ") == "id"
    assert services._normalise_context_identifier(_ExplodingStr()) is None


def test_merge_service_context_metadata() -> None:
    target: dict[str, object] = {}
    services._merge_service_context_metadata(
        target,
        {"context_id": "abc", "parent_id": None, 1: "ignored"},
    )
    assert target == {"context_id": "abc"}

    services._merge_service_context_metadata(
        target,
        {"parent_id": None},
        include_none=True,
    )
    assert "parent_id" in target


def test_extract_service_context_from_mapping_and_object() -> None:
    mapping_call = SimpleNamespace(
        context={"id": " c1 ", "parent_id": None, "user_id": "u1"},
    )
    context, metadata = services._extract_service_context(mapping_call)
    assert isinstance(context, Context)
    assert metadata == {"context_id": "c1", "parent_id": None, "user_id": "u1"}

    context_obj = Context(context_id="ctx", parent_id=None, user_id="usr")
    object_call = SimpleNamespace(context=context_obj)
    context2, metadata2 = services._extract_service_context(object_call)
    assert context2 is context_obj
    assert metadata2 == {"context_id": "ctx", "parent_id": None, "user_id": "usr"}


def test_extract_service_context_returns_none_when_missing() -> None:
    context, metadata = services._extract_service_context(SimpleNamespace(context=None))
    assert context is None
    assert metadata is None
