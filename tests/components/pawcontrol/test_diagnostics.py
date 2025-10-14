from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from custom_components.pawcontrol.const import (
    CONF_API_TOKEN,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_GPS,
)
from custom_components.pawcontrol.diagnostics import async_get_config_entry_diagnostics
from custom_components.pawcontrol.types import (
    CacheRepairAggregate,
    PawControlRuntimeData,
)
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
    entry.add_to_hass(hass)

    hass.config.version = "2025.10.1"
    hass.config.python_version = "3.13.3"
    hass.config.start_time = datetime.now(UTC)

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
    runtime.performance_stats = {"api_token": "runtime-secret"}
    entry.runtime_data = runtime

    hass.services.async_register(DOMAIN, "sync", lambda call: None)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

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

    performance_metrics = diagnostics["performance_metrics"]
    assert "schema_version" not in performance_metrics
    rejection_metrics = performance_metrics["rejection_metrics"]
    assert rejection_metrics["schema_version"] == 2
    assert rejection_metrics["rejected_call_count"] == 0
    assert rejection_metrics["rejection_breaker_count"] == 0
    stats_block = performance_metrics["statistics"]["rejection_metrics"]
    assert stats_block["schema_version"] == 2
