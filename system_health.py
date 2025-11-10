"""System health entry point for local tooling."""

from __future__ import annotations

from custom_components.pawcontrol import system_health as _integration_system_health

async_register = _integration_system_health.async_register
system_health_info = _integration_system_health.system_health_info

__all__ = ["async_register", "system_health_info"]
