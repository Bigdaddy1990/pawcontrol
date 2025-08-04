"""Registry and helpers for optional Paw Control modules.

This module coordinates setup, teardown, and helper creation for each optional
module. Errors raised during these steps by individual modules are logged and
do not prevent subsequent modules from running, keeping setup and teardown
resilient.

Teardown handlers are invoked only when a module is explicitly disabled in the
options. Modules that default to off and are omitted from the options are left
untouched.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import gps, health, push, walk
from .const import (
    CONF_GPS_ENABLE,
    CONF_HEALTH_MODULE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_WALK_MODULE,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

ModuleFunc = Callable[..., Awaitable[None]]


@dataclass
class Module:
    """Container for module handlers."""

    setup: ModuleFunc
    teardown: ModuleFunc | None = None
    ensure_helpers: ModuleFunc | None = None
    default: bool = True


MODULES: dict[str, Module] = {
    CONF_GPS_ENABLE: Module(
        setup=gps.setup_gps,
        teardown=gps.teardown_gps,
        ensure_helpers=gps.ensure_helpers,
        default=True,
    ),
    CONF_NOTIFICATIONS_ENABLED: Module(
        setup=push.setup_push,
        teardown=push.teardown_push,
        default=True,
    ),
    CONF_HEALTH_MODULE: Module(
        setup=health.setup_health,
        teardown=health.teardown_health,
        ensure_helpers=health.ensure_helpers,
        default=True,
    ),
    CONF_WALK_MODULE: Module(
        setup=walk.setup_walk,
        teardown=walk.teardown_walk,
        ensure_helpers=walk.ensure_helpers,
        default=True,
    ),
}

_LOGGER = logging.getLogger(__name__)


async def _call_module_func(
    func: ModuleFunc | None,
    log_msg: str,
    log_args: tuple[Any, ...],
    *call_args: Any,
) -> None:
    """Call ``func`` and log any exception.

    This helper centralises the ``try/except`` pattern used throughout this
    module.  It keeps the logging consistent and makes the calling code easier
    to read.  ``log_msg`` and ``log_args`` are passed directly to
    :func:`logging.Logger.exception` when an error occurs.
    """

    if not func:
        return

    try:
        await func(*call_args)
    except Exception:  # pragma: no cover - defensive programming
        _LOGGER.exception(log_msg, *log_args)


async def ensure_helpers(hass: HomeAssistant, opts: dict[str, bool]) -> None:
    """Ensure helpers for all enabled modules.

    Errors from individual modules are logged but do not halt processing.
    """
    for key, module in MODULES.items():
        if opts.get(key, module.default):
            await _call_module_func(
                module.ensure_helpers,
                "Error ensuring helpers for module %s",
                (key,),
                hass,
                opts,
            )


async def setup_modules(
    hass: HomeAssistant, entry: ConfigEntry, opts: dict[str, bool]
) -> None:
    """Set up or tear down modules based on options.

    Setup errors for individual modules are logged and other modules continue.
    Teardown handlers run only for modules explicitly present in ``opts`` with a
    value of ``False``; modules that default to off and are omitted are skipped.
    """
    for key, module in MODULES.items():
        enabled = opts.get(key, module.default)
        if enabled:
            await _call_module_func(
                module.setup,
                "Error %s module %s",
                ("setting up", key),
                hass,
                entry,
            )
        elif key in opts:
            await _call_module_func(
                module.teardown,
                "Error %s module %s",
                ("tearing down", key),
                hass,
                entry,
            )


async def unload_modules(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Unload all modules that define a teardown handler.

    Errors during teardown are logged to avoid interrupting unloading.
    """
    for key, module in MODULES.items():
        await _call_module_func(
            module.teardown,
            "Error tearing down module %s",
            (key,),
            hass,
            entry,
        )


# Backwards compatible aliases used by the tests and legacy code
async_ensure_helpers = ensure_helpers
async_setup_modules = setup_modules
async_unload_modules = unload_modules

__all__ = [
    "MODULES",
    "Module",
    "async_ensure_helpers",
    "async_setup_modules",
    "async_unload_modules",
]

