"""Platform setup and forwarding for PawControl.

Extracted from __init__.py to isolate platform-related logic.
Handles platform forwarding, helper creation, and script generation.
"""

import asyncio
from collections.abc import Collection, Mapping
import inspect
import logging
import time
from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError

from ..const import PLATFORMS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..types import PawControlConfigEntry, PawControlRuntimeData
_LOGGER = logging.getLogger(__name__)

# Timeouts for platform operations
_PLATFORM_SETUP_TIMEOUT: int = 30  # seconds
_HELPER_CREATION_TIMEOUT: int = 20  # seconds
_SCRIPT_CREATION_TIMEOUT: int = 20  # seconds


def _resolve_enabled_modules(
    options: object | None,
) -> Collection[str] | Mapping[str, bool]:
    """Return enabled module data in the shape expected by managers."""
    if not isinstance(options, Mapping):
        return frozenset()
    raw: object = options.get("enabled_modules", frozenset())
    if isinstance(raw, Mapping):
        return {str(key): bool(value) for key, value in raw.items()}
    if isinstance(raw, Collection) and not isinstance(raw, str | bytes):
        return frozenset(str(item) for item in raw)
    return frozenset()


async def async_setup_platforms(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    runtime_data: PawControlRuntimeData,
) -> None:
    """Set up all platforms for PawControl.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        runtime_data: Runtime data with managers

    Raises:
        ConfigEntryNotReady: If platform setup fails after retries
    """
    # Forward entry setup to all platforms
    await _async_forward_platforms(hass, entry)
    # Create helpers and scripts if not skipped
    options = runtime_data.config_entry_options
    skip_optional = (
        bool(options.get("skip_optional_setup", False)) if options else False
    )
    if not skip_optional:
        await _async_setup_helpers(hass, entry, runtime_data)
        await _async_setup_scripts(hass, entry, runtime_data)


async def _async_forward_platforms(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
) -> None:
    """Forward entry setup to all platforms with retry logic.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Raises:
        ConfigEntryNotReady: If all retry attempts fail
    """
    from homeassistant.exceptions import ConfigEntryNotReady

    platform_setup_start = time.monotonic()
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            forward_callable = hass.config_entries.async_forward_entry_setups
            forward_result = forward_callable(entry, PLATFORMS)
            # async_forward_entry_setups always returns an awaitable in HA 2024+.
            # Use inspect.isawaitable for a correct runtime check rather than
            # the misleading hasattr("__await__") guard that was here before.
            if inspect.isawaitable(forward_result):
                await asyncio.wait_for(forward_result, timeout=_PLATFORM_SETUP_TIMEOUT)

            platform_setup_duration = time.monotonic() - platform_setup_start
            _LOGGER.debug(
                "Platform setup completed in %.2f seconds (attempt %d)",
                platform_setup_duration,
                attempt + 1,
            )
            return
        except TimeoutError as err:
            if attempt == max_retries:
                platform_setup_duration = time.monotonic() - platform_setup_start
                raise ConfigEntryNotReady(
                    f"Platform setup timeout after {platform_setup_duration:.2f}s",
                ) from err
            _LOGGER.warning(
                "Platform setup attempt %d timed out, retrying",
                attempt + 1,
            )
            await asyncio.sleep(1)
        except ImportError as err:
            raise ConfigEntryNotReady(
                f"Platform import failed - missing dependency: {err}",
            ) from err

        except Exception as err:
            if attempt == max_retries:
                _LOGGER.exception("Platform setup failed")
                raise ConfigEntryNotReady(
                    f"Platform setup failed ({err.__class__.__name__}): {err}",
                ) from err
            _LOGGER.warning(
                "Platform setup attempt %d failed: %s, retrying",
                attempt + 1,
                err,
            )
            await asyncio.sleep(1)


async def _async_setup_helpers(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    runtime_data: PawControlRuntimeData,
) -> None:
    """Create Home Assistant helpers for dogs.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        runtime_data: Runtime data with helper manager
    """
    helper_manager = runtime_data.helper_manager
    if helper_manager is None:
        _LOGGER.debug("Helper manager not available, skipping helper creation")
        return

    dogs_config = runtime_data.dogs
    enabled_modules = _resolve_enabled_modules(runtime_data.config_entry_options)
    helpers_start = time.monotonic()
    try:
        created_helpers = await asyncio.wait_for(
            helper_manager.async_create_helpers_for_dogs(
                dogs_config,
                enabled_modules,
            ),
            timeout=_HELPER_CREATION_TIMEOUT,
        )

        helper_count = sum(len(helpers) for helpers in created_helpers.values())
        helpers_duration = time.monotonic() - helpers_start

        if helper_count > 0:
            _LOGGER.info(
                "Created %d Home Assistant helpers for %d dogs in %.2f seconds",
                helper_count,
                len(dogs_config),
                helpers_duration,
            )

            # Send notification about helper creation
            notification_manager = runtime_data.notification_manager
            if notification_manager:
                try:
                    from ..notifications import NotificationPriority, NotificationType

                    await notification_manager.async_send_notification(
                        notification_type=NotificationType.SYSTEM_INFO,
                        title="PawControl Helper Setup Complete",
                        message=(
                            f"Created {helper_count} helpers for automated feeding schedules, "  # noqa: E501
                            "health reminders, and other dog management tasks."
                        ),
                        priority=NotificationPriority.NORMAL,
                    )
                except Exception as notification_err:
                    _LOGGER.debug(
                        "Helper creation notification failed (non-critical): %s",
                        notification_err,
                    )

    except TimeoutError:
        helpers_duration = time.monotonic() - helpers_start
        _LOGGER.warning(
            "Helper creation timed out after %.2f seconds (non-critical) "
            "You can manually create input_boolean and input_datetime helpers if needed",  # noqa: E501
            helpers_duration,
        )

    except Exception as helper_err:
        helpers_duration = time.monotonic() - helpers_start
        _LOGGER.warning(
            "Helper creation failed after %.2f seconds (non-critical): %s "
            "You can manually create input_boolean and input_datetime helpers if needed",  # noqa: E501
            helpers_duration,
            helper_err,
        )


async def _async_setup_scripts(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    runtime_data: PawControlRuntimeData,
) -> None:
    """Generate automation scripts for dogs.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        runtime_data: Runtime data with script manager
    """
    script_manager = runtime_data.script_manager
    if script_manager is None:
        _LOGGER.debug("Script manager not available, skipping script generation")
        return

    dogs_config = runtime_data.dogs
    enabled_modules = _resolve_enabled_modules(runtime_data.config_entry_options)
    scripts_start = time.monotonic()
    try:
        created_scripts = await asyncio.wait_for(
            script_manager.async_generate_scripts_for_dogs(
                dogs_config,
                enabled_modules,
            ),
            timeout=_SCRIPT_CREATION_TIMEOUT,
        )

        script_count = sum(len(scripts) for scripts in created_scripts.values())
        dog_script_map = {
            key: value for key, value in created_scripts.items() if key != "__entry__"
        }
        entry_script_count = len(created_scripts.get("__entry__", []))
        dog_target_count = len(dog_script_map)
        scripts_duration = time.monotonic() - scripts_start

        if script_count > 0:
            entry_detail = (
                f" including {entry_script_count} entry escalation script(s)"
                if entry_script_count
                else ""
            )
            _LOGGER.info(
                "Created %d PawControl automation script(s) for %d dog(s)%s in %.2f seconds",  # noqa: E501
                script_count,
                dog_target_count,
                entry_detail,
                scripts_duration,
            )

            # Send notification about script creation
            notification_manager = runtime_data.notification_manager
            if notification_manager:
                try:
                    from ..notifications import NotificationPriority, NotificationType

                    await notification_manager.async_send_notification(
                        notification_type=NotificationType.SYSTEM_INFO,
                        title="PawControl scripts ready",
                        message=(
                            "Generated PawControl automation scripts for "
                            f"{script_count} workflow(s). "
                            "The resilience escalation helper is included when guard "
                            "and breaker thresholds are configured."
                        ),
                        priority=NotificationPriority.NORMAL,
                    )
                except Exception as notification_err:
                    _LOGGER.debug(
                        "Script creation notification failed (non-critical): %s",
                        notification_err,
                    )

    except TimeoutError:
        scripts_duration = time.monotonic() - scripts_start
        _LOGGER.warning(
            "Script creation timed out after %.2f seconds (non-critical) "
            "You can create the scripts manually from Home Assistant's script editor",
            scripts_duration,
        )

    except (HomeAssistantError, Exception) as script_err:
        scripts_duration = time.monotonic() - scripts_start
        error_type = (
            "skipped" if isinstance(script_err, HomeAssistantError) else "failed"
        )
        _LOGGER.warning(
            "Script creation %s after %.2f seconds (non-critical): %s",
            error_type,
            scripts_duration,
            script_err,
        )
