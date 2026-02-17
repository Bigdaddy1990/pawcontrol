"""Unit tests for PawControl system health output."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.system_health import system_health_info
from custom_components.pawcontrol.types import DomainRuntimeStoreEntry


class _Coordinator:
    """Coordinator stub returning update statistics."""  # noqa: E111

    def __init__(  # noqa: E111
        self,
        stats: dict[str, object],
        *,
        last_update_success: bool = True,
        use_external_api: bool = True,
    ) -> None:
        self._stats = stats
        self.last_update_success = last_update_success
        self.use_external_api = use_external_api

    def get_update_statistics(self) -> dict[str, object]:  # noqa: E111
        """Return the stored statistics payload."""

        return self._stats


_FakeRuntimeData = type(
    "PawControlRuntimeData",
    (),
    {"__module__": "custom_components.pawcontrol.types"},
)


def _make_runtime_data(
    *,
    performance_stats: dict[str, object],
    coordinator: _Coordinator,
    script_manager: object | None = None,
) -> Any:
    """Return a runtime data stub that passes runtime_data validation."""  # noqa: E111

    runtime_data = _FakeRuntimeData()  # noqa: E111
    runtime_data.performance_stats = performance_stats  # noqa: E111
    runtime_data.coordinator = coordinator  # noqa: E111
    runtime_data.script_manager = script_manager  # noqa: E111
    return runtime_data  # noqa: E111


def _install_entry(hass: Any, entry: ConfigEntry) -> None:
    """Install a config entry into the Home Assistant stub."""  # noqa: E111

    hass.config_entries.async_entries = lambda domain=None: (  # noqa: E111
        [entry] if domain == DOMAIN else []
    )


@pytest.mark.asyncio
async def test_system_health_info_reports_guard_breaker_runtime_store(
    hass: Any,
) -> None:
    """System health should expose guard, breaker, and runtime store telemetry."""  # noqa: E111

    entry = ConfigEntry(  # noqa: E111
        domain=DOMAIN,
        data={},
        options={"external_api_quota": 10},
    )
    coordinator = _Coordinator({"performance_metrics": {"api_calls": "5"}})  # noqa: E111
    performance_stats = {  # noqa: E111
        "service_guard_metrics": {
            "executed": "4",
            "skipped": "2",
            "reasons": {"missing_instance": "2", "maintenance": 1},
        },
        "entity_factory_guard_metrics": {"runtime_floor": 0.5},
        "rejection_metrics": {
            "open_breaker_count": "1",
            "half_open_breaker_count": 0,
            "unknown_breaker_count": "0",
            "rejection_breaker_count": "2",
            "rejection_rate": "0.2",
            "open_breakers": ["api"],
            "last_rejection_breaker_id": "api",
            "last_rejection_breaker_name": "API Gateway",
            "last_rejection_time": 1700000000,
        },
        "runtime_store_health": {
            "assessment": {
                "level": "watch",
                "reason": "manual test",
            },
            "assessment_timeline_segments": [
                {
                    "status": "current",
                    "level": "ok",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            ],
            "assessment_timeline_summary": {
                "total_events": 1,
                "status_counts": {"current": 1},
                "level_counts": {"ok": 1},
            },
        },
    }
    runtime_data = _make_runtime_data(  # noqa: E111
        performance_stats=performance_stats,
        coordinator=coordinator,
    )
    entry.runtime_data = runtime_data  # noqa: E111
    _install_entry(hass, entry)  # noqa: E111
    hass.data[DOMAIN] = {  # noqa: E111
        entry.entry_id: DomainRuntimeStoreEntry(runtime_data=runtime_data),
    }

    info = await system_health_info(hass)  # noqa: E111

    assert info["remaining_quota"] == 5  # noqa: E111
    guard_summary = info["service_execution"]["guard_summary"]  # noqa: E111
    assert guard_summary["executed"] == 4  # noqa: E111
    assert guard_summary["skipped"] == 2  # noqa: E111
    assert guard_summary["total_calls"] == 6  # noqa: E111
    assert guard_summary["indicator"]["level"] == "warning"  # noqa: E111
    assert guard_summary["top_reasons"][0]["reason"] == "missing_instance"  # noqa: E111
    assert guard_summary["top_reasons"][0]["count"] == 2  # noqa: E111

    breaker_overview = info["service_execution"]["breaker_overview"]  # noqa: E111
    assert breaker_overview["status"] == "open"  # noqa: E111
    assert breaker_overview["open_breaker_count"] == 1  # noqa: E111
    assert breaker_overview["indicator"]["level"] == "warning"  # noqa: E111

    runtime_store = info["runtime_store"]  # noqa: E111
    assert runtime_store["status"] == "current"  # noqa: E111
    assert info["runtime_store_assessment"]["level"] == "watch"  # noqa: E111
    assert info["runtime_store_timeline_summary"]["total_events"] == 1  # noqa: E111


@pytest.mark.asyncio
async def test_system_health_info_coerces_unexpected_types(hass: Any) -> None:
    """System health should coerce malformed telemetry safely."""  # noqa: E111

    entry = ConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
    coordinator = _Coordinator({"performance_metrics": {"api_calls": None}})  # noqa: E111
    coordinator.use_external_api = False  # noqa: E111
    performance_stats = {  # noqa: E111
        "service_guard_metrics": {
            "executed": "bad",
            "skipped": None,
            "reasons": {"missing_instance": None, 123: "ignored"},
        },
        "rejection_metrics": {
            "open_breaker_count": "not-a-number",
            "half_open_breaker_count": None,
            "unknown_breaker_count": "0",
            "rejection_breaker_count": "2",
            "rejection_rate": "0.1",
        },
    }
    runtime_data = _make_runtime_data(  # noqa: E111
        performance_stats=performance_stats,
        coordinator=coordinator,
    )
    entry.runtime_data = runtime_data  # noqa: E111
    _install_entry(hass, entry)  # noqa: E111
    hass.data[DOMAIN] = {  # noqa: E111
        entry.entry_id: DomainRuntimeStoreEntry(runtime_data=runtime_data),
    }

    info = await system_health_info(hass)  # noqa: E111

    assert info["remaining_quota"] == "unlimited"  # noqa: E111
    guard_summary = info["service_execution"]["guard_summary"]  # noqa: E111
    assert guard_summary["executed"] == 0  # noqa: E111
    assert guard_summary["skipped"] == 0  # noqa: E111
    assert guard_summary["reasons"]["missing_instance"] == 0  # noqa: E111

    breaker_overview = info["service_execution"]["breaker_overview"]  # noqa: E111
    assert breaker_overview["open_breaker_count"] == 0  # noqa: E111
    assert breaker_overview["half_open_breaker_count"] == 0  # noqa: E111
    assert breaker_overview["rejection_breaker_count"] == 2  # noqa: E111
    assert breaker_overview["status"] == "monitoring"  # noqa: E111
