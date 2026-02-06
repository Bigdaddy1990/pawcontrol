"""Set up and manage the PawControl integration lifecycle."""

from __future__ import annotations

import logging
from typing import cast

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import CONF_DOGS, DOMAIN, MODULE_GPS
from .coordinator import PawControlCoordinator
from .data_manager import PawControlDataManager
from .door_sensor_manager import DoorSensorManager
from .entity_factory import EntityFactory
from .feeding_manager import FeedingManager
from .garden_manager import GardenManager
from .geofencing import PawControlGeofencing
from .gps_manager import GPSGeofenceManager
from .helper_manager import PawControlHelperManager
from .notifications import PawControlNotificationManager
from .repairs import async_check_for_issues
from .runtime_data import pop_runtime_data, store_runtime_data
from .script_manager import PawControlScriptManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .types import (
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  ConfigEntryDataPayload,
  ConfigEntryOptionsPayload,
  DogConfigData,
  PawControlConfigEntry,
  PawControlRuntimeData,
  ensure_dog_config_data,
)
from .walk_manager import WalkManager
from .webhooks import async_register_entry_webhook, async_unregister_entry_webhook
from .mqtt_push import async_register_entry_mqtt, async_unregister_entry_mqtt
from .external_bindings import async_unload_external_bindings

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
  Platform.BINARY_SENSOR,
  Platform.BUTTON,
  Platform.DATE,
  Platform.DATETIME,
  Platform.DEVICE_TRACKER,
  Platform.NUMBER,
  Platform.SELECT,
  Platform.SENSOR,
  Platform.SWITCH,
  Platform.TEXT,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
  """Set up the PawControl integration."""
  domain_data = hass.data.setdefault(DOMAIN, {})
  if "service_manager" not in domain_data:
    domain_data["service_manager"] = PawControlServiceManager(hass)
  return True


async def async_setup_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
  """Set up PawControl from a config entry."""
  _LOGGER.debug("Setting up PawControl entry: %s", entry.entry_id)

  dogs_config_raw = entry.data.get(CONF_DOGS, [])
  dogs_config: list[DogConfigData] = []

  if isinstance(dogs_config_raw, list):
    for dog in dogs_config_raw:
      if isinstance(dog, dict) and (normalised := ensure_dog_config_data(dog)):
        dogs_config.append(normalised)

  session = async_get_clientsession(hass)
  coordinator = PawControlCoordinator(hass, entry, session)

  try:
    data_manager = PawControlDataManager(hass, entry.entry_id)
    notification_manager = PawControlNotificationManager(
      hass,
      entry.entry_id,
      session=session,
    )
    feeding_manager = FeedingManager(hass)
    walk_manager = WalkManager(hass, entry.entry_id)
    entity_factory = EntityFactory(coordinator)

    await data_manager.async_initialize()
    await notification_manager.async_initialize()
    await feeding_manager.async_initialize(dogs_config)
    await walk_manager.async_initialize([d[DOG_ID_FIELD] for d in dogs_config])

    helper_manager = PawControlHelperManager(hass, entry)
    script_manager = PawControlScriptManager(hass, entry)
    door_sensor_manager = DoorSensorManager(hass, entry.entry_id)
    garden_manager = GardenManager(hass, entry.entry_id)

    await helper_manager.async_initialize()
    await script_manager.async_initialize()
    await door_sensor_manager.async_initialize(
      dogs=dogs_config,
      walk_manager=walk_manager,
      notification_manager=notification_manager,
      data_manager=data_manager,
    )
    await garden_manager.async_initialize(
      dogs=[d[DOG_ID_FIELD] for d in dogs_config],
      notification_manager=notification_manager,
      door_sensor_manager=door_sensor_manager,
    )

    gps_geofence_manager = None
    geofencing_manager = None

    has_gps = any(
      bool(dog.get(DOG_MODULES_FIELD, {}).get(MODULE_GPS, False)) for dog in dogs_config
    )

    if has_gps:
      gps_geofence_manager = GPSGeofenceManager(hass)
      gps_geofence_manager.set_notification_manager(notification_manager)

      geofencing_manager = PawControlGeofencing(hass, entry.entry_id)
      geofencing_manager.set_notification_manager(notification_manager)
      await geofencing_manager.async_initialize(
        dogs=[d[DOG_ID_FIELD] for d in dogs_config],
        enabled=True,
      )

  except Exception as err:
    _LOGGER.exception("Failed to initialize managers")
    raise ConfigEntryNotReady(f"Manager initialization failed: {err}") from err

  coordinator.attach_runtime_managers(
    data_manager=data_manager,
    feeding_manager=feeding_manager,
    walk_manager=walk_manager,
    notification_manager=notification_manager,
    gps_geofence_manager=gps_geofence_manager,
    geofencing_manager=geofencing_manager,
    garden_manager=garden_manager,
  )

  await coordinator.async_config_entry_first_refresh()

  runtime_data = PawControlRuntimeData(
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=notification_manager,
    feeding_manager=feeding_manager,
    walk_manager=walk_manager,
    entity_factory=entity_factory,
    entity_profile=entry.options.get("entity_profile", "standard"),
    dogs=dogs_config,
    config_entry_data=cast(ConfigEntryDataPayload, entry.data),
    config_entry_options=cast(ConfigEntryOptionsPayload, entry.options),
  )

  runtime_data.helper_manager = helper_manager
  runtime_data.script_manager = script_manager
  runtime_data.geofencing_manager = geofencing_manager
  runtime_data.gps_geofence_manager = gps_geofence_manager
  runtime_data.door_sensor_manager = door_sensor_manager
  runtime_data.garden_manager = garden_manager
  runtime_data.device_api_client = coordinator.api_client

  store_runtime_data(hass, entry, runtime_data)

  await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

  await async_register_entry_webhook(hass, entry)
  await async_register_entry_mqtt(hass, entry)
  await helper_manager.async_create_helpers_for_dogs(dogs_config, set())
  await script_manager.async_generate_scripts_for_dogs(dogs_config, set())
  await async_setup_daily_reset_scheduler(hass, entry)
  await async_check_for_issues(hass, entry)

  entry.async_on_unload(entry.add_update_listener(async_reload_entry))

  return True


async def async_unload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
  """Unload a config entry."""
  await async_unregister_entry_webhook(hass, entry)
  await async_unregister_entry_mqtt(hass, entry)
  await async_unload_external_bindings(hass, entry)

  if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
    runtime_data = pop_runtime_data(hass, entry)
    if runtime_data:
      managers = [
        runtime_data.data_manager,
        runtime_data.feeding_manager,
        runtime_data.walk_manager,
        runtime_data.garden_manager,
        runtime_data.geofencing_manager,
        runtime_data.helper_manager,
        runtime_data.script_manager,
      ]
      for manager in managers:
        if hasattr(manager, "async_shutdown"):
          await manager.async_shutdown()
        elif hasattr(manager, "async_cleanup"):
          await manager.async_cleanup()

  return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> None:
  """Reload config entry."""
  await hass.config_entries.async_reload(entry.entry_id)
