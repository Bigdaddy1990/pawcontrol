"""Reauthentication helpers for Paw Control config flow."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .const import CONF_DOGS, CONF_MODULES
from .entity_factory import ENTITY_PROFILES, EntityFactory
from .exceptions import ConfigEntryAuthFailed, ReauthRequiredError, ValidationError
from .types import (
  DOG_ID_FIELD,
  REAUTH_PLACEHOLDERS_TEMPLATE,
  DogConfigData,
  ReauthDataUpdates,
  ReauthHealthSummary,
  ReauthOptionsUpdates,
  ReauthPlaceholders,
  JSONValue,
  clone_placeholders,
  ensure_dog_modules_mapping,
  freeze_placeholders,
  is_dog_config_valid,
)

_LOGGER = logging.getLogger(__name__)

REAUTH_TIMEOUT_SECONDS: Final[float] = 30.0
CONFIG_HEALTH_CHECK_TIMEOUT: Final[float] = 15.0

_VALID_PROFILES: Final[frozenset[str]] = frozenset(ENTITY_PROFILES.keys())


if TYPE_CHECKING:

  class ReauthFlowHost:
    reauth_entry: ConfigEntry | None
    hass: Any
    context: dict[str, object]

    def _normalise_string_list(self, values: Any) -> list[str]: ...

    def _normalise_entry_dogs(
      self,
      entry: ConfigEntry,
    ) -> list[DogConfigData]: ...

    def _abort_if_unique_id_mismatch(self, *, reason: str) -> None: ...

    async def async_set_unique_id(
      self,
      unique_id: str | None = None,
    ) -> None: ...

    async def async_update_reload_and_abort(
      self,
      entry: ConfigEntry,
      *,
      data_updates: Mapping[str, object] | None = None,
      options_updates: Mapping[str, object] | None = None,
      reason: str,
    ) -> ConfigFlowResult: ...

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      errors: dict[str, str] | None = None,
      description_placeholders: Mapping[str, str] | None = None,
    ) -> ConfigFlowResult: ...

else:  # pragma: no cover
  ReauthFlowHost = object


class ReauthFlowMixin(ReauthFlowHost):
  """Mixin for reauthentication steps and validation."""

  @staticmethod
  def _normalise_dog_payload(
    dogs: object,
  ) -> list[Mapping[str, JSONValue]]:
    """Return stored dog payloads normalised to a list of mappings."""

    if isinstance(dogs, Sequence) and not isinstance(dogs, str | bytes):
      return [dog for dog in dogs if isinstance(dog, Mapping)]
    return []

  @classmethod
  def _count_dogs(cls, dogs: object) -> int:
    """Return the number of stored dogs from an entry payload."""

    return len(cls._normalise_dog_payload(dogs))

  def _render_reauth_health_status(self, summary: ReauthHealthSummary) -> str:
    """Render a concise description of the reauth health snapshot."""

    healthy = summary.get("healthy", True)
    validated = summary.get("validated_dogs", 0)
    total = summary.get("total_dogs", 0)
    parts = [
      "Status: " + ("healthy" if healthy else "attention required"),
      f"Validated dogs: {validated}/{total}",
    ]

    issues = self._normalise_string_list(summary.get("issues", []))
    if issues:
      parts.append("Issues: " + ", ".join(issues))

    warnings = self._normalise_string_list(summary.get("warnings", []))
    if warnings:
      parts.append("Warnings: " + ", ".join(warnings))

    invalid_modules = summary.get("invalid_modules")
    if isinstance(invalid_modules, int) and invalid_modules > 0:
      parts.append(f"Modules needing review: {invalid_modules}")

    return "; ".join(parts)

  def _build_reauth_updates(
    self,
    summary: ReauthHealthSummary,
  ) -> tuple[ReauthDataUpdates, ReauthOptionsUpdates]:
    """Build typed update payloads for a successful reauth."""

    timestamp = dt_util.utcnow().isoformat()

    data_updates: ReauthDataUpdates = {
      "reauth_timestamp": timestamp,
      "reauth_version": getattr(self, "VERSION", 1),
      "health_status": summary.get("healthy", True),
      "health_validated_dogs": summary.get("validated_dogs", 0),
      "health_total_dogs": summary.get("total_dogs", 0),
    }

    options_updates: ReauthOptionsUpdates = {
      "last_reauth": timestamp,
      "reauth_health_issues": self._normalise_string_list(
        summary.get("issues", []),
      ),
      "reauth_health_warnings": self._normalise_string_list(
        summary.get("warnings", []),
      ),
      "last_reauth_summary": self._render_reauth_health_status(summary),
    }

    return data_updates, options_updates

  def _build_reauth_placeholders(
    self,
    summary: ReauthHealthSummary,
  ) -> ReauthPlaceholders:
    """Generate description placeholders for the reauth confirmation form."""

    if not self.reauth_entry:
      raise ConfigEntryAuthFailed(
        "No entry available for reauthentication",
      )

    total_dogs = summary.get("total_dogs")
    if total_dogs is None:
      total_dogs = self._count_dogs(self.reauth_entry.data.get(CONF_DOGS, []))

    profile_raw = self.reauth_entry.options.get(
      "entity_profile",
      "unknown",
    )
    profile = (
      profile_raw
      if isinstance(
        profile_raw,
        str,
      )
      else str(profile_raw)
    )

    placeholders = clone_placeholders(REAUTH_PLACEHOLDERS_TEMPLATE)
    placeholders["integration_name"] = self.reauth_entry.title
    placeholders["dogs_count"] = str(total_dogs)
    placeholders["current_profile"] = profile
    placeholders["health_status"] = self._render_reauth_health_status(
      summary,
    )
    return cast(ReauthPlaceholders, freeze_placeholders(placeholders))

  async def async_step_reauth(
    self,
    _entry_data: Mapping[str, object],
  ) -> ConfigFlowResult:
    """Handle reauthentication flow with enhanced error handling."""

    _LOGGER.debug(
      "Starting reauthentication flow (event=reauth_start entry_id=%s)",
      self.context.get("entry_id"),
    )

    try:
      async with asyncio.timeout(REAUTH_TIMEOUT_SECONDS):
        self.reauth_entry = self.hass.config_entries.async_get_entry(
          self.context["entry_id"],
        )

      if not self.reauth_entry:
        _LOGGER.error("Reauthentication failed: entry not found")
        raise ReauthRequiredError(
          "Config entry not found for reauthentication",
          context={"entry_id": self.context.get("entry_id")},
        )

      try:
        async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
          await self._validate_reauth_entry_enhanced(self.reauth_entry)
      except TimeoutError as err:
        _LOGGER.error(
          "Entry validation timeout during reauth: %s",
          err,
        )
        raise ReauthRequiredError(
          "Entry validation timeout",
          context={"reason": "timeout"},
        ) from err
      except ValidationError as err:
        _LOGGER.error("Reauthentication validation failed: %s", err)
        raise ReauthRequiredError(
          f"Entry validation failed: {err}",
          context={"reason": "validation"},
        ) from err

      return await self.async_step_reauth_confirm()

    except ReauthRequiredError as err:
      _LOGGER.error("Reauthentication required: %s", err)
      raise ConfigEntryAuthFailed(str(err)) from err
    except TimeoutError as err:
      _LOGGER.error("Reauth step timeout: %s", err)
      reauth_error = ReauthRequiredError(
        "Reauthentication timeout",
        context={"reason": "timeout"},
      )
      raise ConfigEntryAuthFailed(str(reauth_error)) from reauth_error
    except Exception as err:
      _LOGGER.error("Unexpected reauth error: %s", err)
      reauth_error = ReauthRequiredError(
        f"Reauthentication failed: {err}",
        context={"reason": "unexpected"},
      )
      raise ConfigEntryAuthFailed(str(reauth_error)) from reauth_error

  async def _validate_reauth_entry_enhanced(self, entry: ConfigEntry) -> None:
    """Enhanced config entry validation for reauthentication."""

    dogs_raw = entry.data.get(CONF_DOGS, [])
    dogs = self._normalise_dog_payload(dogs_raw)
    if not dogs:
      _LOGGER.debug(
        "Reauthentication proceeding without stored dog data for entry %s",
        entry.entry_id,
      )
      return

    invalid_dogs: list[str] = []

    for dog in dogs:
      try:
        if not is_dog_config_valid(dog):
          dog_id = dog.get(DOG_ID_FIELD, "unknown")
          invalid_dogs.append(str(dog_id))
      except Exception as err:
        _LOGGER.warning(
          "Dog validation error during reauth (non-critical): %s",
          err,
        )
        dog_id = dog.get(DOG_ID_FIELD, "corrupted")
        invalid_dogs.append(str(dog_id))

    if invalid_dogs:
      _LOGGER.warning(
        "Invalid dog configurations found during reauth: %d invalid entries",
        len(invalid_dogs),
      )
      if len(invalid_dogs) == len(dogs):
        raise ValidationError(
          "entry_dogs",
          constraint=(f"All dog configurations are invalid: {', '.join(invalid_dogs)}"),
        )

    profile = entry.options.get("entity_profile", "standard")
    if profile not in _VALID_PROFILES:
      _LOGGER.warning(
        "Invalid entity profile '%s' during reauth, will use 'standard'",
        profile,
      )

  async def async_step_reauth_confirm(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Confirm reauthentication with enhanced validation and error handling."""

    if not self.reauth_entry:
      reauth_error = ReauthRequiredError(
        "No entry available for reauthentication",
        context={"reason": "missing_entry"},
      )
      raise ConfigEntryAuthFailed(str(reauth_error)) from reauth_error

    errors: dict[str, str] = {}
    summary: ReauthHealthSummary | None = None

    if user_input is not None:
      if user_input.get("confirm", False):
        try:
          _LOGGER.debug(
            "Reauthentication confirmation received (event=reauth_confirm entry_id=%s)",
            self.reauth_entry.entry_id,
          )
          async with asyncio.timeout(REAUTH_TIMEOUT_SECONDS):
            await self.async_set_unique_id(self.reauth_entry.unique_id)
            self._abort_if_unique_id_mismatch(
              reason="wrong_account",
            )

            try:
              async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
                summary = cast(
                  ReauthHealthSummary,
                  await self._check_config_health_enhanced(
                    self.reauth_entry,
                  ),
                )
            except TimeoutError:
              _LOGGER.warning(
                "Config health check timeout - proceeding with reauth",
              )
              summary = cast(
                ReauthHealthSummary,
                {
                  "healthy": True,
                  "issues": ["Health check timeout"],
                  "warnings": [],
                  "validated_dogs": 0,
                  "total_dogs": self._count_dogs(
                    self.reauth_entry.data.get(CONF_DOGS, []),
                  ),
                },
              )
            except Exception as err:
              _LOGGER.warning(
                "Config health check failed: %s - proceeding with reauth",
                err,
              )
              summary = cast(
                ReauthHealthSummary,
                {
                  "healthy": True,
                  "issues": [f"Health check error: {err}"],
                  "warnings": [],
                  "validated_dogs": 0,
                  "total_dogs": self._count_dogs(
                    self.reauth_entry.data.get(CONF_DOGS, []),
                  ),
                },
              )

            if summary is None:
              summary = cast(
                ReauthHealthSummary,
                {
                  "healthy": True,
                  "issues": [],
                  "warnings": [],
                  "validated_dogs": 0,
                  "total_dogs": self._count_dogs(
                    self.reauth_entry.data.get(CONF_DOGS, []),
                  ),
                },
              )

            if not summary.get("healthy", True):
              _LOGGER.warning(
                "Configuration health issues detected: %d",
                len(self._normalise_string_list(summary.get("issues", []))),
              )

            data_updates, options_updates = self._build_reauth_updates(
              summary,
            )

            _LOGGER.info(
              "Reauthentication succeeded (event=reauth_success entry_id=%s dogs=%d issues=%d warnings=%d)",
              self.reauth_entry.entry_id,
              summary.get("total_dogs", 0),
              len(self._normalise_string_list(summary.get("issues", []))),
              len(self._normalise_string_list(summary.get("warnings", []))),
            )

            return await self.async_update_reload_and_abort(
              self.reauth_entry,
              data_updates=data_updates,
              options_updates=options_updates,
              reason="reauth_successful",
            )

        except TimeoutError as err:
          _LOGGER.error("Reauth confirmation timeout: %s", err)
          errors["base"] = "reauth_timeout"
        except ConfigEntryAuthFailed:
          raise
        except Exception as err:
          _LOGGER.error("Reauthentication failed: %s", err)
          errors["base"] = "reauth_failed"
      else:
        errors["base"] = "reauth_unsuccessful"

    if summary is None:
      try:
        async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
          summary = cast(
            ReauthHealthSummary,
            await self._check_config_health_enhanced(self.reauth_entry),
          )
      except Exception as err:
        _LOGGER.warning("Error getting reauth display info: %s", err)
        summary = cast(
          ReauthHealthSummary,
          {
            "healthy": True,
            "issues": [],
            "warnings": [f"Status check failed: {err}"],
            "validated_dogs": 0,
            "total_dogs": self._count_dogs(self.reauth_entry.data.get(CONF_DOGS, [])),
          },
        )

    return self.async_show_form(
      step_id="reauth_confirm",
      data_schema=vol.Schema(
        {
          vol.Required("confirm", default=True): cv.boolean,
        },
      ),
      errors=errors,
      description_placeholders=dict(
        cast(
          Mapping[str, str],
          self._build_reauth_placeholders(cast(ReauthHealthSummary, summary)),
        ),
      ),
    )

  async def _check_config_health_enhanced(
    self,
    entry: ConfigEntry,
  ) -> ReauthHealthSummary:
    """Enhanced configuration health check with graceful degradation."""

    dogs = [dict(dog) for dog in self._normalise_entry_dogs(entry)]
    issues: list[str] = []
    warnings: list[str] = []
    valid_dogs = 0
    invalid_modules = 0

    for index, dog in enumerate(dogs):
      dog_id_value = dog.get(DOG_ID_FIELD)
      dog_id = (
        dog_id_value
        if isinstance(dog_id_value, str) and dog_id_value
        else f"dog_{index}"
      )
      try:
        if is_dog_config_valid(dog):
          valid_dogs += 1
        else:
          issues.append(f"Invalid dog config: {dog_id}")
      except Exception as err:
        warnings.append(
          f"Dog config validation error for {dog_id}: {err}",
        )

      modules = dog.get(CONF_MODULES)
      if isinstance(modules, Mapping):
        for module, enabled in modules.items():
          if not isinstance(enabled, bool):
            invalid_modules += 1
            warnings.append(
              f"Module '{module}' has invalid flag for {dog_id}",
            )
      elif modules not in (None, {}):
        invalid_modules += 1
        warnings.append(f"Modules payload invalid for {dog_id}")

    if valid_dogs == 0 and dogs:
      issues.append("No valid dog configurations found")

    profile_raw = entry.options.get("entity_profile", "standard")
    profile = (
      profile_raw
      if isinstance(
        profile_raw,
        str,
      )
      else str(profile_raw)
    )
    if profile not in _VALID_PROFILES:
      warnings.append(
        f"Invalid profile '{profile}' - will use 'standard'",
      )

    try:
      dog_ids = [
        dog_id
        for dog_id in (dog.get(DOG_ID_FIELD) for dog in dogs if dog.get(DOG_ID_FIELD))
        if isinstance(dog_id, str)
      ]
      if len(dog_ids) != len(set(dog_ids)):
        issues.append("Duplicate dog IDs detected")
    except Exception as err:
      warnings.append(f"Dog ID validation error: {err}")

    estimated_entities = 0
    try:
      factory = EntityFactory(None)
      estimated_entities = 0
      for dog in dogs:
        if not is_dog_config_valid(dog):
          continue
        modules_mapping = ensure_dog_modules_mapping(dog)
        estimated_entities += await factory.estimate_entity_count_async(
          profile,
          modules_mapping,
        )
      if estimated_entities > 200:
        warnings.append(
          f"High entity count ({estimated_entities}) may impact performance",
        )
    except Exception as err:
      warnings.append(f"Entity estimation failed: {err}")

    summary: ReauthHealthSummary = {
      "healthy": len(issues) == 0,
      "issues": self._normalise_string_list(issues),
      "warnings": self._normalise_string_list(warnings),
      "validated_dogs": valid_dogs,
      "total_dogs": len(dogs),
      "dogs_count": len(dogs),
      "valid_dogs": valid_dogs,
      "profile": profile,
      "estimated_entities": estimated_entities,
    }
    if invalid_modules:
      summary["invalid_modules"] = invalid_modules
    return summary

  async def _get_health_status_summary_safe(self, entry: ConfigEntry) -> str:
    """Get health status summary with graceful error handling."""

    try:
      async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
        summary = cast(
          ReauthHealthSummary,
          await self._check_config_health_enhanced(entry),
        )
      return self._render_reauth_health_status(summary)
    except TimeoutError:
      return "Health check timeout"
    except Exception as err:
      _LOGGER.debug("Health status summary error: %s", err)
      return f"Health check failed: {err}"
