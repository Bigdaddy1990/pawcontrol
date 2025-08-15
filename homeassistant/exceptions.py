"""Minimal exceptions for Home Assistant stubs."""

class HomeAssistantError(Exception):
    """Base error for Home Assistant stub."""
    pass


class ConfigEntryNotReady(HomeAssistantError):
    """Raised when a config entry isn't ready during startup."""


class ServiceValidationError(HomeAssistantError):
    """Raised when service data fails validation."""
