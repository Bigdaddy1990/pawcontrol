"""Unit tests for the HealthMetrics dataclass enhancements."""

from dataclasses import dataclass
from datetime import UTC, datetime
import importlib.machinery
import pathlib
import sys
import types

import pytest


def _load_health_calculator_module() -> types.ModuleType:
  """Load the health_calculator module with lightweight stubs."""  # noqa: E111

  project_root = pathlib.Path(__file__).resolve().parents[2]  # noqa: E111
  module_path = (  # noqa: E111
    project_root / "custom_components" / "pawcontrol" / "health_calculator.py"
  )

  if "homeassistant" not in sys.modules:  # noqa: E111
    homeassistant_pkg = types.ModuleType("homeassistant")
    homeassistant_pkg.__path__ = []
    sys.modules["homeassistant"] = homeassistant_pkg

  ha_util = sys.modules.get("homeassistant.util") or types.ModuleType(  # noqa: E111
    "homeassistant.util"
  )
  ha_dt = sys.modules.get("homeassistant.util.dt") or types.ModuleType(  # noqa: E111
    "homeassistant.util.dt"
  )

  def _now() -> datetime:  # noqa: E111
    return datetime.now(UTC)

  def _utcnow() -> datetime:  # noqa: E111
    return datetime.now(UTC)

  def _start_of_local_day(value: datetime) -> datetime:  # noqa: E111
    if isinstance(value, datetime):
      return value.replace(hour=0, minute=0, second=0, microsecond=0)  # noqa: E111
    return datetime.combine(value, datetime.min.time(), tzinfo=UTC)

  ha_dt.now = _now  # noqa: E111
  ha_dt.utcnow = _utcnow  # noqa: E111
  ha_dt.start_of_local_day = _start_of_local_day  # noqa: E111
  ha_util.dt = ha_dt  # noqa: E111
  sys.modules.setdefault("homeassistant.util", ha_util)  # noqa: E111
  sys.modules.setdefault("homeassistant.util.dt", ha_dt)  # noqa: E111

  module_name = "custom_components.pawcontrol.health_calculator"  # noqa: E111
  module = types.ModuleType(module_name)  # noqa: E111
  module.__file__ = str(module_path)  # noqa: E111
  module.__package__ = "custom_components.pawcontrol"  # noqa: E111
  module.__loader__ = importlib.machinery.SourceFileLoader(  # noqa: E111
    module_name, str(module_path)
  )
  module.ensure_local_datetime = lambda value: value  # noqa: E111
  sys.modules[module_name] = module  # noqa: E111

  source = module_path.read_text(encoding="utf-8")  # noqa: E111
  source = source.replace("from .utils import ensure_local_datetime\n", "")  # noqa: E111
  exec(compile(source, module.__file__, "exec"), module.__dict__)  # noqa: E111
  return module  # noqa: E111


health_calculator = _load_health_calculator_module()
HealthCalculator = health_calculator.HealthCalculator
HealthMetrics = health_calculator.HealthMetrics


@dataclass
class _WeatherConditions:
  temperature_c: float | None = None  # noqa: E111
  humidity_percent: float | None = None  # noqa: E111


class _StubWeatherHealthManager:
  """Simple stub that tracks recommendation requests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.requests: list[tuple[str, int | None, list[str]]] = []

  @staticmethod  # noqa: E111
  def get_weather_health_score() -> int:  # noqa: E111
    return 82

  @staticmethod  # noqa: E111
  def get_active_alerts() -> list:  # noqa: E111
    return []

  def get_recommendations_for_dog(  # noqa: E111
    self,
    *,
    dog_breed: str,
    dog_age_months: int | None,
    health_conditions: list[str],
  ) -> list[str]:
    self.requests.append((dog_breed, dog_age_months, list(health_conditions)))
    return [
      "limit midday walks",
      "ensure hydration",
      "monitor paw pads",
      "consider protective booties",
    ]


def _blank_report() -> dict[str, object]:
  return {  # noqa: E111
    "recommendations": [],
    "areas_of_concern": [],
    "positive_indicators": [],
    "health_score": 100,
  }


def test_breed_recommendations_are_requested_when_breed_valid() -> None:
  manager = _StubWeatherHealthManager()  # noqa: E111
  metrics = HealthMetrics(  # noqa: E111
    current_weight=24.5,
    ideal_weight=23.0,
    height_cm=55.0,
    age_months=30,
    breed="  golden retriever  ",
    health_conditions=["arthritis"],
  )

  report = _blank_report()  # noqa: E111
  HealthCalculator._assess_weather_impact(  # noqa: E111
    metrics,
    _WeatherConditions(temperature_c=21.0),
    manager,
    report,
  )

  # Breed value should be normalised and forwarded to the weather manager  # noqa: E114
  assert manager.requests == [("golden retriever", 30, ["arthritis"])]  # noqa: E111
  assert report["recommendations"] == [  # noqa: E111
    "limit midday walks",
    "ensure hydration",
    "monitor paw pads",
  ]


@pytest.mark.parametrize("invalid_breed", ["", " ", "?", "1", "a"])
def test_invalid_breed_values_raise_value_error(invalid_breed: str) -> None:
  with pytest.raises(ValueError):  # noqa: E111
    HealthMetrics(current_weight=10.0, breed=invalid_breed)


def test_non_string_breed_values_raise_type_error() -> None:
  with pytest.raises(TypeError):  # noqa: E111
    HealthMetrics(current_weight=12.0, breed=123)  # type: ignore[arg-type]
