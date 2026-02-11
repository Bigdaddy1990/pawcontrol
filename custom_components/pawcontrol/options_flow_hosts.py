"""Type-checking protocols for options flow mixin hosts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .types import DogConfigData, DogOptionsMap, JSONValue


class DogOptionsHost(Protocol):
  """Protocol shared by per-dog options mixin hosts."""

  _current_dog: DogConfigData | None
  _dogs: list[DogConfigData]

  def _clone_options(self) -> dict[str, JSONValue]: ...

  def _current_dog_options(self) -> DogOptionsMap: ...

  def _current_options(self) -> Mapping[str, JSONValue]: ...

  def _coerce_bool(self, value: Any, default: bool) -> bool: ...

  def _normalise_options_snapshot(
    self,
    options: Mapping[str, JSONValue],
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
    self,
    *,
    title: str,
    data: Mapping[str, JSONValue],
  ) -> ConfigFlowResult: ...

  async def async_step_init(self) -> ConfigFlowResult: ...
