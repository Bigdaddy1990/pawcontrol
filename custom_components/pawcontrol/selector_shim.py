"""Compatibility shim for :mod:`homeassistant.helpers.selector`.

The integration prefers Home Assistant's native selector helpers when they are
available, but local unit tests run without the full Core runtime. This shim
recreates the subset of the selector namespace that PawControl relies on so
runtime behaviour and static analysis match the official interfaces regardless
of the environment. The fallback purposefully omits the legacy ``SelectOption``
dataclass in favour of ``TypedDict`` entries so that the typing mirrors Home
Assistant's current API surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from types import SimpleNamespace
from typing import Any, cast

_REQUIRED_ATTRIBUTES = {
    "BooleanSelector",
    "BooleanSelectorConfig",
    "DateSelector",
    "DateSelectorConfig",
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
    "TimeSelectorConfig",
}

try:  # pragma: no cover - exercised when Home Assistant is installed
    from homeassistant.helpers import selector as ha_selector
except ModuleNotFoundError:  # pragma: no cover - used in tests
    ha_selector = None

try:
    if ha_selector is not None and not all(
        hasattr(ha_selector, attr) for attr in _REQUIRED_ATTRIBUTES
    ):
        ha_selector = None
except AttributeError:
    # pragma: no cover - defensive guard for partial installs where accessing a
    # missing attribute raises during ``hasattr`` evaluation. Treat the selector
    # module as unavailable so the shim always returns a consistent namespace in
    # unit tests and constrained environments.
    ha_selector = None

if ha_selector is not None:  # pragma: no cover - passthrough when available
    selector = ha_selector
else:
    from typing import Literal, Required, TypedDict

    class BaseSelectorConfig(TypedDict, total=False):
        """Common selector configuration shared across helpers."""

        read_only: bool

    class BooleanSelectorConfig(BaseSelectorConfig, total=False):
        """Boolean selector configuration shim."""

    class NumberSelectorMode(StrEnum):
        """Available modes for number selectors."""

        BOX = "box"
        SLIDER = "slider"

    class NumberSelectorConfig(BaseSelectorConfig, total=False):
        """Number selector configuration shim."""

        min: float
        max: float
        step: float | Literal["any"]
        unit_of_measurement: str
        mode: NumberSelectorMode
        translation_key: str

    class SelectOptionDict(TypedDict):
        """Select selector option entry."""

        value: str
        label: str

    class SelectSelectorMode(StrEnum):
        """Available modes for select selectors."""

        LIST = "list"
        DROPDOWN = "dropdown"

    class SelectSelectorConfig(BaseSelectorConfig, total=False):
        """Select selector configuration shim."""

        options: Required[Sequence[SelectOptionDict | str]]
        multiple: bool
        custom_value: bool
        mode: SelectSelectorMode
        translation_key: str
        sort: bool

    class TextSelectorType(StrEnum):
        """Valid text selector input types."""

        COLOR = "color"
        DATE = "date"
        DATETIME_LOCAL = "datetime-local"
        EMAIL = "email"
        MONTH = "month"
        NUMBER = "number"
        PASSWORD = "password"
        SEARCH = "search"
        TEL = "tel"
        TEXT = "text"
        TIME = "time"
        URL = "url"
        WEEK = "week"

    class TextSelectorConfig(BaseSelectorConfig, total=False):
        """Text selector configuration shim."""

        multiline: bool
        prefix: str
        suffix: str
        type: TextSelectorType
        autocomplete: str
        multiple: bool

    class TimeSelectorConfig(BaseSelectorConfig, total=False):
        """Time selector configuration shim."""

    class DateSelectorConfig(BaseSelectorConfig, total=False):
        """Date selector configuration shim."""

    class _BaseSelector[ConfigT]:
        """Minimal selector implementation that stores the provided config."""

        def __init__(self, config: ConfigT | None = None) -> None:
            default_config: ConfigT = cast(ConfigT, {}) if config is None else config
            self.config = default_config

        def __call__(self, value: Any) -> Any:
            """Return the provided value without validation."""

            return value

        def __repr__(self) -> str:  # pragma: no cover - debug helper
            return f"{self.__class__.__name__}(config={self.config!r})"

    class BooleanSelector(_BaseSelector[BooleanSelectorConfig]):
        """Boolean selector shim."""

    class NumberSelector(_BaseSelector[NumberSelectorConfig]):
        """Number selector shim."""

    class SelectSelector(_BaseSelector[SelectSelectorConfig]):
        """Select selector shim."""

    class TextSelector(_BaseSelector[TextSelectorConfig]):
        """Text selector shim."""

    class TimeSelector(_BaseSelector[TimeSelectorConfig]):
        """Time selector shim."""

    class DateSelector(_BaseSelector[DateSelectorConfig]):
        """Date selector shim."""

    selector = SimpleNamespace(
        BooleanSelector=BooleanSelector,
        BooleanSelectorConfig=BooleanSelectorConfig,
        DateSelector=DateSelector,
        DateSelectorConfig=DateSelectorConfig,
        NumberSelector=NumberSelector,
        NumberSelectorConfig=NumberSelectorConfig,
        NumberSelectorMode=NumberSelectorMode,
        SelectOptionDict=SelectOptionDict,
        SelectSelector=SelectSelector,
        SelectSelectorConfig=SelectSelectorConfig,
        SelectSelectorMode=SelectSelectorMode,
        TextSelector=TextSelector,
        TextSelectorConfig=TextSelectorConfig,
        TextSelectorType=TextSelectorType,
        TimeSelector=TimeSelector,
        TimeSelectorConfig=TimeSelectorConfig,
    )

__all__ = ["selector"]
