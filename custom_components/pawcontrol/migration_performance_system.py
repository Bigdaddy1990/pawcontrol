"""Migration and Performance Monitoring System for Paw Control.

This module provides comprehensive migration support and performance monitoring
for the Paw Control integration, ensuring smooth upgrades and optimal performance.

Key features:
- Configuration migration between versions
- Performance monitoring and optimization
- Health checks and diagnostics
- Data validation and repair
- Backup and restore functionality
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import storage

from .const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_GPS,
    MODULE_FEEDING,
    MODULE_HEALTH,
)

_LOGGER = logging.getLogger(__name__)

# Migration version constants
MIGRATION_VERSION_1_0 = "1.0.0"
MIGRATION_VERSION_1_1 = "1.1.0"
MIGRATION_VERSION_1_2 = "1.2.0"
MIGRATION_VERSION_1_3 = "1.3.0"
CURRENT_VERSION = MIGRATION_VERSION_1_3

# Storage keys
STORAGE_KEY_MIGRATION = "pawcontrol_migration"
STORAGE_KEY_PERFORMANCE = "pawcontrol_performance"


@dataclass
class MigrationResult:
    """Result of a migration operation."""
    success: bool
    version_from: str
    version_to: str
    changes_made: List[str]
    warnings: List[str]
    errors: List[str]
    duration_ms: float


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring."""
    timestamp: datetime
    config_entry_id: str
    entities_count: int
    dogs_count: int
    update_duration_ms: float
    memory_usage_mb: float
    error_count: int
    last_error: Optional[str]
    gps_points_processed: int
    notifications_sent: int


class ConfigMigrator:
    """Handle configuration migrations between versions."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the migrator."""
        self.hass = hass
        self._migration_storage = storage.Store(hass, 1, STORAGE_KEY_MIGRATION)

    async def migrate_config_entry(
        self, config_entry: ConfigEntry, target_version: str = CURRENT_VERSION
    ) -> MigrationResult:
        """Migrate a config entry to the target version.
        
        Args:
            config_entry: The config entry to migrate
            target_version: Target version to migrate to
            
        Returns:
            Migration result with details
        """
        start_time = time.time()
        current_version = config_entry.data.get("version", MIGRATION_VERSION_1_0)
        
        result = MigrationResult(
            success=False,
            version_from=current_version,
            version_to=target_version,
            changes_made=[],
            warnings=[],
            errors=[],
            duration_ms=0.0,
        )
        
        try:
            if current_version == target_version:
                result.success = True
                result.warnings.append("Already at target version")
                return result

            # Perform step-by-step migration
            migration_path = self._get_migration_path(current_version, target_version)
            
            if not migration_path:
                result.errors.append(f"No migration path from {current_version} to {target_version}")
                return result

            # Create backup before migration
            backup_data = await self._create_migration_backup(config_entry)
            
            # Apply migrations in sequence
            current_data = dict(config_entry.data)
            current_options = dict(config_entry.options)
            
            for from_version, to_version in migration_path:
                migration_func = self._get_migration_function(from_version, to_version)
                if migration_func:
                    try:
                        migration_result = await migration_func(current_data, current_options)
                        current_data = migration_result["data"]
                        current_options = migration_result["options"]
                        result.changes_made.extend(migration_result.get("changes", []))
                        result.warnings.extend(migration_result.get("warnings", []))
                        
                        _LOGGER.info("Migrated from %s to %s", from_version, to_version)
                        
                    except Exception as err:
                        result.errors.append(f"Migration {from_version} -> {to_version} failed: {err}")
                        _LOGGER.error("Migration failed: %s", err)
                        
                        # Restore from backup on error
                        await self._restore_from_backup(config_entry, backup_data)
                        return result

            # Update the config entry with migrated data
            current_data["version"] = target_version
            self.hass.config_entries.async_update_entry(
                config_entry,
                data=current_data,
                options=current_options,
            )
            
            result.success = True
            result.changes_made.append(f"Updated version to {target_version}")
            
            # Store migration record
            await self._store_migration_record(config_entry.entry_id, result)
            
        except Exception as err:
            result.errors.append(f"Migration failed: {err}")
            _LOGGER.exception("Config migration failed")
        
        finally:
            result.duration_ms = (time.time() - start_time) * 1000
            
        return result

    def _get_migration_path(self, from_version: str, to_version: str) -> List[tuple[str, str]]:
        """Get the migration path between versions."""
        version_order = [
            MIGRATION_VERSION_1_0,
            MIGRATION_VERSION_1_1,
            MIGRATION_VERSION_1_2,
            MIGRATION_VERSION_1_3,
        ]
        
        try:
            from_index = version_order.index(from_version)
            to_index = version_order.index(to_version)
        except ValueError:
            return []
        
        if from_index >= to_index:
            return []
        
        # Create step-by-step path
        path = []
        for i in range(from_index, to_index):
            path.append((version_order[i], version_order[i + 1]))
        
        return path

    def _get_migration_function(self, from_version: str, to_version: str) -> Optional[Callable]:
        """Get the migration function for a specific version transition."""
        migration_map = {
            (MIGRATION_VERSION_1_0, MIGRATION_VERSION_1_1): self._migrate_1_0_to_1_1,
            (MIGRATION_VERSION_1_1, MIGRATION_VERSION_1_2): self._migrate_1_1_to_1_2,
            (MIGRATION_VERSION_1_2, MIGRATION_VERSION_1_3): self._migrate_1_2_to_1_3,
        }
        
        return migration_map.get((from_version, to_version))

    async def _migrate_1_0_to_1_1(
        self, data: Dict[str, Any], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Migrate from version 1.0 to 1.1."""
        changes = []
        warnings = []
        
        # Add dog modules if not present
        if CONF_DOGS in data:
            for dog in data[CONF_DOGS]:
                if "modules" not in dog:
                    dog["modules"] = {
                        MODULE_GPS: True,
                        MODULE_FEEDING: True,
                        MODULE_HEALTH: True,
                    }
                    changes.append(f"Added default modules for dog {dog.get(CONF_DOG_NAME, 'unknown')}")
        
        # Add notification settings if not present
        if "notifications" not in options:
            options["notifications"] = {
                "enabled": True,
                "quiet_hours_enabled": False,
                "quiet_start": "22:00",
                "quiet_end": "07:00",
            }
            changes.append("Added default notification settings")
        
        return {
            "data": data,
            "options": options,
            "changes": changes,
            "warnings": warnings,
        }

    async def _migrate_1_1_to_1_2(
        self, data: Dict[str, Any], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Migrate from version 1.1 to 1.2."""
        changes = []
        warnings = []
        
        # Add GPS settings structure
        if "gps" not in options:
            options["gps"] = {
                "enabled": True,
                "accuracy_filter": 100,
                "distance_filter": 5,
                "auto_start_walk": False,
                "auto_end_walk": True,
                "route_recording": True,
            }
            changes.append("Added GPS configuration structure")
        
        # Migrate old geofence settings to new structure
        if "geofence_enabled" in options:
            geofence_data = {
                "geofencing_enabled": options.pop("geofence_enabled", True),
                "geofence_lat": options.pop("geofence_lat", 0.0),
                "geofence_lon": options.pop("geofence_lon", 0.0),
                "geofence_radius_m": options.pop("geofence_radius_m", 150),
                "geofence_alerts_enabled": options.pop("geofence_alerts", True),
            }
            options.update(geofence_data)
            changes.append("Migrated geofence settings to new structure")
        
        return {
            "data": data,
            "options": options,
            "changes": changes,
            "warnings": warnings,
        }

    async def _migrate_1_2_to_1_3(
        self, data: Dict[str, Any], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Migrate from version 1.2 to 1.3."""
        changes = []
        warnings = []
        
        # Add data sources configuration
        if "data_sources" not in options:
            options["data_sources"] = {
                "person_entities": [],
                "device_trackers": [],
                "door_sensor": "",
                "weather": "",
                "calendar": "",
                "auto_discovery": True,
                "fallback_tracking": True,
            }
            changes.append("Added data sources configuration")
        
        # Add system settings
        if "system" not in options:
            options["system"] = {
                "reset_time": "23:59:00",
                "visitor_mode": False,
                "export_format": "csv",
                "auto_prune_devices": True,
                "performance_mode": "balanced",
                "log_level": "info",
                "data_retention_days": 365,
            }
            changes.append("Added system configuration")
        
        # Add maintenance settings
        if "maintenance" not in options:
            options["maintenance"] = {
                "auto_backup_enabled": True,
                "backup_interval_days": 7,
                "auto_cleanup_enabled": True,
                "cleanup_interval_days": 30,
            }
            changes.append("Added maintenance configuration")
        
        # Validate and repair dog configurations
        if CONF_DOGS in data:
            for dog in data[CONF_DOGS]:
                # Ensure all required fields are present
                if CONF_DOG_ID not in dog:
                    dog_id = dog.get(CONF_DOG_NAME, "unknown").lower().replace(" ", "_")
                    dog[CONF_DOG_ID] = dog_id
                    warnings.append(f"Generated dog ID '{dog_id}' for dog without ID")
                
                # Ensure modules are complete
                default_modules = {
                    MODULE_GPS: True,
                    MODULE_FEEDING: True,
                    MODULE_HEALTH: True,
                    "walk": True,
                    "grooming": True,
                    "training": True,
                    "medication": True,
                    "notifications": True,
                    "dashboard": True,
                }
                
                if "modules" not in dog:
                    dog["modules"] = default_modules
                    changes.append(f"Added complete module configuration for {dog[CONF_DOG_NAME]}")
                else:
                    for module, default_value in default_modules.items():
                        if module not in dog["modules"]:
                            dog["modules"][module] = default_value
                            changes.append(f"Added missing module '{module}' for {dog[CONF_DOG_NAME]}")
        
        return {
            "data": data,
            "options": options,
            "changes": changes,
            "warnings": warnings,
        }

    async def _create_migration_backup(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Create a backup before migration."""
        backup_data = {
            "timestamp": datetime.now().isoformat(),
            "entry_id": config_entry.entry_id,
            "title": config_entry.title,
            "data": dict(config_entry.data),
            "options": dict(config_entry.options),
            "version": config_entry.version,
        }
        
        # Store backup
        backup_storage = storage.Store(
            self.hass, 1, f"pawcontrol_migration_backup_{config_entry.entry_id}"
        )
        await backup_storage.async_save(backup_data)
        
        return backup_data

    async def _restore_from_backup(self, config_entry: ConfigEntry, backup_data: Dict[str, Any]) -> None:
        """Restore config entry from backup."""
        self.hass.config_entries.async_update_entry(
            config_entry,
            data=backup_data["data"],
            options=backup_data["options"],
        )
        _LOGGER.warning("Restored config entry from backup due to migration failure")

    async def _store_migration_record(self, entry_id: str, result: MigrationResult) -> None:
        """Store migration record for future reference."""
        migration_data = await self._migration_storage.async_load() or {}
        
        if entry_id not in migration_data:
            migration_data[entry_id] = []
        
        migration_data[entry_id].append({
            "timestamp": datetime.now().isoformat(),
            "result": asdict(result),
        })
        
        # Keep only last 10 migration records per entry
        migration_data[entry_id] = migration_data[entry_id][-10:]
        
        await self._migration_storage.async_save(migration_data)

    async def get_migration_history(self, entry_id: str) -> List[Dict[str, Any]]:
        """Get migration history for a config entry."""
        migration_data = await self._migration_storage.async_load() or {}
        return migration_data.get(entry_id, [])


class PerformanceMonitor:
    """Monitor and optimize performance of the Paw Control integration."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the performance monitor."""
        self.hass = hass
        self._performance_storage = storage.Store(hass, 1, STORAGE_KEY_PERFORMANCE)
        self._metrics_cache: Dict[str, PerformanceMetrics] = {}
        self._monitoring_active = False

    async def start_monitoring(self, config_entry: ConfigEntry) -> None:
        """Start performance monitoring for a config entry."""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        _LOGGER.info("Started performance monitoring for %s", config_entry.entry_id)
        
        # Schedule periodic performance collection
        async def collect_metrics():
            while self._monitoring_active:
                try:
                    await self._collect_performance_metrics(config_entry)
                    await asyncio.sleep(300)  # Collect every 5 minutes
                except Exception as err:
                    _LOGGER.error("Performance metrics collection failed: %s", err)
                    await asyncio.sleep(60)  # Retry in 1 minute
        
        asyncio.create_task(collect_metrics())

    async def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        self._monitoring_active = False
        _LOGGER.info("Stopped performance monitoring")

    async def _collect_performance_metrics(self, config_entry: ConfigEntry) -> None:
        """Collect current performance metrics."""
        start_time = time.time()
        
        try:
            # Get entity count
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(self.hass)
            entities_count = len([
                entity for entity in ent_reg.entities.values()
                if entity.platform == DOMAIN
            ])
            
            # Get dogs count
            dogs_count = len(config_entry.data.get(CONF_DOGS, []))
            
            # Get memory usage (approximation)
            import psutil
            process = psutil.Process()
            memory_usage_mb = process.memory_info().rss / 1024 / 1024
            
            # Get error count from coordinator
            coordinator = self.hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
            error_count = 0
            last_error = None
            gps_points_processed = 0
            notifications_sent = 0
            
            if coordinator:
                error_count = getattr(coordinator, 'error_count', 0)
                last_error = getattr(coordinator, 'last_error', None)
                gps_points_processed = getattr(coordinator, 'gps_points_processed', 0)
                notifications_sent = getattr(coordinator, 'notifications_sent', 0)
            
            update_duration_ms = (time.time() - start_time) * 1000
            
            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                config_entry_id=config_entry.entry_id,
                entities_count=entities_count,
                dogs_count=dogs_count,
                update_duration_ms=update_duration_ms,
                memory_usage_mb=memory_usage_mb,
                error_count=error_count,
                last_error=str(last_error) if last_error else None,
                gps_points_processed=gps_points_processed,
                notifications_sent=notifications_sent,
            )
            
            # Cache metrics
            self._metrics_cache[config_entry.entry_id] = metrics
            
            # Store metrics
            await self._store_performance_metrics(metrics)
            
            # Check for performance issues
            await self._check_performance_issues(metrics)
            
        except Exception as err:
            _LOGGER.error("Failed to collect performance metrics: %s", err)

    async def _store_performance_metrics(self, metrics: PerformanceMetrics) -> None:
        """Store performance metrics to persistent storage."""
        try:
            performance_data = await self._performance_storage.async_load() or {}
            
            entry_id = metrics.config_entry_id
            if entry_id not in performance_data:
                performance_data[entry_id] = []
            
            # Convert metrics to dict for storage
            metrics_dict = asdict(metrics)
            metrics_dict["timestamp"] = metrics.timestamp.isoformat()
            
            performance_data[entry_id].append(metrics_dict)
            
            # Keep only last 100 entries per config entry
            performance_data[entry_id] = performance_data[entry_id][-100:]
            
            await self._performance_storage.async_save(performance_data)
            
        except Exception as err:
            _LOGGER.error("Failed to store performance metrics: %s", err)

    async def _check_performance_issues(self, metrics: PerformanceMetrics) -> None:
        """Check for performance issues and log warnings."""
        issues = []
        
        # Check update duration
        if metrics.update_duration_ms > 5000:  # 5 seconds
            issues.append(f"Slow update duration: {metrics.update_duration_ms:.1f}ms")
        
        # Check memory usage
        if metrics.memory_usage_mb > 500:  # 500 MB
            issues.append(f"High memory usage: {metrics.memory_usage_mb:.1f}MB")
        
        # Check error rate
        if metrics.error_count > 10:
            issues.append(f"High error count: {metrics.error_count}")
        
        # Check entity count
        if metrics.entities_count > 1000:
            issues.append(f"High entity count: {metrics.entities_count}")
        
        if issues:
            _LOGGER.warning("Performance issues detected for %s: %s", 
                          metrics.config_entry_id, "; ".join(issues))

    async def get_performance_metrics(self, entry_id: str) -> Optional[PerformanceMetrics]:
        """Get current performance metrics for a config entry."""
        return self._metrics_cache.get(entry_id)

    async def get_performance_history(
        self, 
        entry_id: str, 
        hours: int = 24
    ) -> List[PerformanceMetrics]:
        """Get performance history for a config entry."""
        try:
            performance_data = await self._performance_storage.async_load() or {}
            metrics_list = performance_data.get(entry_id, [])
            
            # Filter by time range
            cutoff_time = datetime.now() - timedelta(hours=hours)
            filtered_metrics = []
            
            for metrics_dict in metrics_list:
                timestamp = datetime.fromisoformat(metrics_dict["timestamp"])
                if timestamp >= cutoff_time:
                    # Convert back to PerformanceMetrics object
                    metrics_dict["timestamp"] = timestamp
                    filtered_metrics.append(PerformanceMetrics(**metrics_dict))
            
            return filtered_metrics
            
        except Exception as err:
            _LOGGER.error("Failed to get performance history: %s", err)
            return []

    async def generate_performance_report(self, entry_id: str) -> Dict[str, Any]:
        """Generate a comprehensive performance report."""
        try:
            # Get recent metrics
            history = await self.get_performance_history(entry_id, hours=24)
            current = await self.get_performance_metrics(entry_id)
            
            if not history:
                return {"error": "No performance data available"}
            
            # Calculate statistics
            update_durations = [m.update_duration_ms for m in history]
            memory_usage = [m.memory_usage_mb for m in history]
            error_counts = [m.error_count for m in history]
            
            report = {
                "entry_id": entry_id,
                "report_time": datetime.now().isoformat(),
                "data_points": len(history),
                "current_metrics": asdict(current) if current else None,
                "statistics": {
                    "avg_update_duration_ms": sum(update_durations) / len(update_durations),
                    "max_update_duration_ms": max(update_durations),
                    "min_update_duration_ms": min(update_durations),
                    "avg_memory_usage_mb": sum(memory_usage) / len(memory_usage),
                    "max_memory_usage_mb": max(memory_usage),
                    "total_errors": sum(error_counts),
                    "avg_gps_points": sum(m.gps_points_processed for m in history) / len(history),
                    "total_notifications": sum(m.notifications_sent for m in history),
                },
                "recommendations": self._generate_recommendations(history, current),
            }
            
            return report
            
        except Exception as err:
            _LOGGER.error("Failed to generate performance report: %s", err)
            return {"error": str(err)}

    def _generate_recommendations(
        self, 
        history: List[PerformanceMetrics], 
        current: Optional[PerformanceMetrics]
    ) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        if not history:
            return recommendations
        
        # Analyze update duration
        avg_duration = sum(m.update_duration_ms for m in history) / len(history)
        if avg_duration > 2000:
            recommendations.append(
                "Consider reducing update frequency or optimizing GPS tracking settings"
            )
        
        # Analyze memory usage
        avg_memory = sum(m.memory_usage_mb for m in history) / len(history)
        if avg_memory > 200:
            recommendations.append(
                "High memory usage detected. Consider reducing GPS route history retention"
            )
        
        # Analyze error rate
        total_errors = sum(m.error_count for m in history)
        if total_errors > 50:
            recommendations.append(
                "High error rate detected. Check device connectivity and GPS settings"
            )
        
        # Analyze entity count
        if current and current.entities_count > 500:
            recommendations.append(
                "Large number of entities. Consider disabling unused modules for some dogs"
            )
        
        # GPS-specific recommendations
        total_gps_points = sum(m.gps_points_processed for m in history)
        if total_gps_points > 10000:
            recommendations.append(
                "High GPS activity. Consider increasing distance filter or reducing update frequency"
            )
        
        if not recommendations:
            recommendations.append("Performance is within optimal ranges")
        
        return recommendations


class HealthChecker:
    """Perform health checks and diagnostics for the integration."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the health checker."""
        self.hass = hass

    async def perform_health_check(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "entry_id": config_entry.entry_id,
            "overall_status": "healthy",
            "checks": {},
        }
        
        try:
            # Check configuration validity
            config_check = await self._check_configuration(config_entry)
            health_report["checks"]["configuration"] = config_check
            
            # Check coordinator status
            coordinator_check = await self._check_coordinator_status(config_entry)
            health_report["checks"]["coordinator"] = coordinator_check
            
            # Check entity status
            entity_check = await self._check_entity_status(config_entry)
            health_report["checks"]["entities"] = entity_check
            
            # Check GPS functionality
            gps_check = await self._check_gps_functionality(config_entry)
            health_report["checks"]["gps"] = gps_check
            
            # Check data sources
            sources_check = await self._check_data_sources(config_entry)
            health_report["checks"]["data_sources"] = sources_check
            
            # Determine overall status
            all_checks = [
                config_check["status"],
                coordinator_check["status"],
                entity_check["status"],
                gps_check["status"],
                sources_check["status"],
            ]
            
            if "error" in all_checks:
                health_report["overall_status"] = "error"
            elif "warning" in all_checks:
                health_report["overall_status"] = "warning"
            else:
                health_report["overall_status"] = "healthy"
                
        except Exception as err:
            health_report["overall_status"] = "error"
            health_report["error"] = str(err)
            _LOGGER.error("Health check failed: %s", err)
        
        return health_report

    async def _check_configuration(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Check configuration validity."""
        check_result = {
            "status": "healthy",
            "issues": [],
            "details": {},
        }
        
        try:
            # Check dogs configuration
            dogs = config_entry.data.get(CONF_DOGS, [])
            check_result["details"]["dogs_count"] = len(dogs)
            
            if not dogs:
                check_result["status"] = "warning"
                check_result["issues"].append("No dogs configured")
            
            # Check for duplicate dog IDs
            dog_ids = [dog.get(CONF_DOG_ID) for dog in dogs]
            if len(dog_ids) != len(set(dog_ids)):
                check_result["status"] = "error"
                check_result["issues"].append("Duplicate dog IDs detected")
            
            # Check options structure
            options = config_entry.options
            required_sections = ["notifications", "gps", "data_sources"]
            missing_sections = [s for s in required_sections if s not in options]
            
            if missing_sections:
                check_result["status"] = "warning"
                check_result["issues"].append(f"Missing configuration sections: {missing_sections}")
            
        except Exception as err:
            check_result["status"] = "error"
            check_result["issues"].append(f"Configuration check failed: {err}")
        
        return check_result

    async def _check_coordinator_status(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Check coordinator status."""
        check_result = {
            "status": "healthy",
            "issues": [],
            "details": {},
        }
        
        try:
            coordinator = self.hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
            
            if not coordinator:
                check_result["status"] = "error"
                check_result["issues"].append("Coordinator not found")
                return check_result
            
            # Check coordinator availability
            if not coordinator.available:
                check_result["status"] = "error"
                check_result["issues"].append("Coordinator unavailable")
            
            # Check last update
            if hasattr(coordinator, 'last_update'):
                last_update = coordinator.last_update
                if last_update:
                    time_since_update = datetime.now() - last_update
                    check_result["details"]["last_update"] = last_update.isoformat()
                    check_result["details"]["time_since_update_seconds"] = time_since_update.total_seconds()
                    
                    if time_since_update.total_seconds() > 3600:  # 1 hour
                        check_result["status"] = "warning"
                        check_result["issues"].append("Coordinator hasn't updated in over an hour")
            
            # Check error count
            if hasattr(coordinator, 'error_count'):
                error_count = coordinator.error_count
                check_result["details"]["error_count"] = error_count
                
                if error_count > 10:
                    check_result["status"] = "warning"
                    check_result["issues"].append(f"High error count: {error_count}")
            
        except Exception as err:
            check_result["status"] = "error"
            check_result["issues"].append(f"Coordinator check failed: {err}")
        
        return check_result

    async def _check_entity_status(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Check entity status."""
        check_result = {
            "status": "healthy",
            "issues": [],
            "details": {},
        }
        
        try:
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(self.hass)
            
            # Count entities by platform
            entities = [
                entity for entity in ent_reg.entities.values()
                if entity.platform == DOMAIN
            ]
            
            check_result["details"]["total_entities"] = len(entities)
            
            # Check for disabled entities
            disabled_entities = [e for e in entities if e.disabled]
            check_result["details"]["disabled_entities"] = len(disabled_entities)
            
            if len(disabled_entities) > 0:
                check_result["status"] = "warning"
                check_result["issues"].append(f"{len(disabled_entities)} entities are disabled")
            
            # Check entity states
            unavailable_count = 0
            for entity in entities:
                state = self.hass.states.get(entity.entity_id)
                if state and state.state == "unavailable":
                    unavailable_count += 1
            
            check_result["details"]["unavailable_entities"] = unavailable_count
            
            if unavailable_count > 0:
                check_result["status"] = "warning"
                check_result["issues"].append(f"{unavailable_count} entities are unavailable")
            
        except Exception as err:
            check_result["status"] = "error"
            check_result["issues"].append(f"Entity check failed: {err}")
        
        return check_result

    async def _check_gps_functionality(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Check GPS functionality."""
        check_result = {
            "status": "healthy",
            "issues": [],
            "details": {},
        }
        
        try:
            gps_options = config_entry.options.get("gps", {})
            
            if not gps_options.get("enabled", True):
                check_result["status"] = "warning"
                check_result["issues"].append("GPS tracking is disabled")
                return check_result
            
            # Check GPS settings
            accuracy_filter = gps_options.get("accuracy_filter", 100)
            if accuracy_filter > 500:
                check_result["status"] = "warning"
                check_result["issues"].append("GPS accuracy filter is set very high")
            
            check_result["details"]["gps_enabled"] = True
            check_result["details"]["accuracy_filter"] = accuracy_filter
            check_result["details"]["route_recording"] = gps_options.get("route_recording", True)
            
        except Exception as err:
            check_result["status"] = "error"
            check_result["issues"].append(f"GPS check failed: {err}")
        
        return check_result

    async def _check_data_sources(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Check data sources availability."""
        check_result = {
            "status": "healthy",
            "issues": [],
            "details": {},
        }
        
        try:
            data_sources = config_entry.options.get("data_sources", {})
            
            # Check person entities
            person_entities = data_sources.get("person_entities", [])
            check_result["details"]["person_entities_count"] = len(person_entities)
            
            # Verify person entities exist
            for entity_id in person_entities:
                state = self.hass.states.get(entity_id)
                if not state:
                    check_result["status"] = "warning"
                    check_result["issues"].append(f"Person entity not found: {entity_id}")
            
            # Check device trackers
            device_trackers = data_sources.get("device_trackers", [])
            check_result["details"]["device_trackers_count"] = len(device_trackers)
            
            # Verify device trackers exist
            for entity_id in device_trackers:
                state = self.hass.states.get(entity_id)
                if not state:
                    check_result["status"] = "warning"
                    check_result["issues"].append(f"Device tracker not found: {entity_id}")
            
            # Check door sensor
            door_sensor = data_sources.get("door_sensor")
            if door_sensor:
                state = self.hass.states.get(door_sensor)
                if not state:
                    check_result["status"] = "warning"
                    check_result["issues"].append(f"Door sensor not found: {door_sensor}")
                else:
                    check_result["details"]["door_sensor_available"] = True
            
        except Exception as err:
            check_result["status"] = "error"
            check_result["issues"].append(f"Data sources check failed: {err}")
        
        return check_result