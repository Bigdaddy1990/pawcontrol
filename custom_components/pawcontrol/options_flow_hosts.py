"""Type-checking protocols for options flow mixin hosts."""

from collections.abc import Mapping
from typing import Any, Protocol

from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

from .types import DogConfigData, DogOptionsMap, JSONValue


class DogOptionsHost(Protocol):
  """Protocol shared by per-dog options mixin hosts."""  # noqa: E111

  _current_dog: DogConfigData | None  # noqa: E111
  _dogs: list[DogConfigData]  # noqa: E111

  def _clone_options(self) -> dict[str, JSONValue]: ...  # noqa: E111

  def _current_dog_options(self) -> DogOptionsMap: ...  # noqa: E111

  def _current_options(self) -> Mapping[str, JSONValue]: ...  # noqa: E111

  def _coerce_bool(self, value: Any, default: bool) -> bool: ...  # noqa: E111

  def _normalise_options_snapshot(  # noqa: E111
    self,
    options: Mapping[str, JSONValue],
  ) -> Mapping[str, JSONValue]: ...

  def _build_dog_selector_schema(self) -> vol.Schema: ...  # noqa: E111

  def _require_current_dog(self) -> DogConfigData | None: ...  # noqa: E111

  def _select_dog_by_id(self, dog_id: str | None) -> DogConfigData | None: ...  # noqa: E111

  def async_show_form(  # noqa: E111
    self,
    *,
    step_id: str,
    data_schema: vol.Schema,
    errors: dict[str, str] | None = None,
  ) -> ConfigFlowResult: ...

  def async_create_entry(  # noqa: E111
    self,
    *,
    title: str,
    data: Mapping[str, JSONValue],
  ) -> ConfigFlowResult: ...

  async def async_step_init(self) -> ConfigFlowResult: ...  # noqa: E111
