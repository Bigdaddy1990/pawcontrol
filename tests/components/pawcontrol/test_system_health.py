from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from custom_components.pawcontrol import system_health as system_health_module
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.types import PawControlRuntimeData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_system_health_no_api(hass: HomeAssistant) -> None:
    """Return defaults when API is unavailable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": [], "entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pawcontrol.system_health.system_health.async_check_can_reach_url"
    ) as mock_check:
        info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is False
    assert info["remaining_quota"] == "unknown"
    assert "service_execution" not in info
    mock_check.assert_not_called()


async def test_system_health_reports_coordinator_status(
    hass: HomeAssistant,
) -> None:
    """Use coordinator statistics when runtime data is available."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 3}
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        unique_id="coordinator-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
    )

    info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is True
    assert info["remaining_quota"] == "unlimited"
    coordinator.get_update_statistics.assert_called_once()

    service_execution = info["service_execution"]
    assert service_execution["guard_summary"]["total_calls"] == 0
    assert service_execution["guard_summary"]["skip_ratio"] == 0.0
    assert service_execution["breaker_overview"]["status"] == "healthy"
    assert service_execution["status"]["guard"]["level"] == "normal"
    assert service_execution["status"]["breaker"]["color"] == "green"
    assert service_execution["status"]["overall"]["level"] == "normal"


async def test_system_health_reports_external_quota(
    hass: HomeAssistant,
) -> None:
    """Report remaining quota when external API tracking is enabled."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = True
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 7}
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        options={"external_api_quota": 10},
        unique_id="quota-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
    )

    info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is True
    assert info["remaining_quota"] == 3


async def test_system_health_guard_and_breaker_summary(hass: HomeAssistant) -> None:
    """Expose guard skip ratios and breaker details in system health."""

    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.use_external_api = True
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 4}
    }

    script_manager = MagicMock()
    script_manager.get_resilience_escalation_snapshot.return_value = {
        "thresholds": {
            "skip_threshold": {"active": 5, "default": 3},
            "breaker_threshold": {"active": 2, "default": 1},
        },
        "manual_events": {
            "available": False,
            "automations": [],
            "configured_guard_events": [],
            "configured_breaker_events": [],
            "configured_check_events": [],
            "preferred_events": {
                "manual_check_event": "pawcontrol_resilience_check",
                "manual_guard_event": "pawcontrol_manual_guard",
                "manual_breaker_event": "pawcontrol_manual_breaker",
            },
            "preferred_guard_event": "pawcontrol_manual_guard",
            "preferred_breaker_event": "pawcontrol_manual_breaker",
            "preferred_check_event": "pawcontrol_resilience_check",
            "active_listeners": [],
            "last_event": None,
        },
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        options={"external_api_quota": 12},
        unique_id="guard-breaker-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 5,
                "skipped": 3,
                "reasons": {"breaker": 2, "maintenance": 1},
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 6,
                "rejection_breaker_count": 2,
                "rejection_rate": 0.42,
                "open_breaker_count": 1,
                "open_breakers": ["Primary API"],
                "half_open_breaker_count": 1,
                "half_open_breakers": ["Telemetry"],
                "unknown_breaker_count": 0,
                "last_rejection_breaker_id": "primary",
                "last_rejection_breaker_name": "Primary API",
                "last_rejection_time": 1_700_000_500.0,
            },
        },
        script_manager=script_manager,
    )

    info = await system_health_module.system_health_info(hass)

    assert info["remaining_quota"] == 8

    service_execution = info["service_execution"]
    guard_summary = service_execution["guard_summary"]
    assert guard_summary["total_calls"] == 8
    assert guard_summary["has_skips"] is True
    assert guard_summary["skip_ratio"] == pytest.approx(3 / 8)
    assert guard_summary["top_reasons"][0] == {"reason": "breaker", "count": 2}
    assert guard_summary["thresholds"]["source"] == "resilience_script"
    assert guard_summary["thresholds"]["source_key"] == "active"
    assert guard_summary["thresholds"]["warning"]["count"] == 4
    assert guard_summary["thresholds"]["critical"]["count"] == 5
    guard_indicator = guard_summary["indicator"]
    assert guard_indicator["level"] == "warning"
    assert guard_indicator["color"] == "amber"
    assert guard_indicator["threshold_source"] == "default_ratio"
    assert "system default threshold" in guard_indicator["message"]

    rejection_metrics = service_execution["rejection_metrics"]
    assert rejection_metrics["open_breaker_count"] == 1
    assert rejection_metrics["half_open_breaker_count"] == 1
    assert rejection_metrics["rejection_rate"] == pytest.approx(0.42)

    breaker_overview = service_execution["breaker_overview"]
    assert breaker_overview["status"] == "open"
    assert breaker_overview["open_breakers"] == ["Primary API"]
    assert breaker_overview["half_open_breakers"] == ["Telemetry"]
    assert breaker_overview["thresholds"]["critical"]["count"] == 2
    breaker_indicator = breaker_overview["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["threshold"] == 2
    assert breaker_indicator["threshold_source"] == "active"
    assert "configured resilience script threshold" in breaker_indicator["message"]

    status = service_execution["status"]
    assert status["guard"]["level"] == "warning"
    assert status["breaker"]["level"] == "critical"
    assert status["overall"]["level"] == "critical"


async def test_system_health_indicator_critical_paths(hass: HomeAssistant) -> None:
    """Surface critical status when guard ratios and breakers exceed thresholds."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 2}
    }

    script_manager = MagicMock()
    script_manager.get_resilience_escalation_snapshot.return_value = {
        "thresholds": {
            "skip_threshold": {"active": 5, "default": 3},
            "breaker_threshold": {"active": 2, "default": 1},
        },
        "manual_events": {
            "available": False,
            "automations": [],
            "configured_guard_events": [],
            "configured_breaker_events": [],
            "configured_check_events": [],
            "preferred_events": {
                "manual_check_event": "pawcontrol_resilience_check",
                "manual_guard_event": "pawcontrol_manual_guard",
                "manual_breaker_event": "pawcontrol_manual_breaker",
            },
            "preferred_guard_event": "pawcontrol_manual_guard",
            "preferred_breaker_event": "pawcontrol_manual_breaker",
            "preferred_check_event": "pawcontrol_resilience_check",
            "active_listeners": [],
            "last_event": None,
        },
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        unique_id="critical-indicator-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 2,
                "skipped": 5,
                "reasons": {"breaker": 3, "maintenance": 2},
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 10,
                "rejection_breaker_count": 1,
                "rejection_rate": 0.78,
                "open_breaker_count": 2,
                "open_breakers": ["Primary API", "Sync"],
                "half_open_breaker_count": 1,
                "half_open_breakers": ["Telemetry"],
                "unknown_breaker_count": 0,
            },
        },
        script_manager=script_manager,
    )

    info = await system_health_module.system_health_info(hass)

    service_execution = info["service_execution"]
    guard_indicator = service_execution["guard_summary"]["indicator"]
    assert guard_indicator["level"] == "critical"
    assert guard_indicator["color"] == "red"
    assert guard_indicator["threshold_source"] == "active"
    assert "configured resilience script threshold" in guard_indicator["message"]

    breaker_indicator = service_execution["breaker_overview"]["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["metric"] == 3
    assert breaker_indicator["threshold_source"] == "active"

    overall_indicator = service_execution["status"]["overall"]
    assert overall_indicator["level"] == "critical"
    assert overall_indicator["color"] == "red"


async def test_system_health_threshold_disabled_fallbacks(
    hass: HomeAssistant,
) -> None:
    """Fallback to ratio and default counts when thresholds are disabled."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 5}
    }

    script_manager = MagicMock()
    script_manager.get_resilience_escalation_snapshot.return_value = {
        "thresholds": {
            "skip_threshold": {"active": 0, "default": 0},
            "breaker_threshold": {"active": 0, "default": 0},
        },
        "manual_events": {
            "available": False,
            "automations": [],
            "configured_guard_events": [],
            "configured_breaker_events": [],
            "configured_check_events": [],
            "preferred_events": {
                "manual_check_event": "pawcontrol_resilience_check",
                "manual_guard_event": "pawcontrol_manual_guard",
                "manual_breaker_event": "pawcontrol_manual_breaker",
            },
            "preferred_guard_event": "pawcontrol_manual_guard",
            "preferred_breaker_event": "pawcontrol_manual_breaker",
            "preferred_check_event": "pawcontrol_resilience_check",
            "active_listeners": [],
            "last_event": None,
        },
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        unique_id="threshold-disabled-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 1,
                "skipped": 1,
                "reasons": {"breaker": 1},
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 0,
                "rejection_breaker_count": 0,
                "rejection_rate": 0.0,
                "open_breaker_count": 2,
                "open_breakers": ["Primary", "Backup"],
                "half_open_breaker_count": 1,
                "half_open_breakers": ["Telemetry"],
            },
        },
        script_manager=script_manager,
    )

    info = await system_health_module.system_health_info(hass)

    guard_summary = info["service_execution"]["guard_summary"]
    assert guard_summary["thresholds"]["source"] == "default_ratio"
    assert guard_summary["thresholds"]["critical"]["ratio"] == pytest.approx(0.5)
    guard_indicator = guard_summary["indicator"]
    assert guard_indicator["level"] == "critical"
    assert guard_indicator["threshold_source"] == "default_ratio"
    assert "system default threshold" in guard_indicator["message"]

    breaker_overview = info["service_execution"]["breaker_overview"]
    assert breaker_overview["thresholds"]["source"] == "default_counts"
    breaker_indicator = breaker_overview["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["threshold"] == 3
    assert "system default threshold" in breaker_indicator["message"]

    status = info["service_execution"]["status"]
    assert status["overall"]["level"] == "critical"


async def test_system_health_uses_option_thresholds(
    hass: HomeAssistant,
) -> None:
    """Use options flow thresholds when script metadata is unavailable."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 1}
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        options={
            "system_settings": {
                "resilience_skip_threshold": 4,
                "resilience_breaker_threshold": 2,
            }
        },
        unique_id="options-threshold-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 2,
                "skipped": 3,
                "reasons": {"breaker": 3},
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 0,
                "rejection_breaker_count": 0,
                "rejection_rate": 0.0,
                "open_breaker_count": 2,
                "open_breakers": ["Primary", "Backup"],
                "half_open_breaker_count": 0,
                "half_open_breakers": [],
            },
        },
        script_manager=None,
    )

    info = await system_health_module.system_health_info(hass)

    guard_summary = info["service_execution"]["guard_summary"]
    assert guard_summary["thresholds"]["source"] == "config_entry"
    assert guard_summary["thresholds"]["critical"]["count"] == 4
    guard_indicator = guard_summary["indicator"]
    assert guard_indicator["level"] == "warning"
    assert guard_indicator["threshold_source"] == "system_settings"
    assert "options flow system settings threshold" in guard_indicator["message"]

    breaker_overview = info["service_execution"]["breaker_overview"]
    assert breaker_overview["thresholds"]["source"] == "config_entry"
    assert breaker_overview["thresholds"]["critical"]["count"] == 2
    breaker_indicator = breaker_overview["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["threshold_source"] == "system_settings"
    assert "options flow system settings threshold" in breaker_indicator["message"]

    status = info["service_execution"]["status"]
    assert status["overall"]["level"] == "critical"
