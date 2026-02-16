"""Unit tests for :mod:`custom_components.pawcontrol.entity_factory`.

These tests provide lightweight coverage for the profile guard rails without
requiring the full Home Assistant runtime.  The integration normally imports
``homeassistant.const.Platform`` and ``homeassistant.helpers.entity.Entity`` on
module import which are not available in the execution environment.  We stub
the minimal interfaces that the entity factory relies on so the module can be
imported and exercised directly.
"""

from enum import Enum, StrEnum
import types

import pytest

from custom_components.pawcontrol.entity_factory import (
  _MIN_OPERATION_DURATION,
  _RUNTIME_CONTRACT_FACTOR,
  _RUNTIME_CONTRACT_THRESHOLD,
  _RUNTIME_EXPAND_THRESHOLD,
  _RUNTIME_MAX_FLOOR,
  _RUNTIME_TARGET_RATIO,
  ENTITY_PROFILES,
  EntityEstimate,
  EntityFactory,
)
from tests.helpers.homeassistant_test_stubs import (
  Platform as _Platform,
  install_homeassistant_stubs,
)


class _PlatformStringAlias(Enum):
  """Enum stub exposing string values for compatibility testing."""  # noqa: E111

  SENSOR = "sensor"  # noqa: E111


class _PlatformEnumAlias(Enum):
  """Enum stub whose values point to another enum."""  # noqa: E111

  SENSOR = _Platform.SENSOR  # noqa: E111


class _NestedPlatformAlias(Enum):
  """Enum stub with nested enum indirection for platform aliases."""  # noqa: E111

  SENSOR = _PlatformEnumAlias.SENSOR  # noqa: E111


install_homeassistant_stubs()


def test_basic_profile_supports_buttons() -> None:
  """The basic profile must now recognise button entities."""  # noqa: E111

  assert _Platform.BUTTON in ENTITY_PROFILES["basic"]["platforms"]  # noqa: E111


def test_validate_profile_rejects_unknown_modules() -> None:
  """Unknown modules should cause profile validation to fail."""  # noqa: E111

  factory = EntityFactory(coordinator=None)  # noqa: E111
  modules = {"feeding": True, "unknown": True}  # noqa: E111

  assert not factory.validate_profile_for_modules("standard", modules)  # noqa: E111


def test_should_create_entity_accepts_platform_enum() -> None:
  """Passing the Platform enum is supported and validated."""  # noqa: E111

  factory = EntityFactory(coordinator=None)  # noqa: E111

  assert factory.should_create_entity(  # noqa: E111
    "standard",
    _Platform.SENSOR,
    "feeding",
    priority=6,
  )


def test_should_create_entity_accepts_nested_enum_alias() -> None:
  """Nested enum aliases should resolve to their underlying platform."""  # noqa: E111

  factory = EntityFactory(coordinator=None)  # noqa: E111

  assert factory.should_create_entity(  # noqa: E111
    "standard",
    _NestedPlatformAlias.SENSOR,
    "feeding",
    priority=6,
  )


def test_should_create_entity_blocks_unknown_module() -> None:
  """Unknown modules are rejected even for high-priority requests."""  # noqa: E111

  factory = EntityFactory(coordinator=None)  # noqa: E111

  assert not factory.should_create_entity(  # noqa: E111
    "advanced",
    _Platform.SENSOR,
    "unknown",
    priority=9,
  )


def test_create_entity_config_normalises_output() -> None:
  """Entity configuration results expose canonical values."""  # noqa: E111

  factory = EntityFactory(coordinator=None)  # noqa: E111
  config = factory.create_entity_config(  # noqa: E111
    dog_id="buddy",
    entity_type=_Platform.BUTTON,
    module="feeding",
    profile="basic",
    priority=9,
  )

  assert config is not None  # noqa: E111
  assert config["entity_type"] == "button"  # noqa: E111
  assert config["platform"] is _Platform.BUTTON  # noqa: E111


def test_create_entity_config_preserves_alias_enum_platform() -> None:
  """Entity configs should preserve alias enums when values match."""  # noqa: E111

  factory = EntityFactory(coordinator=None)  # noqa: E111

  config = factory.create_entity_config(  # noqa: E111
    dog_id="buddy",
    entity_type=_NestedPlatformAlias.SENSOR,
    module="feeding",
    profile="basic",
    priority=9,
  )

  assert config is not None  # noqa: E111
  assert config["platform"] is _NestedPlatformAlias.SENSOR  # noqa: E111


def test_create_entity_config_rejects_invalid_type() -> None:
  """Unsupported entity types should return ``None``."""  # noqa: E111

  factory = EntityFactory(coordinator=None)  # noqa: E111

  assert (  # noqa: E111
    factory.create_entity_config(
      dog_id="buddy",
      entity_type="unsupported",
      module="feeding",
      profile="standard",
    )
    is None
  )


def test_runtime_guard_expands_when_scheduler_starves() -> None:
  """The runtime guard should expand if operations are repeatedly delayed."""  # noqa: E111

  factory = EntityFactory(coordinator=None, enforce_min_runtime=True)  # noqa: E111
  baseline = factory._runtime_guard_floor  # noqa: E111

  factory._recalibrate_runtime_floor(  # noqa: E111
    baseline * (_RUNTIME_EXPAND_THRESHOLD + 2.5),
  )

  boosted = factory._runtime_guard_floor  # noqa: E111
  assert boosted > baseline  # noqa: E111
  observed_ratio = (baseline * (_RUNTIME_EXPAND_THRESHOLD + 2.5)) / boosted  # noqa: E111
  assert observed_ratio <= _RUNTIME_TARGET_RATIO  # noqa: E111
  assert boosted <= _RUNTIME_MAX_FLOOR  # noqa: E111


def test_runtime_guard_contracts_after_sustained_stability() -> None:
  """The adaptive guard should relax when jitter subsides."""  # noqa: E111

  factory = EntityFactory(coordinator=None, enforce_min_runtime=True)  # noqa: E111
  factory._runtime_guard_floor = _RUNTIME_MAX_FLOOR  # noqa: E111

  factory._recalibrate_runtime_floor(  # noqa: E111
    factory._runtime_guard_floor * (_RUNTIME_CONTRACT_THRESHOLD - 0.4),
  )

  contracted = factory._runtime_guard_floor  # noqa: E111
  assert contracted < _RUNTIME_MAX_FLOOR  # noqa: E111
  assert contracted >= _MIN_OPERATION_DURATION  # noqa: E111


def test_runtime_guard_respects_minimum_floor() -> None:
  """Contraction must not push the guard below the static baseline."""  # noqa: E111

  factory = EntityFactory(coordinator=None, enforce_min_runtime=True)  # noqa: E111
  factory._runtime_guard_floor = _MIN_OPERATION_DURATION * 1.5  # noqa: E111

  factory._recalibrate_runtime_floor(_MIN_OPERATION_DURATION * 0.5)  # noqa: E111

  assert factory._runtime_guard_floor >= _MIN_OPERATION_DURATION  # noqa: E111


def test_prewarm_restores_runtime_guard_floor(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Prewarming should not permanently alter the runtime guard floor."""  # noqa: E111

  factory = EntityFactory(  # noqa: E111
    coordinator=None,
    prewarm=False,
    enforce_min_runtime=True,
  )
  original_floor = factory._runtime_guard_floor  # noqa: E111
  original_get_estimate = EntityFactory._get_entity_estimate  # noqa: E111

  def _wrapped_get_estimate(  # noqa: E111
    self: EntityFactory,
    profile: str,
    modules: dict[str, bool] | None,
    *,
    log_invalid_inputs: bool,
  ) -> EntityEstimate:
    estimate = original_get_estimate(
      self,
      profile,
      modules,
      log_invalid_inputs=log_invalid_inputs,
    )
    self._runtime_guard_floor = original_floor * 2
    return estimate

  monkeypatch.setattr(EntityFactory, "_get_entity_estimate", _wrapped_get_estimate)  # noqa: E111

  factory._prewarm_caches()  # noqa: E111

  assert factory._runtime_guard_floor == pytest.approx(original_floor)  # noqa: E111


def test_runtime_guard_records_telemetry() -> None:
  """Runtime guard recalibrations should persist telemetry snapshots."""  # noqa: E111

  runtime_store = types.SimpleNamespace(performance_stats={})  # noqa: E111
  coordinator = types.SimpleNamespace(  # noqa: E111
    config_entry=types.SimpleNamespace(runtime_data=runtime_store),
  )

  factory = EntityFactory(coordinator=coordinator, enforce_min_runtime=True)  # noqa: E111
  baseline = factory._runtime_guard_floor  # noqa: E111
  assert baseline == pytest.approx(_MIN_OPERATION_DURATION)  # noqa: E111

  existing_metrics = runtime_store.performance_stats.get(  # noqa: E111
    "entity_factory_guard_metrics",
  )
  if isinstance(existing_metrics, dict):  # noqa: E111
    initial_samples = int(existing_metrics.get("samples", 0))
    initial_average = float(existing_metrics.get("average_duration", 0.0))
    initial_max = existing_metrics.get("max_duration")
    initial_min = existing_metrics.get("min_duration")
    initial_expansions = int(existing_metrics.get("expansions", 0))
    initial_contractions = int(existing_metrics.get("contractions", 0))
  else:  # noqa: E111
    initial_samples = 0
    initial_average = 0.0
    initial_max = None
    initial_min = None
    initial_expansions = 0
    initial_contractions = 0

  expand_duration = baseline * (_RUNTIME_TARGET_RATIO + 2.0)  # noqa: E111
  factory._recalibrate_runtime_floor(expand_duration)  # noqa: E111

  metrics = runtime_store.performance_stats["entity_factory_guard_metrics"]  # noqa: E111
  assert metrics["expansions"] == initial_expansions + 1  # noqa: E111
  assert metrics["samples"] == initial_samples + 1  # noqa: E111
  assert metrics["runtime_floor"] >= baseline  # noqa: E111
  assert metrics["last_event"] == "expand"  # noqa: E111
  assert metrics["last_actual_duration"] == pytest.approx(expand_duration)  # noqa: E111
  assert metrics["peak_runtime_floor"] >= metrics["runtime_floor"]  # noqa: E111
  assert metrics["lowest_runtime_floor"] >= baseline - 1e-12  # noqa: E111
  assert metrics["lowest_runtime_floor"] <= metrics["runtime_floor"] + 1e-12  # noqa: E111
  assert metrics["last_floor_change"] == pytest.approx(  # noqa: E111
    metrics["runtime_floor"] - baseline,
  )
  assert metrics["last_floor_change_ratio"] == pytest.approx(  # noqa: E111
    (metrics["runtime_floor"] - baseline) / baseline,
  )
  first_sample = metrics["last_actual_duration"]  # noqa: E111
  updated_average = ((initial_average * initial_samples) + first_sample) / (  # noqa: E111
    initial_samples + 1
  )
  assert metrics["average_duration"] == pytest.approx(updated_average)  # noqa: E111
  max_candidates = [first_sample]  # noqa: E111
  if isinstance(initial_max, (int, float)):  # noqa: E111
    max_candidates.append(float(initial_max))
  assert metrics["max_duration"] == pytest.approx(max(max_candidates))  # noqa: E111
  min_candidates = [first_sample]  # noqa: E111
  if isinstance(initial_min, (int, float)) and initial_samples > 0:  # noqa: E111
    min_candidates.append(float(initial_min))
  assert metrics["min_duration"] == pytest.approx(min(min_candidates))  # noqa: E111
  assert metrics["runtime_floor_delta"] == pytest.approx(  # noqa: E111
    metrics["runtime_floor"] - metrics["baseline_floor"],
  )

  expanded_floor = factory._runtime_guard_floor  # noqa: E111
  contract_duration = expanded_floor * (_RUNTIME_CONTRACT_THRESHOLD - 0.2)  # noqa: E111
  factory._recalibrate_runtime_floor(contract_duration)  # noqa: E111

  metrics = runtime_store.performance_stats["entity_factory_guard_metrics"]  # noqa: E111
  assert metrics["samples"] == initial_samples + 2  # noqa: E111
  assert metrics["contractions"] == initial_contractions + 1  # noqa: E111
  assert metrics["last_event"] == "contract"  # noqa: E111
  assert metrics["last_actual_duration"] > 0  # noqa: E111
  assert metrics["peak_runtime_floor"] >= expanded_floor  # noqa: E111
  assert metrics["lowest_runtime_floor"] <= metrics["runtime_floor"]  # noqa: E111
  assert metrics["last_floor_change"] == pytest.approx(  # noqa: E111
    metrics["runtime_floor"] - expanded_floor,
  )
  assert metrics["last_floor_change_ratio"] == pytest.approx(  # noqa: E111
    metrics["last_floor_change"] / expanded_floor,
  )
  second_sample = metrics["last_actual_duration"]  # noqa: E111
  combined_average = (  # noqa: E111
    (initial_average * initial_samples) + first_sample + second_sample
  ) / (initial_samples + 2)
  assert metrics["average_duration"] == pytest.approx(combined_average)  # noqa: E111
  max_candidates = [first_sample, second_sample]  # noqa: E111
  if isinstance(initial_max, (int, float)):  # noqa: E111
    max_candidates.append(float(initial_max))
  assert metrics["max_duration"] == pytest.approx(max(max_candidates))  # noqa: E111
  min_candidates = [first_sample, second_sample]  # noqa: E111
  if isinstance(initial_min, (int, float)) and initial_samples > 0:  # noqa: E111
    min_candidates.append(float(initial_min))
  assert metrics["min_duration"] == pytest.approx(min(min_candidates))  # noqa: E111
  assert metrics["runtime_floor_delta"] == pytest.approx(  # noqa: E111
    metrics["runtime_floor"] - metrics["baseline_floor"],
  )

  stable_duration = factory._runtime_guard_floor * 1.8  # noqa: E111
  factory._recalibrate_runtime_floor(stable_duration)  # noqa: E111

  metrics = runtime_store.performance_stats["entity_factory_guard_metrics"]  # noqa: E111
  assert metrics["samples"] == initial_samples + 3  # noqa: E111
  assert metrics["stable_samples"] >= 1  # noqa: E111
  assert metrics["last_event"] == "stable"  # noqa: E111
  assert metrics["consecutive_stable_samples"] >= 1  # noqa: E111
  assert metrics["longest_stable_run"] >= metrics["consecutive_stable_samples"]  # noqa: E111
  assert metrics["stable_ratio"] == pytest.approx(  # noqa: E111
    metrics["stable_samples"] / metrics["samples"],
  )
  assert metrics["expansion_ratio"] == pytest.approx(  # noqa: E111
    metrics["expansions"] / metrics["samples"],
  )
  assert metrics["contraction_ratio"] == pytest.approx(  # noqa: E111
    metrics["contractions"] / metrics["samples"],
  )
  assert metrics["volatility_ratio"] == pytest.approx(  # noqa: E111
    (metrics["expansions"] + metrics["contractions"]) / metrics["samples"],
  )

  recent = metrics["recent_durations"]  # noqa: E111
  assert len(recent) == min(5, metrics["samples"])  # noqa: E111
  assert recent[-1] == pytest.approx(stable_duration)  # noqa: E111
  assert metrics["recent_average_duration"] == pytest.approx(  # noqa: E111
    sum(recent) / len(recent),
  )
  assert metrics["recent_max_duration"] == pytest.approx(max(recent))  # noqa: E111
  assert metrics["recent_min_duration"] == pytest.approx(min(recent))  # noqa: E111
  assert metrics["recent_duration_span"] == pytest.approx(  # noqa: E111
    metrics["recent_max_duration"] - metrics["recent_min_duration"],
  )
  if metrics["runtime_floor"] > 0:  # noqa: E111
    assert metrics["jitter_ratio"] == pytest.approx(
      metrics["duration_span"] / metrics["runtime_floor"],
    )
    assert metrics["recent_jitter_ratio"] == pytest.approx(
      metrics["recent_duration_span"] / metrics["runtime_floor"],
    )

  assert metrics["recent_samples"] == len(recent)  # noqa: E111
  assert metrics["recent_events"][-1] == "stable"  # noqa: E111
  assert metrics["recent_stable_samples"] <= metrics["recent_samples"]  # noqa: E111
  assert metrics["recent_stable_ratio"] == pytest.approx(  # noqa: E111
    metrics["recent_stable_samples"] / metrics["recent_samples"],
  )
  assert metrics["stability_trend"] == "regressing"  # noqa: E111
