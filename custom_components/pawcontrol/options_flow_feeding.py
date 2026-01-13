"""Feeding configuration steps for Paw Control options flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .exceptions import FlowValidationError
from .selector_shim import selector
from .types import (
    DOG_ID_FIELD,
    DOG_OPTIONS_FIELD,
    DogConfigData,
    DogOptionsMap,
    FeedingOptions,
    JSONLikeMapping,
    JSONValue,
    OptionsDogSelectionInput,
    OptionsFeedingSettingsInput,
    ensure_dog_options_entry,
)

if TYPE_CHECKING:

    class FeedingOptionsHost:
        _current_dog: DogConfigData | None
        _dogs: list[DogConfigData]

        def _clone_options(self) -> dict[str, JSONValue]: ...

        def _current_dog_options(self) -> DogOptionsMap: ...

        def _current_options(self) -> Mapping[str, JSONValue]: ...

        def _normalise_options_snapshot(
            self, options: Mapping[str, JSONValue]
        ) -> Mapping[str, JSONValue]: ...

        def _build_dog_selector_schema(self) -> vol.Schema: ...

        def _require_current_dog(self) -> DogConfigData | None: ...

        def _select_dog_by_id(self, dog_id: str | None) -> DogConfigData | None: ...

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: vol.Schema,
            errors: dict[str, str] | None = None,
        ) -> ConfigFlowResult: ...

        def async_create_entry(
            self, *, title: str, data: Mapping[str, JSONValue]
        ) -> ConfigFlowResult: ...

        async def async_step_init(self) -> ConfigFlowResult: ...

else:  # pragma: no cover
    FeedingOptionsHost = object


class FeedingOptionsMixin(FeedingOptionsHost):
    """Handle per-dog feeding options."""

    def _current_feeding_options(self, dog_id: str) -> FeedingOptions:
        """Return the stored feeding configuration as a typed mapping."""

        dog_options = self._current_dog_options()
        entry = dog_options.get(dog_id, {})
        raw = entry.get("feeding_settings")
        if isinstance(raw, Mapping):
            return cast(FeedingOptions, dict(raw))

        legacy = self._current_options().get("feeding_settings", {})
        if isinstance(legacy, Mapping):
            return cast(FeedingOptions, dict(legacy))

        return cast(FeedingOptions, {})

    async def async_step_select_dog_for_feeding_settings(
        self, user_input: OptionsDogSelectionInput | None = None
    ) -> ConfigFlowResult:
        """Select which dog to configure feeding settings for."""

        if not self._dogs:
            return await self.async_step_init()

        if user_input is not None:
            selected_dog_id = user_input.get("dog_id")
            self._select_dog_by_id(
                selected_dog_id if isinstance(selected_dog_id, str) else None
            )
            if self._current_dog:
                return await self.async_step_feeding_settings()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="select_dog_for_feeding_settings",
            data_schema=self._build_dog_selector_schema(),
        )

    async def async_step_feeding_settings(
        self, user_input: OptionsFeedingSettingsInput | None = None
    ) -> ConfigFlowResult:
        """Configure feeding and nutrition settings."""

        current_dog = self._require_current_dog()
        if current_dog is None:
            return await self.async_step_select_dog_for_feeding_settings()

        dog_id = current_dog.get(DOG_ID_FIELD)
        if not isinstance(dog_id, str):
            return await self.async_step_select_dog_for_feeding_settings()

        if user_input is not None:
            try:
                current_feeding = self._current_feeding_options(dog_id)
                new_options = self._clone_options()
                dog_options = self._current_dog_options()
                entry = ensure_dog_options_entry(
                    cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
                    dog_id=dog_id,
                )
                entry["feeding_settings"] = self._build_feeding_settings(
                    user_input, current_feeding
                )
                dog_options[dog_id] = entry
                new_options[DOG_OPTIONS_FIELD] = dog_options

                typed_options = self._normalise_options_snapshot(new_options)
                return self.async_create_entry(title="", data=typed_options)
            except FlowValidationError as err:
                return self.async_show_form(
                    step_id="feeding_settings",
                    data_schema=self._get_feeding_settings_schema(dog_id, user_input),
                    errors=err.as_form_errors(),
                )
            except Exception:
                return self.async_show_form(
                    step_id="feeding_settings",
                    data_schema=self._get_feeding_settings_schema(dog_id, user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="feeding_settings",
            data_schema=self._get_feeding_settings_schema(dog_id),
        )

    def _get_feeding_settings_schema(
        self, dog_id: str, user_input: OptionsFeedingSettingsInput | None = None
    ) -> vol.Schema:
        """Get feeding settings schema."""

        current_feeding = self._current_feeding_options(dog_id)
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "meals_per_day",
                    default=current_values.get(
                        "meals_per_day",
                        current_feeding.get("default_meals_per_day", 2),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=6, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    "feeding_reminders",
                    default=current_values.get(
                        "feeding_reminders",
                        current_feeding.get("feeding_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "portion_tracking",
                    default=current_values.get(
                        "portion_tracking",
                        current_feeding.get("portion_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "calorie_tracking",
                    default=current_values.get(
                        "calorie_tracking",
                        current_feeding.get("calorie_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "auto_schedule",
                    default=current_values.get(
                        "auto_schedule",
                        current_feeding.get("auto_schedule", False),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    def _build_feeding_settings(
        self,
        user_input: OptionsFeedingSettingsInput,
        current: FeedingOptions,
    ) -> FeedingOptions:
        """Create a typed feeding payload from the submitted form data."""

        return cast(
            FeedingOptions,
            {
                "default_meals_per_day": int(
                    user_input.get(
                        "meals_per_day", current.get("default_meals_per_day", 2)
                    )
                ),
                "feeding_reminders": bool(
                    user_input.get(
                        "feeding_reminders", current.get("feeding_reminders", True)
                    )
                ),
                "portion_tracking": bool(
                    user_input.get(
                        "portion_tracking", current.get("portion_tracking", True)
                    )
                ),
                "calorie_tracking": bool(
                    user_input.get(
                        "calorie_tracking", current.get("calorie_tracking", True)
                    )
                ),
                "auto_schedule": bool(
                    user_input.get("auto_schedule", current.get("auto_schedule", False))
                ),
            },
        )
