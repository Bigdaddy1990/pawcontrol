"""Unit tests for the HealthMetrics dataclass enhancements."""

from __future__ import annotations

import importlib.machinery
import pathlib
import sys
import types
from dataclasses import dataclass
from datetime import UTC

import pytest


def _load_health_calculator_module() -> types.ModuleType:
  """Load the health_calculator module with lightweight stubs."""

  project_root = pathlib.Path(__file__).resolve().parents[2]
  module_path = (
    project_root / "custom_components" / "pawcontrol" / "health_calculator.py"
  )

  if "homeassistant" not in sys.modules:
    homeassistant_pkg = types.ModuleType("homeassistant")
    homeassistant_pkg.__path__ = []
    sys.modules["homeassistant"] = homeassistant_pkg

  ha_util = types.ModuleType("homeassistant.util")
  ha_dt = types.ModuleType("homeassistant.util.dt")

  def _now():
    from datetime import datetime, timezone

    return datetime.now(UTC)

  ha_dt.now = _now
  ha_util.dt = ha_dt
  sys.modules["homeassistant.util"] = ha_util
  sys.modules["homeassistant.util.dt"] = ha_dt

  module_name = "custom_components.pawcontrol.health_calculator"
  module = types.ModuleType(module_name)
  module.__file__ = str(module_path)
  module.__package__ = "custom_components.pawcontrol"
  module.__loader__ = importlib.machinery.SourceFileLoader(
    module_name, str(module_path)
  )
  module.ensure_local_datetime = lambda value: value
  sys.modules[module_name] = module

  source = module_path.read_text(encoding="utf-8")
  source = source.replace("from .utils import ensure_local_datetime\n", "")
  exec(compile(source, module.__file__, "exec"), module.__dict__)
  return module


health_calculator = _load_health_calculator_module()
HealthCalculator = health_calculator.HealthCalculator
HealthMetrics = health_calculator.HealthMetrics


@dataclass
class _WeatherConditions:
  temperature_c: float | None = None
  humidity_percent: float | None = None


class _StubWeatherHealthManager:
  """Simple stub that tracks recommendation requests."""

  def __init__(self) -> None:
    self.requests: list[tuple[str, int | None, list[str]]] = []

  @staticmethod
  def get_weather_health_score() -> int:
    return 82

  @staticmethod
  def get_active_alerts() -> list:
    return []

  def get_recommendations_for_dog(
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
  return {
    "recommendations": [],
    "areas_of_concern": [],
    "positive_indicators": [],
    "health_score": 100,
  }


def test_breed_recommendations_are_requested_when_breed_valid() -> None:
  manager = _StubWeatherHealthManager()
  metrics = HealthMetrics(
    current_weight=24.5,
    ideal_weight=23.0,
    height_cm=55.0,
    age_months=30,
    breed="  golden retriever  ",
    health_conditions=["arthritis"],
  )

  report = _blank_report()
  HealthCalculator._assess_weather_impact(
    metrics,
    _WeatherConditions(temperature_c=21.0),
    manager,
    report,
  )

  # Breed value should be normalised and forwarded to the weather manager
  assert manager.requests == [("golden retriever", 30, ["arthritis"])]
  assert report["recommendations"] == [
    "limit midday walks",
    "ensure hydration",
    "monitor paw pads",
  ]


@pytest.mark.parametrize("invalid_breed", ["", " ", "?", "1", "a"])
def test_invalid_breed_values_raise_value_error(invalid_breed: str) -> None:
  with pytest.raises(ValueError):
    HealthMetrics(current_weight=10.0, breed=invalid_breed)


def test_non_string_breed_values_raise_type_error() -> None:
  with pytest.raises(TypeError):
    HealthMetrics(current_weight=12.0, breed=123)  # type: ignore[arg-type]
