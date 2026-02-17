"""Feeding configuration steps for Paw Control options flow."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

from .exceptions import FlowValidationError
from .selector_shim import selector
from .types import (
    DOG_ID_FIELD,
    DOG_OPTIONS_FIELD,
    FeedingOptions,
    JSONLikeMapping,
    JSONValue,
    OptionsDogSelectionInput,
    OptionsFeedingSettingsInput,
    ensure_dog_options_entry,
)

if TYPE_CHECKING:
    from .options_flow_hosts import DogOptionsHost  # noqa: E111

    class FeedingOptionsHost(DogOptionsHost):  # noqa: E111
        """Type-checking host for feeding options mixin."""

else:  # pragma: no cover
    from .options_flow_shared import OptionsFlowSharedMixin  # noqa: E111

    class FeedingOptionsHost(OptionsFlowSharedMixin):  # noqa: E111
        """Runtime host for feeding options mixin."""

        pass


class FeedingOptionsMixin(FeedingOptionsHost):
    """Handle per-dog feeding options."""  # noqa: E111

    @staticmethod  # noqa: E111
    def _coerce_meals_per_day(value: Any, default: int) -> int:  # noqa: E111
        """Coerce meal counts to a bounded integer."""

        if value is None:
            return default  # noqa: E111
        try:
            meals = int(value)  # noqa: E111
        except ValueError:
            return default  # noqa: E111
        except TypeError:
            return default  # noqa: E111
        return max(1, min(6, meals))

    def _current_feeding_options(self, dog_id: str) -> FeedingOptions:  # noqa: E111
        """Return the stored feeding configuration as a typed mapping."""

        dog_options = self._current_dog_options()
        entry = dog_options.get(dog_id, {})
        raw = entry.get("feeding_settings")
        if isinstance(raw, Mapping):
            return cast(FeedingOptions, dict(raw))  # noqa: E111

        legacy = self._current_options().get("feeding_settings", {})
        if isinstance(legacy, Mapping):
            return cast(FeedingOptions, dict(legacy))  # noqa: E111

        return cast(FeedingOptions, {})

    async def async_step_select_dog_for_feeding_settings(  # noqa: E111
        self,
        user_input: OptionsDogSelectionInput | None = None,
    ) -> ConfigFlowResult:
        """Select which dog to configure feeding settings for."""

        if not self._dogs:
            return await self.async_step_init()  # noqa: E111

        if user_input is not None:
            selected_dog_id = user_input.get("dog_id")  # noqa: E111
            self._select_dog_by_id(  # noqa: E111
                selected_dog_id if isinstance(selected_dog_id, str) else None,
            )
            if self._current_dog:  # noqa: E111
                return await self.async_step_feeding_settings()
            return await self.async_step_init()  # noqa: E111

        return self.async_show_form(
            step_id="select_dog_for_feeding_settings",
            data_schema=self._build_dog_selector_schema(),
        )

    async def async_step_feeding_settings(  # noqa: E111
        self,
        user_input: OptionsFeedingSettingsInput | None = None,
    ) -> ConfigFlowResult:
        """Configure feeding and nutrition settings."""

        current_dog = self._require_current_dog()
        if current_dog is None:
            return await self.async_step_select_dog_for_feeding_settings()  # noqa: E111

        dog_id = current_dog.get(DOG_ID_FIELD)
        if not isinstance(dog_id, str):
            return await self.async_step_select_dog_for_feeding_settings()  # noqa: E111

        if user_input is not None:
            try:  # noqa: E111
                current_feeding = self._current_feeding_options(dog_id)
                new_options = self._clone_options()
                dog_options = self._current_dog_options()
                entry = ensure_dog_options_entry(
                    cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
                    dog_id=dog_id,
                )
                entry["feeding_settings"] = self._build_feeding_settings(
                    user_input,
                    current_feeding,
                )
                if dog_id in dog_options or not dog_options:
                    dog_options[dog_id] = entry  # noqa: E111
                    new_options[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)  # noqa: E111
                new_options["feeding_settings"] = cast(
                    JSONValue, entry["feeding_settings"]
                )

                typed_options = self._normalise_options_snapshot(new_options)
                return self.async_create_entry(title="", data=typed_options)
            except FlowValidationError as err:  # noqa: E111
                return self.async_show_form(
                    step_id="feeding_settings",
                    data_schema=self._get_feeding_settings_schema(
                        dog_id,
                        user_input,
                    ),
                    errors=err.as_form_errors(),
                )
            except Exception:  # noqa: E111
                return self.async_show_form(
                    step_id="feeding_settings",
                    data_schema=self._get_feeding_settings_schema(
                        dog_id,
                        user_input,
                    ),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="feeding_settings",
            data_schema=self._get_feeding_settings_schema(dog_id),
        )

    def _get_feeding_settings_schema(  # noqa: E111
        self,
        dog_id: str,
        user_input: OptionsFeedingSettingsInput | None = None,
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
                        min=1,
                        max=6,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
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
            },
        )

    def _build_feeding_settings(  # noqa: E111
        self,
        user_input: OptionsFeedingSettingsInput,
        current: FeedingOptions,
    ) -> FeedingOptions:
        """Create a typed feeding payload from the submitted form data."""

        return cast(
            FeedingOptions,
            {
                "default_meals_per_day": self._coerce_meals_per_day(
                    user_input.get("meals_per_day"),
                    current.get("default_meals_per_day", 2),
                ),
                "feeding_reminders": self._coerce_bool(
                    user_input.get("feeding_reminders"),
                    current.get("feeding_reminders", True),
                ),
                "portion_tracking": self._coerce_bool(
                    user_input.get("portion_tracking"),
                    current.get("portion_tracking", True),
                ),
                "calorie_tracking": self._coerce_bool(
                    user_input.get("calorie_tracking"),
                    current.get("calorie_tracking", True),
                ),
                "auto_schedule": self._coerce_bool(
                    user_input.get("auto_schedule"),
                    current.get("auto_schedule", False),
                ),
            },
        )
