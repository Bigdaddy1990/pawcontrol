"""Entity helper stubs for tests."""
from enum import Enum

class EntityCategory(str, Enum):
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
