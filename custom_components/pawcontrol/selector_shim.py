"""Compatibility shim for :mod:`homeassistant.helpers.selector`.

The integration prefers Home Assistant's native selector helpers when they are
available, but local unit tests run without the full Core runtime. This shim
recreates the subset of the selector namespace that PawControl relies on so
runtime behaviour and static analysis match the official interfaces regardless
of the environment. The fallback mirrors Home Assistant's ``TypedDict`` based
selector APIs to provide identical configuration schemas without depending on
the Core runtime during tests.
"""

from collections.abc import Sequence
from enum import StrEnum
from types import SimpleNamespace
from typing import Any, Protocol, TypeVar, cast


class _SelectorNamespace(SimpleNamespace):
  """Namespace exposing selector helpers and callable schema factory."""  # noqa: E111

  def __call__(self, config: Any) -> Any:  # noqa: E111
    selector_factory = getattr(self, "selector", None)
    if callable(selector_factory):
      return selector_factory(config)  # noqa: E111
    return config


class _SelectorNamespaceProtocol(Protocol):
  """Typing contract for the exported selector namespace."""  # noqa: E111

  Selector: Any  # noqa: E111
  BooleanSelector: Any  # noqa: E111
  BooleanSelectorConfig: Any  # noqa: E111
  DateSelector: Any  # noqa: E111
  DateSelectorConfig: Any  # noqa: E111
  NumberSelector: Any  # noqa: E111
  NumberSelectorConfig: Any  # noqa: E111
  NumberSelectorMode: Any  # noqa: E111
  SelectOptionDict: Any  # noqa: E111
  SelectSelector: Any  # noqa: E111
  SelectSelectorConfig: Any  # noqa: E111
  SelectSelectorMode: Any  # noqa: E111
  TextSelector: Any  # noqa: E111
  TextSelectorConfig: Any  # noqa: E111
  TextSelectorType: Any  # noqa: E111
  TimeSelector: Any  # noqa: E111
  TimeSelectorConfig: Any  # noqa: E111

  def __call__(self, config: Any) -> Any:  # noqa: E111
    """Return normalized selector config payload."""

    pass


try:  # pragma: no cover - exercised when Home Assistant is installed
  from homeassistant.helpers import selector as ha_selector  # noqa: E111
except ImportError:  # pragma: no cover - used in tests
  ha_selector = None  # noqa: E111


def _supports_selector_callables(module: object) -> bool:
  """Return ``True`` when selector instances behave like validators."""  # noqa: E111

  text_selector = getattr(module, "TextSelector", None)  # noqa: E111
  text_selector_config = getattr(module, "TextSelectorConfig", None)  # noqa: E111
  if not callable(text_selector) or text_selector_config is None:  # noqa: E111
    return False

  try:  # noqa: E111
    selector_instance = text_selector(text_selector_config())
  except Exception:  # noqa: E111
    return False

  return callable(selector_instance)  # noqa: E111


if ha_selector is not None and _supports_selector_callables(ha_selector):
  # pragma: no cover - passthrough when available  # noqa: E114
  selector = cast(  # noqa: E111
    _SelectorNamespaceProtocol, _SelectorNamespace(**ha_selector.__dict__)
  )
else:
  from typing import Literal, Required, TypedDict  # noqa: E111

  class BaseSelectorConfig(TypedDict, total=False):  # noqa: E111
    """Common selector configuration shared across helpers."""

    read_only: bool

  class BooleanSelectorConfig(BaseSelectorConfig, total=False):  # noqa: E111
    """Boolean selector configuration shim."""

  class NumberSelectorMode(StrEnum):  # noqa: E111
    """Available modes for number selectors."""

    BOX = "box"
    SLIDER = "slider"

  class NumberSelectorConfig(BaseSelectorConfig, total=False):  # noqa: E111
    """Number selector configuration shim."""

    min: float
    max: float
    step: float | Literal["any"]
    unit_of_measurement: str
    mode: NumberSelectorMode
    translation_key: str

  class SelectOptionDict(TypedDict):  # noqa: E111
    """Select selector option entry."""

    value: str
    label: str

  class SelectSelectorMode(StrEnum):  # noqa: E111
    """Available modes for select selectors."""

    LIST = "list"
    DROPDOWN = "dropdown"

  class SelectSelectorConfig(BaseSelectorConfig, total=False):  # noqa: E111
    """Select selector configuration shim."""

    options: Required[Sequence[SelectOptionDict | str]]
    multiple: bool
    custom_value: bool
    mode: SelectSelectorMode
    translation_key: str
    sort: bool

  class TextSelectorType(StrEnum):  # noqa: E111
    """Valid text selector input types."""

    COLOR = "color"
    DATE = "date"
    DATETIME_LOCAL = "datetime-local"
    EMAIL = "email"
    MONTH = "month"
    NUMBER = "number"
    PASSWORD = "password"  # nosec B105 - HTML input type constant, not a secret.
    SEARCH = "search"
    TEL = "tel"
    TEXT = "text"
    TIME = "time"
    URL = "url"
    WEEK = "week"

  class TextSelectorConfig(BaseSelectorConfig, total=False):  # noqa: E111
    """Text selector configuration shim."""

    multiline: bool
    prefix: str
    suffix: str
    type: TextSelectorType
    autocomplete: str
    multiple: bool

  class TimeSelectorConfig(BaseSelectorConfig, total=False):  # noqa: E111
    """Time selector configuration shim."""

  class DateSelectorConfig(BaseSelectorConfig, total=False):  # noqa: E111
    """Date selector configuration shim."""

  ConfigT = TypeVar("ConfigT", bound=BaseSelectorConfig)  # noqa: E111

  class _BaseSelector[ConfigT: BaseSelectorConfig]:  # noqa: E111
    """Typed selector stub that mirrors Home Assistant's runtime helpers.

    The shim relies on PEP 695 generics so each fallback selector exposes the
    same TypedDict-backed configuration objects as the real helpers. This
    keeps static analysis and IDE tooling aligned with Home Assistant's
    implementation even when the Core package is unavailable.
    """

    def __init__(self, config: ConfigT | None = None) -> None:
      # Normalise ``None`` to an empty mapping while preserving the specific  # noqa: E114, E501
      # TypedDict type advertised by ``ConfigT``. The cast is safe because  # noqa: E114
      # TypedDicts accept missing keys when ``total=False`` and the runtime  # noqa: E114, E501
      # helpers perform the same normalisation before storing configs.  # noqa: E114
      default_config: ConfigT = (  # noqa: E111
        cast(
          ConfigT,
          {},
        )
        if config is None
        else config
      )
      self.config = default_config  # noqa: E111

    def __call__(self, value: Any) -> Any:
      """Return the provided value without validation."""  # noqa: E111

      return value  # noqa: E111

    def __repr__(self) -> str:  # pragma: no cover - debug helper
      return f"{self.__class__.__name__}(config={self.config!r})"  # noqa: E111

  class BooleanSelector(_BaseSelector[BooleanSelectorConfig]):  # noqa: E111
    """Boolean selector shim."""

  class Selector(_BaseSelector[BaseSelectorConfig]):  # noqa: E111
    """Generic selector shim matching Home Assistant type hints."""

  class NumberSelector(_BaseSelector[NumberSelectorConfig]):  # noqa: E111
    """Number selector shim."""

  class SelectSelector(_BaseSelector[SelectSelectorConfig]):  # noqa: E111
    """Select selector shim."""

  class TextSelector(_BaseSelector[TextSelectorConfig]):  # noqa: E111
    """Text selector shim."""

  class TimeSelector(_BaseSelector[TimeSelectorConfig]):  # noqa: E111
    """Time selector shim."""

  class DateSelector(_BaseSelector[DateSelectorConfig]):  # noqa: E111
    """Date selector shim."""

  selector = cast(  # noqa: E111
    _SelectorNamespaceProtocol,
    _SelectorNamespace(
      # Home Assistant's selector() helper wraps selector config mappings into a
      # validator object. The lightweight test shim keeps the mapping unchanged
      # because tests assert schema shape rather than runtime coercion.
      selector=lambda config: config,
      Selector=Selector,
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
    ),
  )
__all__ = ["selector"]
