"""Tests for setup package exports."""

from custom_components.pawcontrol import setup
from custom_components.pawcontrol.setup import (
    cleanup,
    manager_init,
    platform_setup,
    validation,
)


def test_setup_package_exports_match_module_helpers() -> None:
    """The setup package should re-export the public setup helpers."""
    assert setup.__all__ == [
        "async_initialize_managers",
        "async_setup_platforms",
        "async_validate_entry_config",
        "async_cleanup_runtime_data",
        "async_register_cleanup",
    ]
    assert setup.async_initialize_managers is manager_init.async_initialize_managers
    assert setup.async_setup_platforms is platform_setup.async_setup_platforms
    assert setup.async_validate_entry_config is validation.async_validate_entry_config
    assert setup.async_cleanup_runtime_data is cleanup.async_cleanup_runtime_data
    assert setup.async_register_cleanup is cleanup.async_register_cleanup
