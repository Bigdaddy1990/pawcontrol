"""Minimal constants for Home Assistant stubs."""
from enum import Enum

class Platform(str, Enum):
    """Enumeration of core platforms used in tests."""
    BINARY_SENSOR = "binary_sensor"
    SENSOR = "sensor"
    SWITCH = "switch"
    BUTTON = "button"
    NUMBER = "number"
    SELECT = "select"
    TEXT = "text"
    DEVICE_TRACKER = "device_tracker"
