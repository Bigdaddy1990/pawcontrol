"""Runtime-path coverage tests for diagnostics helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
import pytest

from custom_components.pawcontrol import diagnostics
from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME


def _runtime(
    *,
    data_manager: object | None = None,
    notification_manager: object | None = None,
    coordinator: object | None = None,
    dogs: list[object] | None = None,
    performance_stats: object | None = None,
    door_sensor_manager: object | None = None,
    script_manager: object | None = None,
) -> Any:
    """Create a minimal runtime-like object for diagnostics tests."""
    return SimpleNamespace(
        runtime_managers=SimpleNamespace(
            data_manager=data_manager,
            notification_manager=notification_manager,
        ),
        coordinator=coordinator,
        dogs=dogs if dogs is not None else [],
        performance_stats=performance_stats if performance_stats is not None else {},
        door_sensor_manager=door_sensor_manager,
        script_manager=script_manager,
    )


def _entry(**overrides: object) -> Any:
    """Create a minimal config-entry-like object."""
    payload = {
        "entry_id": "entry-1",
        "domain": "pawcontrol",
        "state": ConfigEntryState.LOADED,
        "title": "PawControl",
        "source": "user",
        "unique_id": "abc",
        "data": {},
        "options": {},
        "version": 1,
        "supports_options": False,
        "supports_reconfigure": False,
        "supports_remove_device": False,
        "supports_unload": False,
        "created_at": None,
        "modified_at": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _state(
    *,
    state: str = "on",
    attributes: dict[str, object] | None = None,
) -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        state=state,
        last_changed=now,
        last_updated=now,
        attributes=attributes or {},
    )


def test_resolve_runtime_managers_none_and_present() -> None:
    """Runtime manager helpers should handle missing runtime data."""
    runtime = _runtime(data_manager="dm", notification_manager="nm")

    assert diagnostics._resolve_data_manager(None) is None
    assert diagnostics._resolve_notification_manager(None) is None
    assert diagnostics._resolve_data_manager(runtime) == "dm"
    assert diagnostics._resolve_notification_manager(runtime) == "nm"


@pytest.mark.asyncio
async def test_async_get_translations_wrapper_handles_missing_and_available(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translation wrapper should return defaults when helper is unavailable."""
    monkeypatch.setattr(diagnostics, "_ASYNC_GET_TRANSLATIONS", None)
    assert (
        await diagnostics._async_get_translations_wrapper(
            hass,
            "de",
            "component",
            {"pawcontrol"},
        )
        == {}
    )

    async_get = AsyncMock(return_value={"k": "v"})
    monkeypatch.setattr(diagnostics, "_ASYNC_GET_TRANSLATIONS", async_get)
    payload = await diagnostics._async_get_translations_wrapper(
        hass,
        "de",
        "component",
        {"pawcontrol"},
    )
    assert payload == {"k": "v"}


@pytest.mark.asyncio
async def test_async_resolve_setup_flag_translations_uses_fallback(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translation resolution should combine requested and fallback language maps."""
    hass.config.language = "de"

    async def _fake_async_get(
        _hass: object,
        language: str,
        _category: str,
        _integrations: set[str],
    ) -> dict[str, str]:
        if language == "de":
            return {
                diagnostics.SETUP_FLAG_LABEL_TRANSLATION_KEYS[
                    "enable_analytics"
                ]: "Analysen",
                diagnostics.SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[
                    "options"
                ]: "Optionen",
            }
        return {
            diagnostics.SETUP_FLAG_LABEL_TRANSLATION_KEYS[
                "enable_cloud_backup"
            ]: "Cloud backup",
            diagnostics.SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY: "Setup",
            diagnostics.SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY: "Beschreibung",
        }

    monkeypatch.setattr(diagnostics, "_ASYNC_GET_TRANSLATIONS", _fake_async_get)
    (
        language,
        flag_labels,
        source_labels,
        title,
        description,
    ) = await diagnostics._async_resolve_setup_flag_translations(hass)

    assert language == "de"
    assert flag_labels["enable_analytics"] == "Analysen"
    assert flag_labels["enable_cloud_backup"] == "Cloud backup"
    assert source_labels["options"] == "Optionen"
    assert title == "Setup"
    assert description == "Beschreibung"


@pytest.mark.asyncio
async def test_async_resolve_setup_flag_translations_defaults_without_helper(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translation resolution should return defaults when helper is unavailable."""
    monkeypatch.setattr(diagnostics, "_ASYNC_GET_TRANSLATIONS", None)
    (
        language,
        flag_labels,
        source_labels,
        title,
        description,
    ) = await diagnostics._async_resolve_setup_flag_translations(
        hass,
        language="en",
    )
    assert language == "en"
    assert flag_labels["enable_analytics"] == diagnostics.SETUP_FLAG_LABELS[
        "enable_analytics"
    ]
    assert source_labels["options"] == diagnostics.SETUP_FLAG_SOURCE_LABELS["options"]
    assert title == diagnostics.SETUP_FLAGS_PANEL_TITLE
    assert description == diagnostics.SETUP_FLAGS_PANEL_DESCRIPTION


def test_module_import_handles_missing_or_invalid_translation_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module import should tolerate translation import failures."""
    std_importlib = importlib.import_module("importlib")
    original_import_module = std_importlib.import_module

    def _missing(name: str, *args: object, **kwargs: object) -> object:
        if name == diagnostics._TRANSLATIONS_IMPORT_PATH:
            raise ModuleNotFoundError(name)
        return original_import_module(name, *args, **kwargs)

    monkeypatch.setattr(std_importlib, "import_module", _missing)
    module_missing = importlib.reload(diagnostics)
    assert module_missing._ASYNC_GET_TRANSLATIONS is None

    def _attribute_error(name: str, *args: object, **kwargs: object) -> object:
        if name == diagnostics._TRANSLATIONS_IMPORT_PATH:
            raise AttributeError("boom")
        return original_import_module(name, *args, **kwargs)

    monkeypatch.setattr(std_importlib, "import_module", _attribute_error)
    module_attr = importlib.reload(diagnostics)
    assert module_attr._ASYNC_GET_TRANSLATIONS is None

    importlib.reload(diagnostics)


def test_collect_setup_flag_snapshots_and_summary_cover_fallbacks() -> None:
    """Setup flag snapshots should use config-entry and default fallbacks."""
    entry = _entry(
        data={"enable_cloud_backup": True},
        options={"advanced_settings": {"debug_logging": True}},
    )

    snapshots = diagnostics._collect_setup_flag_snapshots(entry)
    summary = diagnostics._summarise_setup_flags(entry)

    assert snapshots["enable_analytics"] == {"value": False, "source": "default"}
    assert snapshots["enable_cloud_backup"] == {
        "value": True,
        "source": "config_entry",
    }
    assert snapshots["debug_logging"] == {
        "value": True,
        "source": "advanced_settings",
    }
    assert summary == {
        "enable_analytics": False,
        "enable_cloud_backup": True,
        "debug_logging": True,
    }


def test_build_statistics_payload_legacy_counts_and_optional_fields() -> None:
    """Legacy payload paths should populate all known metrics sections."""
    stats = diagnostics._build_statistics_payload(
        {
            "total_updates": "8",
            "failed": 3,
            "performance_metrics": {
                "success_rate": 75,
                "cache_entries": "12",
                "cache_hit_rate": 80.5,
                "consecutive_errors": "6",
                "last_update": "2024-01-01T00:00:00+00:00",
                "update_interval": 45,
                "api_calls": 19,
            },
            "health_indicators": {
                "consecutive_errors": "4",
                "stability_window_ok": False,
            },
            "reconfigure": {"enabled": True},
            "entity_budget": {"limit": 42},
        },
    )

    assert stats["update_counts"]["total"] == 8
    assert stats["update_counts"]["failed"] == 3
    assert stats["update_counts"]["successful"] == 5
    assert stats["performance_metrics"]["success_rate"] == 62.5
    assert stats["performance_metrics"]["cache_entries"] == 12
    assert stats["performance_metrics"]["cache_hit_rate"] == 80.5
    assert stats["performance_metrics"]["consecutive_errors"] == 6
    assert stats["performance_metrics"]["api_calls"] == 19
    assert stats["health_indicators"]["consecutive_errors"] == 4
    assert stats["health_indicators"]["stability_window_ok"] is False
    assert stats["reconfigure"] == {"enabled": True}
    assert stats["entity_budget"] == {"limit": 42}


def test_build_statistics_payload_top_level_update_interval() -> None:
    """Top-level update interval should be used when metrics payload is invalid."""
    stats = diagnostics._build_statistics_payload({"update_interval": 33})
    assert stats["performance_metrics"]["update_interval"] == 33.0


def test_entity_registry_entries_for_config_entry_helper_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entity registry lookup should support both HA helper and fallback scan."""
    expected = [SimpleNamespace(entity_id="sensor.a")]
    monkeypatch.setattr(
        diagnostics.er,
        "async_entries_for_config_entry",
        lambda _registry, _entry_id: expected,
        raising=False,
    )
    assert diagnostics._entity_registry_entries_for_config_entry(
        object(),
        "entry-1",
    ) == expected

    monkeypatch.setattr(
        diagnostics.er,
        "async_entries_for_config_entry",
        None,
        raising=False,
    )
    registry = SimpleNamespace(
        entities={
            "sensor.a": SimpleNamespace(config_entry_id="entry-1"),
            "sensor.b": SimpleNamespace(config_entry_id="entry-2"),
        },
    )
    entries = diagnostics._entity_registry_entries_for_config_entry(registry, "entry-1")
    assert len(entries) == 1
    assert entries[0].config_entry_id == "entry-1"


def test_device_registry_entries_for_config_entry_helper_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Device registry lookup should support helper and config_entries fallback."""
    expected = [SimpleNamespace(id="device-1")]
    monkeypatch.setattr(
        diagnostics.dr,
        "async_entries_for_config_entry",
        lambda _registry, _entry_id: expected,
        raising=False,
    )
    assert diagnostics._device_registry_entries_for_config_entry(
        object(),
        "entry-1",
    ) == expected

    monkeypatch.setattr(
        diagnostics.dr,
        "async_entries_for_config_entry",
        None,
        raising=False,
    )
    registry = SimpleNamespace(
        devices={
            "device-1": SimpleNamespace(config_entry_id=None, config_entries={"entry-1"}),
            "device-2": SimpleNamespace(config_entry_id="entry-2", config_entries=set()),
        },
    )
    entries = diagnostics._device_registry_entries_for_config_entry(registry, "entry-1")
    assert len(entries) == 1
    assert entries[0].config_entries == {"entry-1"}


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics_aggregates_runtime_sections(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-level diagnostics should aggregate runtime store and cache sections."""
    entry = _entry(entry_id="entry-main", data={})
    runtime = _runtime(coordinator=object())

    monkeypatch.setattr(diagnostics, "get_runtime_data", lambda _h, _e: runtime)
    monkeypatch.setattr(
        diagnostics,
        "_collect_cache_diagnostics",
        lambda _runtime: {"primary": {"stats": {"entries": 2}}},
    )
    monkeypatch.setattr(
        diagnostics,
        "_serialise_cache_diagnostics_payload",
        lambda payload: {"serialised": sorted(payload.keys())},
    )

    monkeypatch.setattr(
        diagnostics,
        "_get_config_entry_diagnostics",
        AsyncMock(return_value={"config": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_system_diagnostics",
        AsyncMock(return_value={"system": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_integration_status",
        AsyncMock(return_value={"integration": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_coordinator_diagnostics",
        AsyncMock(return_value={"coordinator": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_entities_diagnostics",
        AsyncMock(return_value={"entities": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_devices_diagnostics",
        AsyncMock(return_value={"devices": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_dogs_summary",
        AsyncMock(return_value={"dogs": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_performance_metrics",
        AsyncMock(return_value={"perf": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_data_statistics",
        AsyncMock(return_value={"metrics": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_recent_errors",
        AsyncMock(return_value=[{"error": True}]),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_debug_information",
        AsyncMock(return_value={"debug": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_door_sensor_diagnostics",
        AsyncMock(return_value={"door": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_service_execution_diagnostics",
        AsyncMock(return_value={"service": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_async_build_setup_flags_panel",
        AsyncMock(return_value={"flags": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_notification_diagnostics",
        AsyncMock(return_value={"notifications": True}),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_bool_coercion_diagnostics",
        lambda _runtime: {"recorded": False},
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_resilience_diagnostics",
        lambda _runtime, _coordinator: {"available": True},
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_resilience_escalation_snapshot",
        lambda _runtime: {"available": True},
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_guard_notification_error_metrics",
        lambda _runtime: {"available": False},
    )
    monkeypatch.setattr(
        diagnostics,
        "describe_runtime_store_status",
        lambda _hass, _entry: {"status": "ok"},
    )
    monkeypatch.setattr(
        diagnostics,
        "get_runtime_store_health",
        lambda _runtime: {
            "assessment": {"grade": "good"},
            "assessment_timeline_segments": [
                {"state": "ok"},
                "skip",
                {"state": "warn"},
            ],
            "assessment_timeline_summary": {"segments": 2},
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "get_entry_push_telemetry_snapshot",
        lambda _hass, _entry_id: {"push": True},
    )
    monkeypatch.setattr(diagnostics, "_summarise_setup_flags", lambda _entry: {})
    monkeypatch.setattr(diagnostics, "_redact_sensitive_data", lambda value: value)

    payload = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert payload["runtime_store_assessment"] == {"grade": "good"}
    assert payload["runtime_store_timeline_segments"] == [
        {"state": "ok"},
        {"state": "warn"},
    ]
    assert payload["runtime_store_timeline_summary"] == {"segments": 2}
    assert payload["cache_diagnostics"] == {"serialised": ["primary"]}


def test_resilience_escalation_snapshot_paths() -> None:
    """Escalation diagnostics should degrade gracefully when runtime data is missing."""
    assert diagnostics._get_resilience_escalation_snapshot(None) == {"available": False}
    assert (
        diagnostics._get_resilience_escalation_snapshot(_runtime(script_manager=None))
        == {"available": False}
    )

    manager_none = SimpleNamespace(get_resilience_escalation_snapshot=lambda: None)
    assert (
        diagnostics._get_resilience_escalation_snapshot(
            _runtime(script_manager=manager_none),
        )
        == {"available": False}
    )

    manager = SimpleNamespace(
        get_resilience_escalation_snapshot=lambda: {"captured": datetime(2024, 1, 1, tzinfo=UTC)}
    )
    payload = diagnostics._get_resilience_escalation_snapshot(
        _runtime(script_manager=manager),
    )
    assert payload["captured"] == "2024-01-01T00:00:00+00:00"


def test_resilience_diagnostics_runtime_and_coordinator_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resilience diagnostics should support runtime telemetry and coordinator fallback."""
    monkeypatch.setattr(
        diagnostics,
        "get_runtime_resilience_diagnostics",
        lambda _runtime: {
            "summary": {"status": "ok"},
            "breakers": {"api": {"state": "closed"}, "invalid": "skip"},
        },
    )
    runtime_payload = diagnostics._get_resilience_diagnostics(_runtime(), None)
    assert runtime_payload["available"] is True
    assert runtime_payload["summary"] == {"status": "ok"}
    assert "invalid" not in runtime_payload["breakers"]

    monkeypatch.setattr(
        diagnostics,
        "get_runtime_resilience_diagnostics",
        lambda _runtime: None,
    )
    coordinator = SimpleNamespace(
        get_update_statistics=lambda: {"resilience": {"summary": "invalid"}},
    )
    coordinator_payload = diagnostics._get_resilience_diagnostics(None, coordinator)
    assert coordinator_payload["available"] is True
    assert coordinator_payload["summary"] is None


def test_resilience_diagnostics_handles_coordinator_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coordinator fallback should guard against statistics retrieval failures."""
    monkeypatch.setattr(
        diagnostics,
        "get_runtime_resilience_diagnostics",
        lambda _runtime: None,
    )
    coordinator = SimpleNamespace(
        get_update_statistics=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    payload = diagnostics._get_resilience_diagnostics(None, coordinator)
    assert payload == {"available": False}


@pytest.mark.asyncio
async def test_get_config_entry_diagnostics_handles_state_variants() -> None:
    """Config entry diagnostics should normalise config metadata and dog counts."""
    created = datetime(2024, 1, 1, tzinfo=UTC)
    modified = datetime(2024, 1, 2, tzinfo=UTC)

    loaded_entry = _entry(
        data={"dogs": [{"id": 1}, {"id": 2}]},
        state=ConfigEntryState.LOADED,
        created_at=created,
        modified_at=modified,
    )
    loaded_payload = await diagnostics._get_config_entry_diagnostics(loaded_entry)
    assert loaded_payload["state"] == ConfigEntryState.LOADED.value
    assert loaded_payload["dogs_configured"] == 2
    assert loaded_payload["created_at"] == created.isoformat()
    assert loaded_payload["modified_at"] == modified.isoformat()

    custom_entry = _entry(state="booting", data={"dogs": "invalid"})
    custom_payload = await diagnostics._get_config_entry_diagnostics(custom_entry)
    assert custom_payload["state"] == "booting"
    assert custom_payload["dogs_configured"] == 0

    none_entry = _entry(state=None)
    none_payload = await diagnostics._get_config_entry_diagnostics(none_entry)
    assert none_payload["state"] is None


@pytest.mark.asyncio
async def test_get_system_diagnostics_with_and_without_start_time(hass) -> None:
    """System diagnostics should include uptime only when start_time exists."""
    hass.config.version = "2026.1"
    hass.config.python_version = "3.13"
    hass.config.time_zone = "Europe/Berlin"
    hass.config.config_dir = "/tmp/config"
    hass.config.safe_mode = True
    hass.config.recovery_mode = False
    hass.is_running = True

    hass.config.start_time = datetime.now(UTC) - timedelta(minutes=5)
    with_uptime = await diagnostics._get_system_diagnostics(hass)
    assert isinstance(with_uptime["uptime_seconds"], float)
    assert with_uptime["uptime_seconds"] > 0

    hass.config.start_time = None
    without_uptime = await diagnostics._get_system_diagnostics(hass)
    assert without_uptime["uptime_seconds"] is None


def test_collect_cache_diagnostics_guards_and_unexpected_payloads() -> None:
    """Cache diagnostics should return None for unsupported runtime manager setups."""
    assert diagnostics._collect_cache_diagnostics(None) is None
    assert diagnostics._collect_cache_diagnostics(_runtime(data_manager=None)) is None
    assert (
        diagnostics._collect_cache_diagnostics(
            _runtime(data_manager=SimpleNamespace(cache_snapshots="nope")),
        )
        is None
    )
    assert (
        diagnostics._collect_cache_diagnostics(
            _runtime(data_manager=SimpleNamespace(cache_snapshots=lambda: [1, 2, 3])),
        )
        is None
    )


def test_collect_cache_diagnostics_normalises_and_skips_invalid_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache diagnostics should keep only valid cache names."""
    monkeypatch.setattr(
        diagnostics,
        "_normalise_cache_snapshot",
        lambda payload: payload,
    )
    runtime = _runtime(
        data_manager=SimpleNamespace(
            cache_snapshots=lambda: {"main": {"ok": True}, "": {}, 3: {}},
        ),
    )
    payload = diagnostics._collect_cache_diagnostics(runtime)
    assert payload == {"main": {"ok": True}}


def test_collect_cache_diagnostics_supports_dict_branch_when_mapping_alias_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coverage guard: explicit dict branch should still normalise snapshots."""
    fake_mapping = type("FakeMapping", (), {})
    monkeypatch.setattr(diagnostics, "Mapping", fake_mapping)
    runtime = _runtime(
        data_manager=SimpleNamespace(cache_snapshots=lambda: {"main": {"ok": True}}),
    )
    payload = diagnostics._collect_cache_diagnostics(runtime)
    assert payload is not None
    assert payload["main"].to_mapping()["snapshot"] == {"value": {"ok": True}}


def test_normalise_cache_snapshot_handles_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache snapshot normalisation should handle invalid summaries and payload types."""
    monkeypatch.setattr(diagnostics, "ensure_cache_repair_aggregate", lambda _v: None)
    monkeypatch.setattr(
        diagnostics.CacheRepairAggregate,
        "from_mapping",
        lambda _value: (_ for _ in ()).throw(ValueError("broken")),
    )

    snapshot = diagnostics._normalise_cache_snapshot(
        {
            "repair_summary": {"broken": True},
            "diagnostics": "invalid",
            "snapshot": {"x": 1},
            "stats": {"entries": 1},
        },
    )
    assert snapshot.repair_summary is None
    assert snapshot.diagnostics is None
    assert snapshot.snapshot == {"x": 1}

    empty_snapshot = diagnostics._normalise_cache_snapshot({})
    assert empty_snapshot.snapshot == {"value": {}}

    unsupported = diagnostics._normalise_cache_snapshot(5)
    assert "Unsupported diagnostics payload" in (unsupported.error or "")


def test_normalise_cache_snapshot_handles_invalid_repair_summary_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid repair summaries and diagnostics payloads should be dropped safely."""
    monkeypatch.setattr(diagnostics, "ensure_cache_repair_aggregate", lambda _v: None)

    def _raise_from_mapping(*_args: object, **_kwargs: object) -> object:
        raise ValueError("invalid")

    monkeypatch.setattr(
        diagnostics.CacheRepairAggregate,
        "from_mapping",
        _raise_from_mapping,
    )
    snapshot = diagnostics.CacheDiagnosticsSnapshot(
        repair_summary={"broken": True},  # type: ignore[arg-type]
        diagnostics="invalid",  # type: ignore[arg-type]
    )
    normalised = diagnostics._normalise_cache_snapshot(snapshot)
    assert normalised.repair_summary is None
    assert normalised.diagnostics is None


def test_normalise_cache_snapshot_keeps_mapping_diagnostics() -> None:
    """Mapping diagnostics metadata should be normalised and preserved."""
    snapshot = diagnostics.CacheDiagnosticsSnapshot(
        diagnostics={"ttl": 30, "nested": {"count": 1}},
    )
    normalised = diagnostics._normalise_cache_snapshot(snapshot)
    assert normalised.diagnostics == {"ttl": 30, "nested": {"count": 1}}


def test_serialise_cache_helpers_cover_mapping_inputs() -> None:
    """Cache serialisation should accept plain mapping payloads."""
    payload = diagnostics._serialise_cache_diagnostics_payload(
        {"primary": {"stats": {"entries": 2}}},
    )
    assert payload["primary"]["stats"]["entries"] == 2

    single = diagnostics._serialise_cache_snapshot({"stats": {"entries": 4}})
    assert single["stats"]["entries"] == 4


@pytest.mark.asyncio
async def test_get_integration_status_with_runtime_and_without_runtime(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration status should report runtime manager availability correctly."""
    coordinator = SimpleNamespace(
        last_update_success=True,
        last_update_time=datetime(2024, 1, 1, tzinfo=UTC),
    )
    runtime = _runtime(
        coordinator=coordinator,
        data_manager=object(),
        notification_manager=object(),
    )
    entry = _entry(state=ConfigEntryState.LOADED)
    monkeypatch.setattr(
        diagnostics,
        "_get_loaded_platforms",
        AsyncMock(return_value=["sensor"]),
    )
    monkeypatch.setattr(
        diagnostics,
        "_get_registered_services",
        AsyncMock(return_value=["refresh"]),
    )

    payload = await diagnostics._get_integration_status(hass, entry, runtime)
    assert payload["entry_loaded"] is True
    assert payload["coordinator_available"] is True
    assert payload["data_manager_available"] is True
    assert payload["notification_manager_available"] is True

    no_runtime_payload = await diagnostics._get_integration_status(hass, entry, None)
    assert no_runtime_payload["coordinator_available"] is False
    assert no_runtime_payload["data_manager_available"] is False
    assert no_runtime_payload["notification_manager_available"] is False


@pytest.mark.asyncio
async def test_get_notification_diagnostics_available_path() -> None:
    """Notification diagnostics should export manager stats and delivery snapshot."""
    manager = SimpleNamespace(
        async_get_performance_statistics=AsyncMock(return_value={"window": timedelta(seconds=30)}),
        get_delivery_status_snapshot=lambda: {
            "services": {"notify.test": {"total_failures": 1}},
        },
    )
    runtime = _runtime(notification_manager=manager)

    payload = await diagnostics._get_notification_diagnostics(runtime)
    assert payload["available"] is True
    assert payload["manager_stats"]["window"] == "0:00:30"
    assert payload["rejection_metrics"]["total_failures"] == 1


def test_build_notification_rejection_metrics_handles_invalid_services_payload() -> None:
    """Notification rejection helper should ignore malformed service entries."""
    assert diagnostics._build_notification_rejection_metrics({"services": []})[
        "total_services"
    ] == 0

    payload = diagnostics._build_notification_rejection_metrics(
        {
            "services": {
                "notify.ok": {"total_failures": 2, "consecutive_failures": 1},
                "notify.skip": "invalid",
                5: {"total_failures": 1},
            },
        },
    )
    assert payload["total_services"] == 1
    assert payload["total_failures"] == 2


def test_build_guard_notification_error_metrics_handles_zero_and_invalid_entries() -> None:
    """Guard/notification aggregation should skip invalid entries and zero counts."""
    payload = diagnostics._build_guard_notification_error_metrics(
        {
            "skipped": 2,
            "reasons": {"missing_instance": 0, "missing_services_api": "3"},
        },
        {
            "services": {
                "notify.invalid": "bad",
                "notify.zero": {"total_failures": 0},
                "notify.auth": {"total_failures": "2", "last_error": "Unauthorized"},
            },
        },
    )

    assert payload["guard"]["skipped"] == 2
    assert payload["guard"]["reasons"] == {"missing_services_api": 3}
    assert payload["notifications"]["total_failures"] == 2
    assert payload["notifications"]["services_with_failures"] == ["notify.auth"]
    assert payload["available"] is True


def test_get_guard_notification_error_metrics_runtime_paths() -> None:
    """Runtime guard/notification helper should use runtime telemetry when available."""
    assert diagnostics._get_guard_notification_error_metrics(None)["available"] is False

    manager = SimpleNamespace(
        get_delivery_status_snapshot=lambda: {
            "services": {
                "notify.test": {
                    "total_failures": 1,
                    "last_error_reason": "missing_notify_service",
                },
            },
        },
    )
    runtime = _runtime(
        notification_manager=manager,
        performance_stats={
            "service_guard_metrics": {"skipped": 1, "reasons": {"missing_instance": 1}},
        },
    )
    payload = diagnostics._get_guard_notification_error_metrics(runtime)
    assert payload["available"] is True
    assert payload["total_errors"] == 2


@pytest.mark.asyncio
async def test_get_coordinator_diagnostics_none_and_active() -> None:
    """Coordinator diagnostics should support missing coordinators and active snapshots."""
    unavailable = await diagnostics._get_coordinator_diagnostics(None)
    assert unavailable == {"available": False, "reason": "Coordinator not initialized"}

    coordinator = SimpleNamespace(
        available=True,
        last_update_success=False,
        last_update_time=datetime(2024, 1, 1, tzinfo=UTC),
        update_interval=timedelta(seconds=90),
        update_method="poll",
        logger=SimpleNamespace(name="pawcontrol.test"),
        name="PawControl",
        config_entry=SimpleNamespace(entry_id="entry-1"),
        dogs=[{"id": "a"}],
        get_update_statistics=lambda: {"update_counts": {"total": 1}},
    )
    payload = await diagnostics._get_coordinator_diagnostics(coordinator)
    assert payload["available"] is True
    assert payload["update_interval_seconds"] == 90.0
    assert payload["dogs_managed"] == 1


@pytest.mark.asyncio
async def test_get_coordinator_diagnostics_uses_fallback_on_exception() -> None:
    """Coordinator diagnostics should use fallback statistics on retrieval errors."""
    coordinator = SimpleNamespace(
        available=False,
        last_update_success=False,
        last_update_time=None,
        update_interval=None,
        logger=SimpleNamespace(name="pawcontrol.test"),
        name="PawControl",
        config_entry=SimpleNamespace(entry_id="entry-1"),
        dogs=[],
        get_update_statistics=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    payload = await diagnostics._get_coordinator_diagnostics(coordinator)
    assert payload["statistics"]["update_counts"]["total"] == 0


@pytest.mark.asyncio
async def test_get_entities_and_devices_diagnostics(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entity and device diagnostics should export grouped registry snapshots."""
    monkeypatch.setattr(diagnostics.er, "async_get", lambda _hass: object(), raising=False)
    monkeypatch.setattr(
        diagnostics,
        "_entity_registry_entries_for_config_entry",
        lambda _registry, _entry_id: [
            SimpleNamespace(
                entity_id="sensor.pawcontrol_test",
                unique_id="uid-1",
                platform="sensor",
                device_id="device-1",
                disabled=False,
                disabled_by=None,
                hidden=False,
                entity_category=None,
                has_entity_name=True,
                original_name="Test Sensor",
                capabilities={"state_class": "measurement"},
            ),
        ],
    )
    hass.states = SimpleNamespace(
        get=lambda _entity_id: _state(attributes={"unit_of_measurement": "kg"}),
    )

    entry = _entry(entry_id="entry-1")
    entities_payload = await diagnostics._get_entities_diagnostics(hass, entry)
    assert entities_payload["total_entities"] == 1
    assert entities_payload["platform_counts"] == {"sensor": 1}

    monkeypatch.setattr(diagnostics.dr, "async_get", lambda _hass: object(), raising=False)
    monkeypatch.setattr(
        diagnostics,
        "_device_registry_entries_for_config_entry",
        lambda _registry, _entry_id: [
            SimpleNamespace(
                id="device-1",
                name="Hub",
                manufacturer="PawControl",
                model="Hub",
                sw_version="1.0",
                hw_version="A",
                via_device_id=None,
                disabled=False,
                disabled_by=None,
                entry_type=None,
                identifiers={("pawcontrol", "device-1")},
                connections={("mac", "AA:BB:CC:DD:EE:FF")},
                configuration_url="https://example.test",
            ),
        ],
    )
    devices_payload = await diagnostics._get_devices_diagnostics(hass, entry)
    assert devices_payload["total_devices"] == 1
    assert devices_payload["disabled_devices"] == 0


@pytest.mark.asyncio
async def test_get_dogs_summary_covers_coordinator_data_paths() -> None:
    """Dog summary diagnostics should handle success, missing data, and exceptions."""
    entry = _entry(
        data={
            "dogs": [
                {
                    CONF_DOG_ID: "dog-a",
                    CONF_DOG_NAME: "Alpha",
                    "modules": {"feeding": True, "walk": False},
                },
                {
                    CONF_DOG_ID: "dog-b",
                    CONF_DOG_NAME: "Bravo",
                    "modules": {},
                },
                {
                    CONF_DOG_ID: "dog-c",
                    CONF_DOG_NAME: "Charlie",
                    "modules": {"walk": True},
                },
                {CONF_DOG_ID: 123},
            ],
        },
    )

    def _get_dog_data(dog_id: str) -> object:
        if dog_id == "dog-a":
            return {"last_update": "now", "status": "ok"}
        if dog_id == "dog-b":
            return None
        raise RuntimeError("failure")

    coordinator = SimpleNamespace(get_dog_data=_get_dog_data)
    payload = await diagnostics._get_dogs_summary(entry, coordinator)
    dogs = {dog["dog_id"]: dog for dog in payload["dogs"]}

    assert payload["total_dogs"] == 4
    assert dogs["dog-a"]["coordinator_data_available"] is True
    assert dogs["dog-b"]["coordinator_data_available"] is False
    assert dogs["dog-c"]["coordinator_data_available"] is False


@pytest.mark.asyncio
async def test_get_performance_metrics_exception_and_default_rejection_path() -> None:
    """Performance diagnostics should expose fallback errors and default rejection data."""
    failing = SimpleNamespace(
        get_update_statistics=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    failed_payload = await diagnostics._get_performance_metrics(failing)
    assert failed_payload["available"] is False
    assert failed_payload["error"] == "offline"

    coordinator = SimpleNamespace(
        get_update_statistics=lambda: {
            "update_counts": {"total": 2, "failed": 1, "successful": 1},
            "performance_metrics": {"update_interval": 30},
            "reconfigure": {"enabled": True},
            "entity_budget": {"limit": 8},
        },
        last_update_success=True,
    )
    payload = await diagnostics._get_performance_metrics(coordinator)
    assert payload["rejection_metrics"]["schema_version"] == 4
    assert payload["statistics"]["reconfigure"] == {"enabled": True}
    assert payload["statistics"]["entity_budget"] == {"limit": 8}


@pytest.mark.asyncio
async def test_get_performance_metrics_uses_default_rejection_when_stats_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Performance diagnostics should fall back to default rejection metrics."""
    monkeypatch.setattr(
        diagnostics,
        "_build_statistics_payload",
        lambda _stats: {
            "update_counts": {"total": 3, "failed": 1, "successful": 2},
            "health_indicators": {"consecutive_errors": 0, "stability_window_ok": True},
            "performance_metrics": {"update_interval": 5.0},
        },
    )
    coordinator = SimpleNamespace(
        get_update_statistics=lambda: {"ignored": True},
        last_update_success=True,
    )
    payload = await diagnostics._get_performance_metrics(coordinator)
    assert payload["rejection_metrics"]["schema_version"] == 4
    assert payload["statistics"]["rejection_metrics"]["schema_version"] == 4


@pytest.mark.asyncio
async def test_get_performance_metrics_merges_rejection_defaults_when_no_perf_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty performance payload should still merge rejection metrics into output."""
    class _FalsyDict(dict[str, object]):
        def __bool__(self) -> bool:
            return False

    monkeypatch.setattr(diagnostics, "normalize_value", lambda value: value)
    monkeypatch.setattr(
        diagnostics,
        "_build_statistics_payload",
        lambda _stats: {
            "update_counts": {"total": 1, "failed": 0, "successful": 1},
            "health_indicators": {"consecutive_errors": 0, "stability_window_ok": True},
            "performance_metrics": _FalsyDict({"update_interval": 0}),
            "rejection_metrics": diagnostics.default_rejection_metrics(),
        },
    )
    coordinator = SimpleNamespace(
        get_update_statistics=lambda: {"ignored": True},
        last_update_success=True,
    )
    payload = await diagnostics._get_performance_metrics(coordinator)
    assert "rejected_call_count" in payload


@pytest.mark.asyncio
async def test_get_door_sensor_diagnostics_paths() -> None:
    """Door sensor diagnostics should include telemetry and manager diagnostics."""
    assert await diagnostics._get_door_sensor_diagnostics(None) == {"available": False}

    no_manager = _runtime(
        performance_stats={
            "door_sensor_failure_count": 2,
            "last_door_sensor_failure": {"reason": "timeout"},
            "door_sensor_failures": [{"id": 1}],
            "door_sensor_failure_summary": {"timeout": {"count": 2}},
        },
    )
    no_manager_payload = await diagnostics._get_door_sensor_diagnostics(no_manager)
    assert no_manager_payload["available"] is False
    assert no_manager_payload["telemetry"]["failure_count"] == 2

    manager = SimpleNamespace(
        async_get_detection_status=AsyncMock(return_value={"armed": True}),
        get_diagnostics=lambda: {"sensors": 1},
    )
    runtime = _runtime(door_sensor_manager=manager, performance_stats={})
    payload = await diagnostics._get_door_sensor_diagnostics(runtime)
    assert payload["available"] is True
    assert payload["status"] == {"armed": True}
    assert payload["manager_diagnostics"] == {"sensors": 1}


@pytest.mark.asyncio
async def test_get_service_execution_diagnostics_non_mapping_and_merge_paths() -> None:
    """Service execution diagnostics should handle absent and present rejection payloads."""
    non_mapping_runtime = _runtime(performance_stats=["invalid"])
    unavailable = await diagnostics._get_service_execution_diagnostics(non_mapping_runtime)
    assert unavailable["available"] is False

    runtime = _runtime(
        performance_stats={
            "service_guard_metrics": {"executed": 1, "skipped": 0},
            "rejection_metrics": {"rejected_call_count": 2},
        },
    )
    available = await diagnostics._get_service_execution_diagnostics(runtime)
    assert available["available"] is True
    assert available["rejection_metrics"]["rejected_call_count"] == 2


def test_get_bool_coercion_diagnostics_includes_metrics_when_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bool coercion diagnostics should include raw metrics when events are recorded."""
    monkeypatch.setattr(diagnostics, "get_bool_coercion_metrics", lambda: {"calls": 1})
    monkeypatch.setattr(
        diagnostics,
        "update_runtime_bool_coercion_summary",
        lambda _runtime: {"recorded": 1, "last": "ok"},
    )
    payload = diagnostics._get_bool_coercion_diagnostics(_runtime())
    assert payload["recorded"] is True
    assert payload["metrics"] == {"calls": 1}


def test_normalise_service_guard_metrics_and_service_call_telemetry() -> None:
    """Service guard and call telemetry normalisation should handle edge payloads."""
    assert diagnostics._normalise_service_guard_metrics({}) is None

    telemetry = diagnostics._normalise_service_call_telemetry(
        {
            "last": "ok",
            "per_service": {
                "notify.mobile": {"success": True},
                "skip": "invalid",
            },
        },
    )
    assert telemetry is not None
    assert telemetry["per_service"] == {"notify.mobile": {"success": True}}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, 1),
        (7, 7),
        (2.9, 2),
        (" 5 ", 5),
        ("invalid", None),
    ],
)
def test_coerce_int_variants(value: object, expected: int | None) -> None:
    """Integer coercion should support bool/int/float/string inputs."""
    assert diagnostics._coerce_int(value) == expected


@pytest.mark.asyncio
async def test_get_data_statistics_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Data statistics should handle runtime absence and include cache/dog metrics."""
    assert await diagnostics._get_data_statistics(None, None) == {
        "data_manager_available": False,
        "metrics": {},
    }

    assert await diagnostics._get_data_statistics(_runtime(data_manager=None), None) == {
        "data_manager_available": False,
        "metrics": {},
    }

    manager = SimpleNamespace(get_metrics=lambda: {"objects": 3, "window": timedelta(seconds=5)})
    runtime = _runtime(data_manager=manager, dogs=[{"id": "a"}, {"id": "b"}])
    monkeypatch.setattr(
        diagnostics,
        "_collect_cache_diagnostics",
        lambda _runtime: {"main": {"stats": {"entries": 1}}},
    )
    payload = await diagnostics._get_data_statistics(runtime, None)
    assert payload["data_manager_available"] is True
    assert payload["metrics"]["objects"] == 3
    assert payload["metrics"]["window"] == "0:00:05"
    assert payload["metrics"]["dogs"] == 2
    assert "cache_diagnostics" in payload["metrics"]

    runtime_with_bad_metrics = _runtime(
        data_manager=SimpleNamespace(get_metrics=lambda: ["invalid"]),
        dogs=[],
    )
    provided_cache = {"provided": diagnostics.CacheDiagnosticsSnapshot(snapshot={"ok": True})}
    payload_with_provided_cache = await diagnostics._get_data_statistics(
        runtime_with_bad_metrics,
        provided_cache,
    )
    assert payload_with_provided_cache["metrics"]["cache_diagnostics"]["provided"][
        "snapshot"
    ] == {"ok": True}


@pytest.mark.asyncio
async def test_misc_debug_platform_service_and_module_usage_helpers(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Miscellaneous helpers should return deterministic diagnostics payloads."""
    errors = await diagnostics._get_recent_errors("entry-1")
    assert errors[0]["entry_id"] == "entry-1"

    hass.config.version = "2026.2"
    entry = _entry(entry_id="entry-1")
    debug_payload = await diagnostics._get_debug_information(hass, entry)
    assert debug_payload["entry_id"] == "entry-1"
    assert debug_payload["ha_version"] == "2026.2"

    monkeypatch.setattr(diagnostics.er, "async_get", lambda _hass: object(), raising=False)
    monkeypatch.setattr(
        diagnostics,
        "_entity_registry_entries_for_config_entry",
        lambda _registry, _entry_id: [
            SimpleNamespace(platform="sensor"),
            SimpleNamespace(platform="binary_sensor"),
        ],
    )
    platforms = await diagnostics._get_loaded_platforms(hass, entry)
    assert sorted(platforms) == ["binary_sensor", "sensor"]

    hass.services = SimpleNamespace(
        async_services=lambda: {"pawcontrol": {"refresh": object(), "sync": object()}},
    )
    services = await diagnostics._get_registered_services(hass)
    assert sorted(services) == ["refresh", "sync"]

    usage = diagnostics._calculate_module_usage(
        [
            {"modules": {"feeding": True, "walk": False}},
            {"modules": {"feeding": False, "walk": True}},
            {"modules": "invalid"},
        ],
    )
    assert usage["counts"]["feeding"] == 1
    assert usage["counts"]["walk"] == 1
