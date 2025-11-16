from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
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
    CacheDiagnosticsMap,
    CacheDiagnosticsSnapshot,
    CacheRepairAggregate,
    CoordinatorDogData,
    CoordinatorHealthIndicators,
    CoordinatorPerformanceMetrics,
    CoordinatorRuntimeStoreSummary,
    CoordinatorStatisticsPayload,
    CoordinatorUpdateCounts,
    DataManagerMetricsSnapshot,
    JSONMutableMapping,
    PawControlRuntimeData,
    RuntimeStoreAssessmentEvent,
    RuntimeStoreAssessmentTimelineSegment,
    RuntimeStoreAssessmentTimelineSummary,
    RuntimeStoreCompatibilitySnapshot,
    RuntimeStoreEntrySnapshot,
    RuntimeStoreHealthAssessment,
    RuntimeStoreHealthHistory,
)
from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.core import Context, Event, HomeAssistant
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

        def get_update_statistics(self) -> CoordinatorStatisticsPayload:
            update_counts: CoordinatorUpdateCounts = {
                "total": 10,
                "successful": 10,
                "failed": 0,
            }
            performance_metrics: CoordinatorPerformanceMetrics = {
                "success_rate": 1.0,
                "cache_entries": 1,
                "cache_hit_rate": 1.0,
                "consecutive_errors": 0,
                "last_update": datetime.now(UTC).isoformat(),
                "update_interval": 30.0,
                "api_calls": 5,
            }
            health_indicators: CoordinatorHealthIndicators = {
                "consecutive_errors": 0,
                "stability_window_ok": True,
            }
            runtime_store_snapshot: RuntimeStoreCompatibilitySnapshot = {
                "entry_id": entry.entry_id,
                "status": "current",
                "current_version": 3,
                "minimum_compatible_version": 2,
                "entry": cast(
                    RuntimeStoreEntrySnapshot,
                    {
                        "status": "current",
                        "version": 3,
                        "created_version": 3,
                    },
                ),
                "store": cast(
                    RuntimeStoreEntrySnapshot,
                    {
                        "status": "current",
                        "version": 3,
                        "created_version": 3,
                    },
                ),
                "divergence_detected": False,
            }
            runtime_store_history: RuntimeStoreHealthHistory = {
                "checks": 1,
                "status_counts": {"current": 1},
                "last_status": "current",
                "assessment_events": cast(
                    list[RuntimeStoreAssessmentEvent],
                    [
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "level": "ok",
                            "previous_level": None,
                            "status": "current",
                            "reason": "initialisation",
                            "recommended_action": None,
                            "divergence_detected": False,
                            "checks": 1,
                            "divergence_events": 0,
                            "level_streak": 1,
                            "escalations": 0,
                            "deescalations": 0,
                            "level_changed": True,
                            "current_level_duration_seconds": None,
                        }
                    ],
                ),
                "assessment_timeline_segments": cast(
                    list[RuntimeStoreAssessmentTimelineSegment],
                    [
                        {
                            "start": datetime.now(UTC).isoformat(),
                            "end": None,
                            "level": "ok",
                            "status": "current",
                            "duration_seconds": None,
                        }
                    ],
                ),
                "assessment_timeline_summary": cast(
                    RuntimeStoreAssessmentTimelineSummary,
                    {
                        "total_events": 1,
                        "level_counts": {"ok": 1, "watch": 0, "action_required": 0},
                        "status_counts": {"current": 1},
                        "reason_counts": {"initialisation": 1},
                        "distinct_reasons": 1,
                        "last_event_timestamp": datetime.now(UTC).isoformat(),
                        "timeline_window_seconds": 0.0,
                        "timeline_window_days": 0.0,
                        "events_per_day": None,
                        "most_common_reason": "initialisation",
                        "most_common_level": "ok",
                        "most_common_status": "current",
                        "average_divergence_rate": None,
                        "max_divergence_rate": None,
                        "level_duration_peaks": {"ok": 0.0, "watch": 0.0, "action_required": 0.0},
                        "level_duration_latest": {
                            "ok": None,
                            "watch": None,
                            "action_required": None,
                        },
                        "level_duration_totals": {
                            "ok": 0.0,
                            "watch": 0.0,
                            "action_required": 0.0,
                        },
                        "level_duration_samples": {
                            "ok": 0,
                            "watch": 0,
                            "action_required": 0,
                        },
                        "level_duration_averages": {
                            "ok": None,
                            "watch": None,
                            "action_required": None,
                        },
                        "level_duration_minimums": {
                            "ok": None,
                            "watch": None,
                            "action_required": None,
                        },
                        "level_duration_medians": {
                            "ok": None,
                            "watch": None,
                            "action_required": None,
                        },
                        "level_duration_standard_deviations": {
                            "ok": None,
                            "watch": None,
                            "action_required": None,
                        },
                        "level_duration_percentiles": {
                            "ok": {},
                            "watch": {},
                            "action_required": {},
                        },
                        "level_duration_alert_thresholds": {
                            "ok": None,
                            "watch": None,
                            "action_required": None,
                        },
                    },
                ),
                "assessment": cast(
                    RuntimeStoreHealthAssessment,
                    {
                        "level": "ok",
                        "previous_level": None,
                        "reason": "initialisation",
                        "recommended_action": None,
                        "divergence_rate": None,
                        "checks": 1,
                        "divergence_events": 0,
                        "last_status": "current",
                        "divergence_detected": False,
                        "level_streak": 1,
                        "last_level_change": datetime.now(UTC).isoformat(),
                        "escalations": 0,
                        "deescalations": 0,
                        "level_durations": {
                            "ok": 0.0,
                            "watch": 0.0,
                            "action_required": 0.0,
                        },
                        "current_level_duration_seconds": None,
                        "events": cast(
                            list[RuntimeStoreAssessmentEvent],
                            [
                                {
                                    "timestamp": datetime.now(UTC).isoformat(),
                                    "level": "ok",
                                    "previous_level": None,
                                    "status": "current",
                                    "reason": "initialisation",
                                    "recommended_action": None,
                                    "divergence_detected": False,
                                    "checks": 1,
                                    "divergence_events": 0,
                                    "level_streak": 1,
                                    "escalations": 0,
                                    "deescalations": 0,
                                    "level_changed": True,
                                    "current_level_duration_seconds": None,
                                }
                            ],
                        ),
                        "timeline_segments": cast(
                            list[RuntimeStoreAssessmentTimelineSegment],
                            [
                                {
                                    "start": datetime.now(UTC).isoformat(),
                                    "end": None,
                                    "level": "ok",
                                    "status": "current",
                                    "duration_seconds": None,
                                }
                            ],
                        ),
                        "timeline_summary": cast(
                            RuntimeStoreAssessmentTimelineSummary,
                            {
                                "total_events": 1,
                                "level_counts": {
                                    "ok": 1,
                                    "watch": 0,
                                    "action_required": 0,
                                },
                                "last_level": "ok",
                                "timeline_window_days": 0.0,
                                "average_divergence_rate": None,
                                "level_duration_latest": {
                                    "ok": None,
                                    "watch": None,
                                    "action_required": None,
                                },
                                "level_duration_totals": {
                                    "ok": 0.0,
                                    "watch": 0.0,
                                    "action_required": 0.0,
                                },
                                "level_duration_samples": {
                                    "ok": 0,
                                    "watch": 0,
                                    "action_required": 0,
                                },
                                "level_duration_averages": {
                                    "ok": None,
                                    "watch": None,
                                    "action_required": None,
                                },
                                "level_duration_minimums": {
                                    "ok": None,
                                    "watch": None,
                                    "action_required": None,
                                },
                                "level_duration_medians": {
                                    "ok": None,
                                    "watch": None,
                                    "action_required": None,
                                },
                                "level_duration_standard_deviations": {
                                    "ok": None,
                                    "watch": None,
                                    "action_required": None,
                                },
                            },
                        ),
                    },
                ),
            }
            runtime_store: CoordinatorRuntimeStoreSummary = {
                "snapshot": runtime_store_snapshot,
                "history": runtime_store_history,
                "assessment": runtime_store_history["assessment"],
            }
            stats_payload: dict[str, object] = {
                "update_counts": update_counts,
                "performance_metrics": performance_metrics,
                "health_indicators": health_indicators,
                "runtime_store": runtime_store,
                "api_token": "another-secret",
            }
            return cast(CoordinatorStatisticsPayload, stats_payload)

        def get_dog_data(self, dog_id: str) -> CoordinatorDogData:
            return {
                "last_update": "2025-02-01T12:00:00+00:00",
                "status": "active",
            }

    class DummyDataManager:
        def __init__(self) -> None:
            timestamp = datetime.now(UTC)
            stats_payload: JSONMutableMapping = {
                "entries": 2,
                "hits": 5,
                "api_token": "cache-secret",
            }
            diagnostics_payload: JSONMutableMapping = {
                "cleanup_invocations": 3,
                "last_cleanup": timestamp,
            }
            snapshot = CacheDiagnosticsSnapshot(
                stats=stats_payload,
                diagnostics=cast(JSONMutableMapping, diagnostics_payload),
            )
            summary_payload: JSONMutableMapping = {
                "total_caches": 1,
                "anomaly_count": 0,
                "severity": "info",
                "generated_at": timestamp.isoformat(),
            }
            self._summary = CacheRepairAggregate.from_mapping(summary_payload)
            snapshot.repair_summary = self._summary
            self._snapshots: CacheDiagnosticsMap = {
                "notification_cache": snapshot,
            }

        def cache_snapshots(self) -> CacheDiagnosticsMap:
            return self._snapshots

        def cache_repair_summary(
            self, snapshots: Mapping[str, object] | None = None
        ) -> CacheRepairAggregate:
            return self._summary

        def get_metrics(self) -> DataManagerMetricsSnapshot:
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
    script_manager.attach_runtime_manual_history(runtime)
    entry.runtime_data = runtime
    script_manager._manual_event_sources["pawcontrol_manual_guard"] = {
        "preference_key": "manual_guard_event",
        "configured_role": "guard",
        "listener_sources": ("system_options",),
    }
    manual_context = Context(user_id="support-user")
    manual_event = Event(
        "pawcontrol_manual_guard",
        data={"note": "manual check"},
        origin="LOCAL",
        time_fired=datetime.now(UTC) - timedelta(seconds=12),
        context=manual_context,
    )
    script_manager._handle_manual_event(manual_event)
    script_manager.sync_manual_event_history()
    resilience_summary = {
        "total_breakers": 1,
        "states": {
            "closed": 0,
            "open": 1,
            "half_open": 0,
            "unknown": 0,
            "other": 0,
        },
        "failure_count": 3,
        "success_count": 5,
        "total_calls": 8,
        "total_failures": 3,
        "total_successes": 5,
        "rejected_call_count": 2,
        "last_failure_time": 1700000100.0,
        "last_state_change": 1700000200.0,
        "last_success_time": 1700000300.0,
        "last_rejection_time": 1700000400.0,
        "recovery_latency": 200.0,
        "recovery_breaker_id": "api",
        "recovery_breaker_name": "api",
        "last_rejection_breaker_id": "api",
        "last_rejection_breaker_name": "api",
        "rejection_rate": 0.25,
        "open_breaker_count": 1,
        "half_open_breaker_count": 0,
        "unknown_breaker_count": 0,
        "open_breakers": ["api"],
        "open_breaker_ids": ["api"],
        "half_open_breakers": [],
        "half_open_breaker_ids": [],
        "unknown_breakers": [],
        "unknown_breaker_ids": [],
        "rejection_breaker_count": 1,
        "rejection_breakers": ["api"],
        "rejection_breaker_ids": ["api"],
    }

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
        "entity_factory_guard_metrics": {
            "runtime_floor": 0.001,
            "baseline_floor": 0.00045,
            "max_floor": 0.0045,
            "runtime_floor_delta": 0.00055,
            "peak_runtime_floor": 0.003,
            "lowest_runtime_floor": 0.00045,
            "last_floor_change": 0.0002,
            "last_floor_change_ratio": 0.25,
            "last_actual_duration": 0.002,
            "last_duration_ratio": 2.0,
            "last_event": "expand",
            "last_updated": "2024-01-01T00:00:00+00:00",
            "samples": 3,
            "stable_samples": 2,
            "expansions": 1,
            "contractions": 0,
            "last_expansion_duration": 0.002,
            "enforce_min_runtime": True,
            "average_duration": 0.0016,
            "max_duration": 0.002,
            "min_duration": 0.001,
            "stable_ratio": 2 / 3,
            "expansion_ratio": 1 / 3,
            "contraction_ratio": 0.0,
            "volatility_ratio": 1 / 3,
            "consecutive_stable_samples": 2,
            "longest_stable_run": 2,
            "duration_span": 0.001,
            "jitter_ratio": 1.0,
            "recent_durations": [0.001, 0.0015, 0.002],
            "recent_average_duration": 0.0015,
            "recent_max_duration": 0.002,
            "recent_min_duration": 0.001,
            "recent_duration_span": 0.001,
            "recent_jitter_ratio": 1.0,
            "recent_samples": 3,
            "recent_events": ["stable", "stable", "expand"],
            "recent_stable_samples": 2,
            "recent_stable_ratio": 2 / 3,
            "stability_trend": "steady",
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
        "resilience_summary": dict(resilience_summary),
        "resilience_diagnostics": {
            "summary": dict(resilience_summary),
            "breakers": {
                "api": {
                    "breaker_id": "api",
                    "state": "OPEN",
                    "failure_count": 3,
                    "success_count": 5,
                    "last_failure_time": 1700000100.0,
                    "last_state_change": 1700000200.0,
                    "last_success_time": 1700000300.0,
                    "total_calls": 8,
                    "total_failures": 3,
                    "total_successes": 5,
                    "rejected_calls": 2,
                    "last_rejection_time": 1700000400.0,
                }
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
        "component.pawcontrol.common.setup_flags_panel_title": "Setup flags",
        "component.pawcontrol.common.setup_flags_panel_description": (
            "Analytics, backup, and debug logging toggles captured during onboarding "
            "and options flows."
        ),
        "component.pawcontrol.common.setup_flags_panel_flag_enable_analytics": (
            "Analytics telemetry"
        ),
        "component.pawcontrol.common.setup_flags_panel_flag_enable_cloud_backup": (
            "Cloud backup"
        ),
        "component.pawcontrol.common.setup_flags_panel_flag_debug_logging": (
            "Debug logging"
        ),
        "component.pawcontrol.common.setup_flags_panel_source_options": (
            "Options flow"
        ),
        "component.pawcontrol.common.setup_flags_panel_source_system_settings": (
            "System settings"
        ),
        "component.pawcontrol.common.setup_flags_panel_source_advanced_settings": (
            "Advanced settings"
        ),
        "component.pawcontrol.common.setup_flags_panel_source_config_entry": (
            "Config entry defaults"
        ),
        "component.pawcontrol.common.setup_flags_panel_source_default": (
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
        == "component.pawcontrol.common.setup_flags_panel_flag_enable_analytics"
    )
    assert flags_by_key["enable_analytics"]["source_label"] == "Options flow"
    assert flags_by_key["enable_analytics"]["source_label_default"] == "Options flow"
    assert (
        flags_by_key["enable_analytics"]["source_label_translation_key"]
        == "component.pawcontrol.common.setup_flags_panel_source_options"
    )
    assert flags_by_key["enable_cloud_backup"]["enabled"] is False
    assert flags_by_key["enable_cloud_backup"]["source"] == "options"
    assert flags_by_key["enable_cloud_backup"]["label"] == "Cloud backup"
    assert flags_by_key["enable_cloud_backup"]["label_default"] == "Cloud backup"
    assert (
        flags_by_key["enable_cloud_backup"]["label_translation_key"]
        == "component.pawcontrol.common.setup_flags_panel_flag_enable_cloud_backup"
    )
    assert flags_by_key["enable_cloud_backup"]["source_label"] == "Options flow"
    assert flags_by_key["enable_cloud_backup"]["source_label_default"] == "Options flow"
    assert (
        flags_by_key["enable_cloud_backup"]["source_label_translation_key"]
        == "component.pawcontrol.common.setup_flags_panel_source_options"
    )
    assert flags_by_key["debug_logging"]["enabled"] is True
    assert flags_by_key["debug_logging"]["source"] == "options"
    assert flags_by_key["debug_logging"]["label"] == "Debug logging"
    assert flags_by_key["debug_logging"]["label_default"] == "Debug logging"
    assert (
        flags_by_key["debug_logging"]["label_translation_key"]
        == "component.pawcontrol.common.setup_flags_panel_flag_debug_logging"
    )
    assert flags_by_key["debug_logging"]["source_label"] == "Options flow"
    assert flags_by_key["debug_logging"]["source_label_default"] == "Options flow"
    assert (
        flags_by_key["debug_logging"]["source_label_translation_key"]
        == "component.pawcontrol.common.setup_flags_panel_source_options"
    )
    assert setup_panel["source_breakdown"]["options"] == 3
    assert setup_panel["source_labels"]["options"] == "Options flow"
    assert setup_panel["source_labels_default"]["options"] == "Options flow"
    assert (
        setup_panel["source_label_translation_keys"]["options"]
        == "component.pawcontrol.common.setup_flags_panel_source_options"
    )
    assert (
        setup_panel["title_translation_key"]
        == "component.pawcontrol.common.setup_flags_panel_title"
    )
    assert (
        setup_panel["description_translation_key"]
        == "component.pawcontrol.common.setup_flags_panel_description"
    )

    runtime_store = diagnostics["runtime_store"]
    assert runtime_store["status"] == "current"
    assert runtime_store["entry"]["status"] == "current"
    assert runtime_store["store"]["status"] == "current"
    assert runtime_store["divergence_detected"] is False
    history = diagnostics.get("runtime_store_history")
    if history is not None:
        assert history["checks"] >= 1
        assert history["last_status"] == "current"
        events = history.get("assessment_events")
        if events is not None:
            assert isinstance(events, list)
            if events:
                assert isinstance(events[-1]["timestamp"], str)
        timeline_segments = history.get("assessment_timeline_segments")
        if timeline_segments is not None:
            assert isinstance(timeline_segments, list)
            if timeline_segments:
                last_segment = timeline_segments[-1]
                assert last_segment["level"] in {"ok", "watch", "action_required"}
                assert "duration_seconds" in last_segment
        timeline_summary = history.get("assessment_timeline_summary")
        if timeline_summary is not None:
            assert timeline_summary["total_events"] >= 1
            assert timeline_summary["level_counts"]["ok"] >= 0
            assert timeline_summary["status_counts"]["current"] >= 0
            assert "last_event_timestamp" in timeline_summary
            assert "timeline_window_seconds" in timeline_summary
            assert "events_per_day" in timeline_summary
            assert "level_duration_peaks" in timeline_summary
            assert "level_duration_totals" in timeline_summary
            assert "level_duration_samples" in timeline_summary
            assert "level_duration_minimums" in timeline_summary
            assert "level_duration_medians" in timeline_summary
            assert "level_duration_standard_deviations" in timeline_summary
            assert "level_duration_percentiles" in timeline_summary
            assert "level_duration_alert_thresholds" in timeline_summary
            assert "level_duration_guard_alerts" in timeline_summary
            assert "level_duration_averages" in timeline_summary
            assert "level_duration_minimums" in timeline_summary
            assert "level_duration_medians" in timeline_summary
            assert "average_divergence_rate" in timeline_summary
    assessment = diagnostics.get("runtime_store_assessment")
    if assessment is not None:
        assert assessment["level"] == "ok"
        assert assessment["recommended_action"] is None
        assert assessment["level_streak"] >= 1
        assert assessment["last_level_change"]
        assert assessment["escalations"] >= 0
        assert assessment["deescalations"] >= 0
        assert assessment["previous_level"] in {None, "ok", "watch", "action_required"}
        durations = assessment["level_durations"]
        assert durations["ok"] >= 0.0
        assert durations["watch"] >= 0.0
        assert durations["action_required"] >= 0.0
        current_duration = assessment["current_level_duration_seconds"]
        assert current_duration is None or current_duration >= 0.0
        events = assessment.get("events")
        if events is not None:
            assert isinstance(events, list)
            if events:
                latest_event = events[-1]
                assert latest_event["level"] in {"ok", "watch", "action_required"}
                assert isinstance(latest_event["timestamp"], str)
        timeline_segments = assessment.get("timeline_segments")
        if timeline_segments is not None:
            assert isinstance(timeline_segments, list)
            if timeline_segments:
                assert timeline_segments[-1]["level"] in {"ok", "watch", "action_required"}
                assert "duration_seconds" in timeline_segments[-1]
        timeline_summary = assessment.get("timeline_summary")
        if timeline_summary is not None:
            assert timeline_summary["total_events"] >= 1
            assert timeline_summary["level_counts"]["ok"] >= 0
            assert "last_level" in timeline_summary
            assert "timeline_window_days" in timeline_summary
            assert "most_common_reason" in timeline_summary
            assert "level_duration_latest" in timeline_summary
            assert "level_duration_totals" in timeline_summary
            assert "level_duration_samples" in timeline_summary
            assert "level_duration_minimums" in timeline_summary
            assert "level_duration_percentiles" in timeline_summary
            assert "level_duration_alert_thresholds" in timeline_summary
            assert "level_duration_guard_alerts" in timeline_summary
            assert "level_duration_medians" in timeline_summary
            assert "level_duration_standard_deviations" in timeline_summary
            assert "level_duration_averages" in timeline_summary
            assert "level_duration_minimums" in timeline_summary
            assert "level_duration_medians" in timeline_summary
    timeline_summary_payload = diagnostics.get("runtime_store_timeline_summary")
    if timeline_summary_payload is not None:
        assert timeline_summary_payload["total_events"] >= 1
        assert "level_counts" in timeline_summary_payload
        assert "level_duration_samples" in timeline_summary_payload
        assert "level_duration_minimums" in timeline_summary_payload
        assert "level_duration_medians" in timeline_summary_payload
        assert "level_duration_standard_deviations" in timeline_summary_payload
        assert "level_duration_percentiles" in timeline_summary_payload
        assert "level_duration_alert_thresholds" in timeline_summary_payload
        assert "level_duration_guard_alerts" in timeline_summary_payload
    timeline_segments_payload = diagnostics.get("runtime_store_timeline_segments")
    if timeline_segments_payload is not None:
        assert isinstance(timeline_segments_payload, list)
        if timeline_segments_payload:
            assert "duration_seconds" in timeline_segments_payload[0]

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
    assert manual_events["preferred_guard_event"] == "pawcontrol_manual_guard"
    assert manual_events["preferred_breaker_event"] == "pawcontrol_manual_breaker"
    assert manual_events["preferred_check_event"] == "pawcontrol_resilience_check"
    assert manual_events["preferred_events"] == {
        "manual_check_event": "pawcontrol_resilience_check",
        "manual_guard_event": "pawcontrol_manual_guard",
        "manual_breaker_event": "pawcontrol_manual_breaker",
    }
    assert manual_events["active_listeners"] == [
        "pawcontrol_manual_breaker",
        "pawcontrol_manual_guard",
        "pawcontrol_resilience_check",
    ]
    last_event = manual_events["last_event"]
    assert last_event is not None
    assert last_event["event_type"] == "pawcontrol_manual_guard"
    assert last_event["matched_preference"] == "manual_guard_event"
    assert last_event["category"] == "guard"
    assert last_event["user_id"] == "support-user"
    assert last_event["origin"] == "LOCAL"
    assert "system_options" in (last_event["sources"] or [])
    history = manual_events["event_history"]
    assert isinstance(history, list) and history
    assert history[0]["event_type"] == "pawcontrol_manual_guard"

    resilience = diagnostics["resilience"]
    assert resilience["available"] is True
    assert resilience["schema_version"] == 1
    resilience_summary = resilience["summary"]
    assert resilience_summary["recovery_breaker_id"] == "api"
    assert resilience_summary["rejection_rate"] == pytest.approx(0.25)
    assert resilience_summary["open_breakers"] == ["api"]
    breakers = resilience["breakers"]
    assert "api" in breakers
    assert breakers["api"]["state"] == "OPEN"
    assert breakers["api"]["rejected_calls"] == 2

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
    entity_guard = service_execution["entity_factory_guard"]
    assert entity_guard["runtime_floor_ms"] == pytest.approx(1.0)
    assert entity_guard["baseline_floor_ms"] == pytest.approx(0.45)
    assert entity_guard["runtime_floor_delta_ms"] == pytest.approx(0.55)
    assert entity_guard["peak_runtime_floor_ms"] == pytest.approx(3.0)
    assert entity_guard["lowest_runtime_floor_ms"] == pytest.approx(0.45)
    assert entity_guard["last_floor_change_ms"] == pytest.approx(0.2)
    assert entity_guard["last_actual_duration_ms"] == pytest.approx(2.0)
    assert entity_guard["last_event"] == "expand"
    assert entity_guard["samples"] == 3
    assert entity_guard["last_floor_change_ratio"] == pytest.approx(0.25)
    assert entity_guard["average_duration_ms"] == pytest.approx(1.6)
    assert entity_guard["max_duration_ms"] == pytest.approx(2.0)
    assert entity_guard["min_duration_ms"] == pytest.approx(1.0)
    assert entity_guard["duration_span_ms"] == pytest.approx(1.0)
    assert entity_guard["jitter_ratio"] == pytest.approx(1.0)
    assert entity_guard["recent_average_duration_ms"] == pytest.approx(1.5)
    assert entity_guard["recent_max_duration_ms"] == pytest.approx(2.0)
    assert entity_guard["recent_min_duration_ms"] == pytest.approx(1.0)
    assert entity_guard["recent_duration_span_ms"] == pytest.approx(1.0)
    assert entity_guard["recent_jitter_ratio"] == pytest.approx(1.0)
    assert entity_guard["stable_ratio"] == pytest.approx(2 / 3)
    assert entity_guard["expansion_ratio"] == pytest.approx(1 / 3)
    assert entity_guard["contraction_ratio"] == pytest.approx(0)
    assert entity_guard["volatility_ratio"] == pytest.approx(1 / 3)
    assert entity_guard["consecutive_stable_samples"] == 2
    assert entity_guard["longest_stable_run"] == 2
    assert entity_guard["recent_samples"] == 3
    assert entity_guard["recent_events"] == ["stable", "stable", "expand"]
    assert entity_guard["recent_stable_samples"] == 2
    assert entity_guard["recent_stable_ratio"] == pytest.approx(2 / 3)
    assert entity_guard["stability_trend"] == "steady"
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
