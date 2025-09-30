"""Domain orchestration helpers for PawControl."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import CONF_MODULES
from ..exceptions import GPSUnavailableError, NetworkError
from ..module_adapters import CoordinatorModuleAdapters
from .models import DomainSnapshot, ModuleSnapshot

_DEFAULT_MODULE_KEYS: tuple[str, ...] = (
    "feeding",
    "walk",
    "gps",
    "geofencing",
    "health",
    "weather",
    "garden",
)

ModuleNormalizer = Callable[[str, Any, str], ModuleSnapshot | Mapping[str, Any]]


class DogDomainOrchestrator:
    """Encapsulate cross-module domain orchestration for dogs."""

    def __init__(
        self,
        adapters: CoordinatorModuleAdapters,
        *,
        logger: logging.Logger | None = None,
        time_provider: Callable[[], datetime] | None = None,
        module_keys: tuple[str, ...] | None = None,
        normalizers: Mapping[str, ModuleNormalizer] | None = None,
    ) -> None:
        self._adapters = adapters
        self._logger = logger or logging.getLogger(__name__)
        self._time_provider = time_provider or dt_util.utcnow
        self._module_keys = module_keys or _DEFAULT_MODULE_KEYS
        self._normalizers: dict[str, ModuleNormalizer] = dict(normalizers or {})

    def register_normalizer(self, module: str, normalizer: ModuleNormalizer) -> None:
        """Register or override a module normalizer."""

        self._normalizers[module] = normalizer

    async def async_build_snapshot(
        self,
        dog_id: str,
        dog_config: Mapping[str, Any],
    ) -> DomainSnapshot:
        """Create a runtime snapshot for a configured dog."""

        modules_config = dog_config.get(CONF_MODULES, {})
        tasks = self._adapters.build_tasks(dog_id, modules_config)
        modules: dict[str, ModuleSnapshot] = {
            key: ModuleSnapshot.empty(key, status="unavailable")
            for key in self._module_keys
        }

        if tasks:
            snapshots = await self._collect_module_snapshots(dog_id, tasks)
            modules.update(snapshots)

        snapshot = DomainSnapshot(
            dog_id=dog_id,
            status="online",
            dog_info=dog_config,
            modules=modules,
            last_updated=self._time_provider(),
            metadata={"module_order": list(self._module_keys)},
        )
        return snapshot

    def empty_snapshot(self, dog_id: str) -> DomainSnapshot:
        """Return a deterministic empty snapshot for fallback paths."""

        modules = {
            key: ModuleSnapshot.empty(key, status="unknown")
            for key in self._module_keys
        }
        return DomainSnapshot(
            dog_id=dog_id,
            status="unknown",
            dog_info={},
            modules=modules,
            metadata={"module_order": list(self._module_keys)},
        )

    async def _collect_module_snapshots(
        self,
        dog_id: str,
        tasks: list[tuple[str, Awaitable[Any]]],
    ) -> dict[str, ModuleSnapshot]:
        """Execute module tasks and normalize their payloads."""

        results: dict[str, ModuleSnapshot] = {}
        task_handles: dict[str, asyncio.Task[ModuleSnapshot]] = {}

        async with asyncio.TaskGroup() as task_group:
            for module_name, awaitable in tasks:
                task_handles[module_name] = task_group.create_task(
                    self._execute_module_task(module_name, awaitable, dog_id)
                )

        for module_name, task in task_handles.items():
            try:
                results[module_name] = task.result()
            except Exception as err:  # pragma: no cover - defensive
                self._logger.error(
                    "Unexpected orchestration failure for module %s of dog %s: %s",
                    module_name,
                    dog_id,
                    err,
                )
                results[module_name] = ModuleSnapshot.empty(module_name, status="error")

        return results

    async def _execute_module_task(
        self,
        module_name: str,
        awaitable: Awaitable[Any],
        dog_id: str,
    ) -> ModuleSnapshot:
        """Execute a single module task and normalize its outcome."""

        started_at = self._time_provider()
        try:
            result = await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            return self._normalize_exception(module_name, err, dog_id, started_at)
        return self._normalize_success(module_name, result, dog_id, started_at)

    def _normalize_success(
        self,
        module_name: str,
        result: Any,
        dog_id: str,
        started_at: datetime,
    ) -> ModuleSnapshot:
        """Normalize a successful module payload."""

        finished_at = self._time_provider()
        latency = (finished_at - started_at).total_seconds()

        if normalizer := self._normalizers.get(module_name):
            try:
                normalized = normalizer(module_name, result, dog_id)
            except Exception as err:  # pragma: no cover - defensive logging
                self._logger.error(
                    "Normalizer for %s failed on dog %s: %s",
                    module_name,
                    dog_id,
                    err,
                )
                return ModuleSnapshot(
                    name=module_name,
                    status="normalizer_error",
                    error=str(err),
                    received_at=finished_at,
                    latency=latency,
                )

            if isinstance(normalized, ModuleSnapshot):
                return normalized.with_defaults(
                    name=module_name,
                    fallback_status="ready",
                    received_at=finished_at,
                    latency=latency,
                )

            if isinstance(normalized, Mapping):
                payload = dict(normalized)
                status = str(payload.get("status", "ready"))
                error = payload.get("error")
                return ModuleSnapshot(
                    name=module_name,
                    status=status,
                    payload=payload,
                    error=str(error) if error is not None else None,
                    received_at=finished_at,
                    latency=latency,
                )

            self._logger.debug(
                "Normalizer for %s returned unsupported payload %r",
                module_name,
                normalized,
            )

        if isinstance(result, Mapping):
            payload = dict(result)
            status = str(payload.get("status", "ready"))
            error_value = payload.get("error")
            return ModuleSnapshot(
                name=module_name,
                status=status,
                payload=payload,
                error=str(error_value) if error_value is not None else None,
                received_at=finished_at,
                latency=latency,
            )

        self._logger.debug(
            "Module %s for dog %s returned unexpected payload %r",
            module_name,
            dog_id,
            result,
        )
        return ModuleSnapshot(
            name=module_name,
            status="invalid",
            payload={"raw": result},
            received_at=finished_at,
            latency=latency,
        )

    def _normalize_exception(
        self,
        module_name: str,
        error: Exception,
        dog_id: str,
        started_at: datetime,
    ) -> ModuleSnapshot:
        """Normalize an exception raised by a module payload."""

        finished_at = self._time_provider()
        latency = (finished_at - started_at).total_seconds()

        if isinstance(error, GPSUnavailableError):
            self._logger.debug("GPS unavailable for dog %s: %s", dog_id, error)
            return ModuleSnapshot(
                name=module_name,
                status="unavailable",
                payload={"reason": str(error)},
                error=str(error),
                received_at=finished_at,
                latency=latency,
            )

        if isinstance(error, NetworkError):
            self._logger.warning(
                "Network error fetching %s for dog %s: %s",
                module_name,
                dog_id,
                error,
            )
            return ModuleSnapshot(
                name=module_name,
                status="network_error",
                error=str(error),
                received_at=finished_at,
                latency=latency,
            )

        self._logger.warning(
            "Module %s for dog %s failed: %s (%s)",
            module_name,
            dog_id,
            error,
            error.__class__.__name__,
        )
        return ModuleSnapshot(
            name=module_name,
            status="error",
            error=str(error),
            received_at=finished_at,
            latency=latency,
        )


# Keep backwards compatibility: modules may rely on the constant tuple of keys.
MODULE_KEYS = _DEFAULT_MODULE_KEYS
