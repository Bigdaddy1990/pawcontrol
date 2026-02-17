"""Setup modules for PawControl integration.

This package contains modularized setup logic extracted from __init__.py
to improve maintainability, testability, and code clarity.

Modules:
    manager_init: Manager initialization and configuration
    platform_setup: Platform forwarding and entity setup
    validation: Configuration validation and normalization
    cleanup: Resource cleanup and shutdown logic
"""

from .cleanup import async_cleanup_runtime_data, async_register_cleanup
from .manager_init import async_initialize_managers
from .platform_setup import async_setup_platforms
from .validation import async_validate_entry_config

__all__ = [
    "async_initialize_managers",
    "async_setup_platforms",
    "async_validate_entry_config",
    "async_cleanup_runtime_data",
    "async_register_cleanup",
]
