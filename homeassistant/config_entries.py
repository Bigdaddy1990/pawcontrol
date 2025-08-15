"""Minimal config_entries stub for Home Assistant tests."""
from enum import Enum

class ConfigEntryState(Enum):
    NOT_LOADED = "not_loaded"
    LOADED = "loaded"

class ConfigEntry:
    def __init__(self, *, domain: str, data: dict | None = None, options: dict | None = None):
        self.domain = domain
        self.data = data or {}
        self.options = options or {}
        self.state = ConfigEntryState.NOT_LOADED
