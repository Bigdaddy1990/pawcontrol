"""Compatibility shim for Home Assistant selector helpers.

This module mirrors the public ``homeassistant.helpers.selector`` interface
required by the PawControl integration while providing lightweight fallbacks
for environments where Home Assistant is not installed (for example during
local unit testing on CI).  When Home Assistant is available we simply expose
the upstream selector helpers to avoid any behavioural differences.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace
from typing import Any

_REQUIRED_ATTRIBUTES = {
    "BooleanSelector",
    "BooleanSelectorConfig",
    "DateSelector",
    "NumberSelector",
    "NumberSelectorConfig",
    "NumberSelectorMode",
    "SelectSelector",
    "SelectSelectorConfig",
    "SelectSelectorMode",
    "TextSelector",
    "TextSelectorConfig",
    "TextSelectorType",
    "TimeSelector",
}

try:  # pragma: no cover - exercised when Home Assistant is installed
    from homeassistant.helpers import selector as ha_selector

    if all(hasattr(ha_selector, attr) for attr in _REQUIRED_ATTRIBUTES):
        selector = ha_selector
    else:  # pragma: no cover - incomplete stub, fall back to local implementation
        raise ImportError("selector module missing required helpers")
except (ModuleNotFoundError, ImportError):  # pragma: no cover - used in tests

    class _BaseSelector:
        """Minimal selector base that stores the provided configuration."""

        def __init__(self, config: Any | None = None) -> None:
            self.config = config

        def __call__(self, value: Any) -> Any:
            """Allow selector instances to act as permissive validators."""

            return value

        def __repr__(self) -> str:  # pragma: no cover - debug helper
            return f"{self.__class__.__name__}(config={self.config!r})"

    class NumberSelectorMode(str, Enum):
        BOX = "box"
        SLIDER = "slider"

    @dataclass(slots=True)
    class NumberSelectorConfig:
        min: float | None = None
        max: float | None = None
        step: float | None = None
        unit_of_measurement: str | None = None
        mode: NumberSelectorMode = NumberSelectorMode.BOX

    class NumberSelector(_BaseSelector):
        pass

    class BooleanSelectorConfig:
        def __init__(self, *, multiple: bool | None = None) -> None:
            self.multiple = multiple

    class BooleanSelector(_BaseSelector):
        pass

    class SelectSelectorMode(str, Enum):
        LIST = "list"
        DROPDOWN = "dropdown"

    @dataclass(slots=True)
    class SelectOption:
        value: str
        label: str | None = None

    class SelectSelectorConfig:
        def __init__(
            self,
            options: list[str | SelectOption],
            *,
            mode: SelectSelectorMode = SelectSelectorMode.DROPDOWN,
            multiple: bool | None = None,
            custom_value: bool | None = None,
        ) -> None:
            self.options = options
            self.mode = mode
            self.multiple = multiple
            self.custom_value = custom_value

    class SelectSelector(_BaseSelector):
        pass

    class TextSelectorType(str, Enum):
        TEXT = "text"
        PASSWORD = "password"  # nosec B105 - selector sentinel, not a credential
        EMAIL = "email"
        TEL = "tel"

    class TextSelectorConfig:
        def __init__(
            self,
            type: TextSelectorType = TextSelectorType.TEXT,
            *,
            multiline: bool | None = None,
        ) -> None:
            self.type = type
            self.multiline = multiline

    class TextSelector(_BaseSelector):
        pass

    class TimeSelector(_BaseSelector):
        pass

    class DateSelector(_BaseSelector):
        pass

    selector = SimpleNamespace(
        BooleanSelector=BooleanSelector,
        BooleanSelectorConfig=BooleanSelectorConfig,
        DateSelector=DateSelector,
        NumberSelector=NumberSelector,
        NumberSelectorConfig=NumberSelectorConfig,
        NumberSelectorMode=NumberSelectorMode,
        SelectSelector=SelectSelector,
        SelectSelectorConfig=SelectSelectorConfig,
        SelectSelectorMode=SelectSelectorMode,
        SelectOption=SelectOption,
        TextSelector=TextSelector,
        TextSelectorConfig=TextSelectorConfig,
        TextSelectorType=TextSelectorType,
        TimeSelector=TimeSelector,
    )
else:  # pragma: no cover - exercised when Home Assistant is installed
    selector = ha_selector

__all__ = ["selector"]
