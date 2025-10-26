from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_API_TOKEN,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_GPS,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.diagnostics import async_get_config_entry_diagnostics
from custom_components.pawcontrol.script_manager import PawControlScriptManager
from custom_components.pawcontrol.telemetry import (
    record_bool_coercion_event,
    reset_bool_coercion_metrics,
)
from custom_components.pawcontrol.types import (
    CacheRepairAggregate,
    PawControlRuntimeData,
)
from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.asyncio
async def test_diagnostics_redact_sensitive_fields(hass: HomeAssistant) -> None:
    """Diagnostics should redact sensitive fields while exposing metadata."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "doggo",
                    CONF_DOG_NAME: "Doggo",
                    "modules": {MODULE_GPS: True},
                }
            ],
            CONF_API_TOKEN: "super-secret-token",
        },
        title="Doggo",
    )
    entry.options = {
        "enable_analytics": True,
        "enable_cloud_backup": False,
        "debug_logging": True,
        "system_settings": {
            "enable_analytics": True,
            "enable_cloud_backup": False,
        },
        "advanced_settings": {"debug_logging": True},
    }
    entry.add_to_hass(hass)

    hass.config.version = "2025.10.1"
    hass.config.python_version = "3.13.3"
    hass.config.start_time = datetime.now(UTC)

    automation_entry = SimpleNamespace(
        entry_id="automation-id",
        title="Resilience follow-up",
        data={
            "use_blueprint": {
                "path": "automation/pawcontrol/resilience_escalation_followup.yaml",
                "input": {
                    "manual_guard_event": "pawcontrol_manual_guard",
                    "manual_breaker_event": "pawcontrol_manual_breaker",
                    "manual_check_event": "pawcontrol_resilience_check",
                },
            }
        },
    )
    hass.config_entries.async_entries = MagicMock(return_value=[automation_entry])

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "doggo")},
        manufacturer="PawControl",
        model="Tracker",
        name="Doggo Tracker",
    )

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "doggo_status",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="pawcontrol_doggo",
    )

    hass.states.async_set(entity.entity_id, "home", {"location": "Backyard"})

    script_manager = PawControlScriptManager(hass, entry)
    object_id, _ = script_manager._build_resilience_escalation_script()
    escalation_entity_id = f"{SCRIPT_DOMAIN}.{object_id}"
    script_manager._entry_scripts = [escalation_entity_id]
    script_manager._created_entities.add(escalation_entity_id)
    script_manager._last_generation = datetime.now(UTC) - timedelta(minutes=15)

    last_triggered = datetime.now(UTC) - timedelta(minutes=5)
    hass.states.async_set(
        escalation_entity_id,
        "off",
        {
            "last_triggered": last_triggered.isoformat(),
            "fields": {
                "skip_threshold": {"default": 6},
                "breaker_threshold": {"default": 2},
                "followup_script": {"default": "script.notify_team"},
                "statistics_entity_id": {"default": "sensor.pawcontrol_statistics"},
                "escalation_service": {"default": "persistent_notification.create"},
            },
        },
    )

    class DummyCoordinator:
        def __init__(self) -> None:
            self.available = True
            self.last_update_success = True
            self.last_update_time = datetime.now(UTC)
            self.update_interval = timedelta(seconds=30)
            self.update_method = "async_update"
            self.logger = logging.getLogger(__name__)
            self.name = "PawControl Coordinator"
            self.config_entry = entry
            self.dogs = [SimpleNamespace(dog_id="doggo")]

        def get_update_statistics(self) -> dict[str, object]:
            return {
                "total_updates": 10,
                "failed": 0,
                "update_interval": 30,
                "api_token": "another-secret",
            }

        def get_dog_data(self, dog_id: str) -> dict[str, object]:
            return {
                "last_update": "2025-02-01T12:00:00+00:00",
                "status": "active",
            }

    class DummyDataManager:
        def __init__(self) -> None:
            timestamp = datetime.now(UTC)
            self._snapshots = {
                "notification_cache": {
                    "stats": {
                        "entries": 2,
                        "hits": 5,
                        "api_token": "cache-secret",
                    },
                    "diagnostics": {
                        "cleanup_invocations": 3,
                        "last_cleanup": timestamp,
                    },
                }
            }
            summary_payload = {
                "total_caches": 1,
                "anomaly_count": 0,
                "severity": "info",
                "generated_at": timestamp.isoformat(),
            }
            self._summary = CacheRepairAggregate.from_mapping(summary_payload)
            self._snapshots["notification_cache"]["repair_summary"] = self._summary

        def cache_snapshots(self) -> dict[str, dict[str, object]]:
            return self._snapshots

        def cache_repair_summary(
            self, snapshots: dict[str, object] | None = None
        ) -> CacheRepairAggregate:
            return self._summary

        def get_metrics(self) -> dict[str, object]:
            return {
                "dogs": 1,
                "storage_path": "/tmp/pawcontrol",  # simulate real path data
                "cache_diagnostics": self._snapshots,
            }

    coordinator = DummyCoordinator()
    data_manager = DummyDataManager()

    runtime = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=data_manager,
        notification_manager=SimpleNamespace(),
        feeding_manager=SimpleNamespace(),
        walk_manager=SimpleNamespace(),
        entity_factory=SimpleNamespace(),
        entity_profile="standard",
        dogs=entry.data[CONF_DOGS],
    )
    runtime.script_manager = script_manager
    runtime.performance_stats = {
        "api_token": "runtime-secret",
        "door_sensor_failures": [
            {
                "dog_id": "doggo",
                "dog_name": "Doggo",
                "door_sensor": "binary_sensor.front_door",
                "error": "storage offline",
                "recorded_at": "2024-01-01T00:00:00+00:00",
            }
        ],
        "door_sensor_failure_count": 1,
        "last_door_sensor_failure": {
            "dog_id": "doggo",
            "dog_name": "Doggo",
            "door_sensor": "binary_sensor.front_door",
            "error": "storage offline",
            "recorded_at": "2024-01-01T00:00:00+00:00",
        },
        "service_guard_metrics": {
            "executed": 1,
            "skipped": 1,
            "reasons": {"hass_missing": 1},
            "last_results": [
                {
                    "domain": "notify",
                    "service": "mobile_app_front_door",
                    "executed": False,
                    "reason": "hass_missing",
                    "description": "notify helper skipped",
                }
            ],
        },
        "service_results": [
            {
                "service": "notify_garden_alert",
                "status": "error",
                "guard": {
                    "executed": 0,
                    "skipped": 1,
                    "reasons": {"hass_missing": 1},
                    "results": [
                        {
                            "domain": "notify",
                            "service": "mobile_app_front_door",
                            "executed": False,
                            "reason": "hass_missing",
                        }
                    ],
                },
                "diagnostics": {
                    "metadata": {"context_id": "abc123"},
                },
            }
        ],
        "last_service_result": {
            "service": "notify_garden_alert",
            "status": "error",
            "guard": {
                "executed": 0,
                "skipped": 1,
                "reasons": {"hass_missing": 1},
            },
        },
        "rejection_metrics": default_rejection_metrics(),
    }
    entry.runtime_data = runtime

    hass.services.async_register(DOMAIN, "sync", lambda call: None)

    reset_bool_coercion_metrics()
    record_bool_coercion_event(
        value="1",
        default=False,
        result=True,
        reason="truthy_string",
    )

    translations = {
        "component.pawcontrol.diagnostics.setup_flags_panel.title": "Setup flags",
        "component.pawcontrol.diagnostics.setup_flags_panel.description": (
            "Analytics, backup, and debug logging toggles captured during onboarding "
            "and options flows."
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_flag_enable_analytics": (
            "Analytics telemetry"
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_flag_enable_cloud_backup": (
            "Cloud backup"
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_flag_debug_logging": (
            "Debug logging"
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_source_options": (
            "Options flow"
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_source_system_settings": (
            "System settings"
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_source_advanced_settings": (
            "Advanced settings"
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_source_config_entry": (
            "Config entry defaults"
        ),
        "component.pawcontrol.diagnostics.setup_flags_panel_source_default": (
            "Integration default"
        ),
    }

    with patch(
        "custom_components.pawcontrol.diagnostics.async_get_translations",
        AsyncMock(return_value=translations),
    ):
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    setup_flags = diagnostics["setup_flags"]
    assert setup_flags["enable_analytics"] is True
    assert setup_flags["enable_cloud_backup"] is False
    assert setup_flags["debug_logging"] is True

    setup_panel = diagnostics["setup_flags_panel"]
    assert setup_panel["title"] == "Setup flags"
    assert setup_panel["title_default"] == "Setup flags"
    assert (
        setup_panel["description"]
        == "Analytics, backup, and debug logging toggles captured during onboarding "
        "and options flows."
    )
    assert (
        setup_panel["description_default"]
        == "Analytics, backup, and debug logging toggles captured during onboarding "
        "and options flows."
    )
    assert setup_panel["enabled_count"] == 2
    assert setup_panel["disabled_count"] == 1
    assert setup_panel["language"] == "en"
    flags_by_key = {flag["key"]: flag for flag in setup_panel["flags"]}
    assert flags_by_key["enable_analytics"]["enabled"] is True
    assert flags_by_key["enable_analytics"]["source"] == "options"
    assert flags_by_key["enable_analytics"]["label"] == "Analytics telemetry"
    assert flags_by_key["enable_analytics"]["label_default"] == "Analytics telemetry"
    assert (
        flags_by_key["enable_analytics"]["label_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel_flag_enable_analytics"
    )
    assert flags_by_key["enable_analytics"]["source_label"] == "Options flow"
    assert flags_by_key["enable_analytics"]["source_label_default"] == "Options flow"
    assert (
        flags_by_key["enable_analytics"]["source_label_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel_source_options"
    )
    assert flags_by_key["enable_cloud_backup"]["enabled"] is False
    assert flags_by_key["enable_cloud_backup"]["source"] == "options"
    assert flags_by_key["enable_cloud_backup"]["label"] == "Cloud backup"
    assert flags_by_key["enable_cloud_backup"]["label_default"] == "Cloud backup"
    assert (
        flags_by_key["enable_cloud_backup"]["label_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel_flag_enable_cloud_backup"
    )
    assert flags_by_key["enable_cloud_backup"]["source_label"] == "Options flow"
    assert flags_by_key["enable_cloud_backup"]["source_label_default"] == "Options flow"
    assert (
        flags_by_key["enable_cloud_backup"]["source_label_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel_source_options"
    )
    assert flags_by_key["debug_logging"]["enabled"] is True
    assert flags_by_key["debug_logging"]["source"] == "options"
    assert flags_by_key["debug_logging"]["label"] == "Debug logging"
    assert flags_by_key["debug_logging"]["label_default"] == "Debug logging"
    assert (
        flags_by_key["debug_logging"]["label_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel_flag_debug_logging"
    )
    assert flags_by_key["debug_logging"]["source_label"] == "Options flow"
    assert flags_by_key["debug_logging"]["source_label_default"] == "Options flow"
    assert (
        flags_by_key["debug_logging"]["source_label_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel_source_options"
    )
    assert setup_panel["source_breakdown"]["options"] == 3
    assert setup_panel["source_labels"]["options"] == "Options flow"
    assert setup_panel["source_labels_default"]["options"] == "Options flow"
    assert (
        setup_panel["source_label_translation_keys"]["options"]
        == "component.pawcontrol.diagnostics.setup_flags_panel_source_options"
    )
    assert (
        setup_panel["title_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel.title"
    )
    assert (
        setup_panel["description_translation_key"]
        == "component.pawcontrol.diagnostics.setup_flags_panel.description"
    )

    escalation = diagnostics["resilience_escalation"]
    assert escalation["available"] is True
    assert escalation["state_available"] is True
    assert escalation["entity_id"] == escalation_entity_id
    assert escalation["thresholds"]["skip_threshold"]["active"] == 6
    assert escalation["thresholds"]["breaker_threshold"]["active"] == 2
    assert escalation["followup_script"]["active"] == "script.notify_team"
    assert escalation["followup_script"]["configured"] is True
    assert (
        escalation["statistics_entity_id"]["active"] == "sensor.pawcontrol_statistics"
    )
    assert escalation["last_triggered"].startswith(
        last_triggered.replace(microsecond=0).isoformat()[:16]
    )
    manual_events = escalation["manual_events"]
    assert manual_events["available"] is True
    assert manual_events["configured_guard_events"] == ["pawcontrol_manual_guard"]
    assert manual_events["configured_breaker_events"] == ["pawcontrol_manual_breaker"]
    assert manual_events["configured_check_events"] == ["pawcontrol_resilience_check"]
    assert manual_events["automations"][0]["title"] == "Resilience follow-up"

    # Diagnostics payloads should be JSON serialisable once normalised.
    serialised = json.dumps(diagnostics)
    assert "notification_cache" in serialised

    stats = diagnostics["performance_metrics"]["statistics"]
    assert stats["api_token"] == "**REDACTED**"

    dogs = diagnostics["dogs_summary"]["dogs"]
    assert dogs[0]["dog_id"] == "doggo"
    assert dogs[0]["status"] == "active"

    services = diagnostics["integration_status"]["services_registered"]
    assert "sync" in services

    debug_info = diagnostics["debug_info"]
    assert debug_info["quality_scale"] == "bronze"

    cache_diagnostics = diagnostics["cache_diagnostics"]
    cache_entry = cache_diagnostics["notification_cache"]
    assert cache_entry["stats"]["api_token"] == "**REDACTED**"
    assert isinstance(cache_entry["diagnostics"]["last_cleanup"], str)
    repair_summary = cache_entry["repair_summary"]
    assert isinstance(repair_summary, dict)
    assert repair_summary["total_caches"] == 1
    assert repair_summary["severity"] == "info"

    data_stats = diagnostics["data_statistics"]
    metrics = data_stats["metrics"]
    assert metrics["dogs"] == 1
    cache_stats = metrics["cache_diagnostics"]["notification_cache"]["stats"]
    assert cache_stats["entries"] == 2

    door_sensor = diagnostics["door_sensor"]
    assert door_sensor["available"] is False
    telemetry = door_sensor["telemetry"]
    assert telemetry["failure_count"] == 1
    assert telemetry["failures"][0]["door_sensor"] == "binary_sensor.front_door"

    performance_metrics = diagnostics["performance_metrics"]
    assert "schema_version" not in performance_metrics
    rejection_metrics = performance_metrics["rejection_metrics"]
    assert rejection_metrics["schema_version"] == 3
    assert rejection_metrics["rejected_call_count"] == 0
    assert performance_metrics["open_breakers"] == []
    assert performance_metrics["open_breaker_ids"] == []
    assert performance_metrics["half_open_breakers"] == []
    assert performance_metrics["half_open_breaker_ids"] == []
    assert performance_metrics["unknown_breakers"] == []
    assert performance_metrics["unknown_breaker_ids"] == []
    assert performance_metrics["rejection_breaker_ids"] == []
    assert performance_metrics["rejection_breakers"] == []

    service_execution = diagnostics["service_execution"]
    assert service_execution["available"] is True
    guard_metrics = service_execution["guard_metrics"]
    assert guard_metrics["executed"] == 1
    assert guard_metrics["skipped"] == 1
    assert guard_metrics["reasons"]["hass_missing"] == 1
    last_guard = guard_metrics["last_results"][0]
    assert last_guard["service"] == "mobile_app_front_door"
    service_rejection = service_execution["rejection_metrics"]
    assert service_rejection["schema_version"] == 3
    assert service_rejection["rejected_call_count"] == 0
    assert service_rejection["rejection_breaker_count"] == 0
    service_results = service_execution["service_results"]
    assert service_results[0]["service"] == "notify_garden_alert"
    assert service_results[0]["diagnostics"]["metadata"]["context_id"] == "abc123"
    assert (
        service_execution["last_service_result"]["guard"]["reasons"]["hass_missing"]
        == 1
    )
    assert rejection_metrics["rejection_breaker_count"] == 0
    assert rejection_metrics["open_breaker_count"] == 0
    assert rejection_metrics["half_open_breaker_count"] == 0
    assert rejection_metrics["unknown_breaker_count"] == 0
    assert rejection_metrics["open_breakers"] == []
    assert rejection_metrics["open_breaker_ids"] == []
    assert rejection_metrics["half_open_breakers"] == []
    assert rejection_metrics["half_open_breaker_ids"] == []
    assert rejection_metrics["unknown_breakers"] == []
    assert rejection_metrics["unknown_breaker_ids"] == []
    assert rejection_metrics["rejection_breaker_ids"] == []
    assert rejection_metrics["rejection_breakers"] == []
    stats_block = performance_metrics["statistics"]["rejection_metrics"]
    assert stats_block["schema_version"] == 3
    assert stats_block["open_breakers"] == []
    assert stats_block["half_open_breakers"] == []
    assert stats_block["unknown_breakers"] == []

    bool_coercion = diagnostics["bool_coercion"]
    assert bool_coercion["recorded"] is True
    metrics = bool_coercion["metrics"]
    assert metrics["total"] >= 1
    assert metrics["reset_count"] >= 0
    assert metrics["first_seen"] is not None
    assert metrics["last_seen"] is not None
    assert metrics["last_reset"] is not None
    assert metrics["active_window_seconds"] is not None
    assert metrics["active_window_seconds"] >= 0
    assert metrics["last_reason"] in {
        "truthy_string",
        "falsy_string",
        "unknown_string",
        "none",
        "blank_string",
        "fallback",
        "native_true",
        "native_false",
        "numeric_nonzero",
        "numeric_zero",
    }
    assert metrics["last_value_type"] is not None
    assert isinstance(metrics["last_value_repr"], str)
    assert metrics["last_result"] in {True, False}
    assert metrics["last_default"] in {True, False}
    assert set(metrics["reason_counts"]).issubset(
        {
            "none",
            "blank_string",
            "fallback",
            "native_true",
            "native_false",
            "numeric_nonzero",
            "numeric_zero",
            "truthy_string",
            "falsy_string",
            "unknown_string",
        }
    )

    summary = bool_coercion["summary"]
    assert summary["recorded"] is True
    assert summary["total"] == metrics["total"]
    assert summary["reset_count"] == metrics["reset_count"]
    assert summary["last_reason"] == metrics["last_reason"]
    assert summary["last_result"] == metrics["last_result"]
    assert summary["last_default"] == metrics["last_default"]
    expected_reason_counts = dict(sorted(metrics["reason_counts"].items()))
    assert summary["reason_counts"] == expected_reason_counts
    assert len(summary["samples"]) <= min(5, len(metrics["samples"]))
    if summary["samples"]:
        assert summary["samples"][0]["reason"] in summary["reason_counts"]

    cached_summary = runtime.performance_stats.get("bool_coercion_summary")
    assert cached_summary is not None
    assert cached_summary["total"] == summary["total"]
    assert cached_summary["reason_counts"] == summary["reason_counts"]
