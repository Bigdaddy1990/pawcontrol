"""Typed runtime data structures for Paw Control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .coordinator import PawControlCoordinator
from .gps_handler import PawControlGPSHandler
from .helpers.scheduler import PawControlScheduler
from .helpers.setup_sync import SetupSync
from .report_generator import ReportGenerator
from .services import ServiceManager


@dataclass
class PawRuntimeData:
    """Aggregated, typed runtime data stored on the config entry."""

    coordinator: PawControlCoordinator
    gps_handler: PawControlGPSHandler
    setup_sync: SetupSync
    report_generator: ReportGenerator
    services: ServiceManager
    notification_router: Any  # Type imported dynamically to avoid circular imports
    scheduler: PawControlScheduler | None = None
