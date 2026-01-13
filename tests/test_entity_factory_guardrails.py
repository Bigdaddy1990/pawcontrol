"""Unit tests for :mod:`custom_components.pawcontrol.entity_factory`.

These tests provide lightweight coverage for the profile guard rails without
requiring the full Home Assistant runtime.  The integration normally imports
``homeassistant.const.Platform`` and ``homeassistant.helpers.entity.Entity`` on
module import which are not available in the execution environment.  We stub
the minimal interfaces that the entity factory relies on so the module can be
imported and exercised directly.
"""
from __future__ import annotations

import types
from enum import Enum
from enum import StrEnum

import pytest

from tests.helpers.homeassistant_test_stubs import (
    install_homeassistant_stubs,
)
from tests.helpers.homeassistant_test_stubs import (
    Platform as _Platform,
)


class _PlatformStringAlias(Enum):
    """Enum stub exposing string values for compatibility testing."""

    SENSOR = 'sensor'


class _PlatformEnumAlias(Enum):
    """Enum stub whose values point to another enum."""

    SENSOR = _Platform.SENSOR


class _NestedPlatformAlias(Enum):
    """Enum stub with nested enum indirection for platform aliases."""

    SENSOR = _PlatformEnumAlias.SENSOR


install_homeassistant_stubs()

from custom_components.pawcontrol.entity_factory import (
    _MIN_OPERATION_DURATION,
    _RUNTIME_CONTRACT_FACTOR,
    _RUNTIME_CONTRACT_THRESHOLD,
    _RUNTIME_EXPAND_THRESHOLD,
    _RUNTIME_MAX_FLOOR,
    _RUNTIME_TARGET_RATIO,
    ENTITY_PROFILES,
    EntityFactory,
)


def test_basic_profile_supports_buttons() -> None:
    """The basic profile must now recognise button entities."""

    assert _Platform.BUTTON in ENTITY_PROFILES['basic']['platforms']


def test_validate_profile_rejects_unknown_modules() -> None:
    """Unknown modules should cause profile validation to fail."""

    factory = EntityFactory(coordinator=None)
    modules = {'feeding': True, 'unknown': True}

    assert not factory.validate_profile_for_modules('standard', modules)


def test_should_create_entity_accepts_platform_enum() -> None:
    """Passing the Platform enum is supported and validated."""

    factory = EntityFactory(coordinator=None)

    assert factory.should_create_entity(
        'standard', _Platform.SENSOR, 'feeding', priority=6
    )


def test_should_create_entity_accepts_nested_enum_alias() -> None:
    """Nested enum aliases should resolve to their underlying platform."""

    factory = EntityFactory(coordinator=None)

    assert factory.should_create_entity(
        'standard', _NestedPlatformAlias.SENSOR, 'feeding', priority=6
    )


def test_should_create_entity_blocks_unknown_module() -> None:
    """Unknown modules are rejected even for high-priority requests."""

    factory = EntityFactory(coordinator=None)

    assert not factory.should_create_entity(
        'advanced', _Platform.SENSOR, 'unknown', priority=9
    )


def test_create_entity_config_normalises_output() -> None:
    """Entity configuration results expose canonical values."""

    factory = EntityFactory(coordinator=None)
    config = factory.create_entity_config(
        dog_id='buddy',
        entity_type=_Platform.BUTTON,
        module='feeding',
        profile='basic',
        priority=9,
    )

    assert config is not None
    assert config['entity_type'] == 'button'
    assert config['platform'] is _Platform.BUTTON


def test_create_entity_config_preserves_alias_enum_platform() -> None:
    """Entity configs should preserve alias enums when values match."""

    factory = EntityFactory(coordinator=None)

    config = factory.create_entity_config(
        dog_id='buddy',
        entity_type=_NestedPlatformAlias.SENSOR,
        module='feeding',
        profile='basic',
        priority=9,
    )

    assert config is not None
    assert config['platform'] is _NestedPlatformAlias.SENSOR


def test_create_entity_config_rejects_invalid_type() -> None:
    """Unsupported entity types should return ``None``."""

    factory = EntityFactory(coordinator=None)

    assert (
        factory.create_entity_config(
            dog_id='buddy',
            entity_type='unsupported',
            module='feeding',
            profile='standard',
        )
        is None
    )


def test_runtime_guard_expands_when_scheduler_starves() -> None:
    """The runtime guard should expand if operations are repeatedly delayed."""

    factory = EntityFactory(coordinator=None, enforce_min_runtime=True)
    baseline = factory._runtime_guard_floor

    factory._recalibrate_runtime_floor(baseline * (_RUNTIME_EXPAND_THRESHOLD + 2.5))

    boosted = factory._runtime_guard_floor
    assert boosted > baseline
    observed_ratio = (baseline * (_RUNTIME_EXPAND_THRESHOLD + 2.5)) / boosted
    assert observed_ratio <= _RUNTIME_TARGET_RATIO
    assert boosted <= _RUNTIME_MAX_FLOOR


def test_runtime_guard_contracts_after_sustained_stability() -> None:
    """The adaptive guard should relax when jitter subsides."""

    factory = EntityFactory(coordinator=None, enforce_min_runtime=True)
    factory._runtime_guard_floor = _RUNTIME_MAX_FLOOR

    factory._recalibrate_runtime_floor(
        factory._runtime_guard_floor * (_RUNTIME_CONTRACT_THRESHOLD - 0.4)
    )

    contracted = factory._runtime_guard_floor
    assert contracted < _RUNTIME_MAX_FLOOR
    assert contracted >= _MIN_OPERATION_DURATION


def test_runtime_guard_respects_minimum_floor() -> None:
    """Contraction must not push the guard below the static baseline."""

    factory = EntityFactory(coordinator=None, enforce_min_runtime=True)
    factory._runtime_guard_floor = _MIN_OPERATION_DURATION * 1.5

    factory._recalibrate_runtime_floor(_MIN_OPERATION_DURATION * 0.5)

    assert factory._runtime_guard_floor >= _MIN_OPERATION_DURATION


def test_runtime_guard_records_telemetry() -> None:
    """Runtime guard recalibrations should persist telemetry snapshots."""

    runtime_store = types.SimpleNamespace(performance_stats={})
    coordinator = types.SimpleNamespace(
        config_entry=types.SimpleNamespace(runtime_data=runtime_store)
    )

    factory = EntityFactory(coordinator=coordinator, enforce_min_runtime=True)
    baseline = factory._runtime_guard_floor
    assert baseline == pytest.approx(_MIN_OPERATION_DURATION)

    existing_metrics = runtime_store.performance_stats.get(
        'entity_factory_guard_metrics'
    )
    if isinstance(existing_metrics, dict):
        initial_samples = int(existing_metrics.get('samples', 0))
        initial_average = float(existing_metrics.get('average_duration', 0.0))
        initial_max = existing_metrics.get('max_duration')
        initial_min = existing_metrics.get('min_duration')
        initial_expansions = int(existing_metrics.get('expansions', 0))
        initial_contractions = int(existing_metrics.get('contractions', 0))
    else:
        initial_samples = 0
        initial_average = 0.0
        initial_max = None
        initial_min = None
        initial_expansions = 0
        initial_contractions = 0

    expand_duration = baseline * (_RUNTIME_TARGET_RATIO + 2.0)
    factory._recalibrate_runtime_floor(expand_duration)

    metrics = runtime_store.performance_stats['entity_factory_guard_metrics']
    assert metrics['expansions'] == initial_expansions + 1
    assert metrics['samples'] == initial_samples + 1
    assert metrics['runtime_floor'] >= baseline
    assert metrics['last_event'] == 'expand'
    assert metrics['last_actual_duration'] == pytest.approx(expand_duration)
    assert metrics['peak_runtime_floor'] >= metrics['runtime_floor']
    assert metrics['lowest_runtime_floor'] >= baseline - 1e-12
    assert metrics['lowest_runtime_floor'] <= metrics['runtime_floor'] + 1e-12
    assert metrics['last_floor_change'] == pytest.approx(
        metrics['runtime_floor'] - baseline
    )
    assert metrics['last_floor_change_ratio'] == pytest.approx(
        (metrics['runtime_floor'] - baseline) / baseline
    )
    first_sample = metrics['last_actual_duration']
    updated_average = ((initial_average * initial_samples) + first_sample) / (
        initial_samples + 1
    )
    assert metrics['average_duration'] == pytest.approx(updated_average)
    max_candidates = [first_sample]
    if isinstance(initial_max, (int, float)):
        max_candidates.append(float(initial_max))
    assert metrics['max_duration'] == pytest.approx(max(max_candidates))
    min_candidates = [first_sample]
    if isinstance(initial_min, (int, float)) and initial_samples > 0:
        min_candidates.append(float(initial_min))
    assert metrics['min_duration'] == pytest.approx(min(min_candidates))
    assert metrics['runtime_floor_delta'] == pytest.approx(
        metrics['runtime_floor'] - metrics['baseline_floor']
    )

    expanded_floor = factory._runtime_guard_floor
    contract_duration = expanded_floor * (_RUNTIME_CONTRACT_THRESHOLD - 0.2)
    factory._recalibrate_runtime_floor(contract_duration)

    metrics = runtime_store.performance_stats['entity_factory_guard_metrics']
    assert metrics['samples'] == initial_samples + 2
    assert metrics['contractions'] == initial_contractions + 1
    assert metrics['last_event'] == 'contract'
    assert metrics['last_actual_duration'] > 0
    assert metrics['peak_runtime_floor'] >= expanded_floor
    assert metrics['lowest_runtime_floor'] <= metrics['runtime_floor']
    assert metrics['last_floor_change'] == pytest.approx(
        metrics['runtime_floor'] - expanded_floor
    )
    assert metrics['last_floor_change_ratio'] == pytest.approx(
        metrics['last_floor_change'] / expanded_floor
    )
    second_sample = metrics['last_actual_duration']
    combined_average = (
        (initial_average * initial_samples) + first_sample + second_sample
    ) / (initial_samples + 2)
    assert metrics['average_duration'] == pytest.approx(combined_average)
    max_candidates = [first_sample, second_sample]
    if isinstance(initial_max, (int, float)):
        max_candidates.append(float(initial_max))
    assert metrics['max_duration'] == pytest.approx(max(max_candidates))
    min_candidates = [first_sample, second_sample]
    if isinstance(initial_min, (int, float)) and initial_samples > 0:
        min_candidates.append(float(initial_min))
    assert metrics['min_duration'] == pytest.approx(min(min_candidates))
    assert metrics['runtime_floor_delta'] == pytest.approx(
        metrics['runtime_floor'] - metrics['baseline_floor']
    )

    stable_duration = factory._runtime_guard_floor * 1.8
    factory._recalibrate_runtime_floor(stable_duration)

    metrics = runtime_store.performance_stats['entity_factory_guard_metrics']
    assert metrics['samples'] == initial_samples + 3
    assert metrics['stable_samples'] >= 1
    assert metrics['last_event'] == 'stable'
    assert metrics['consecutive_stable_samples'] >= 1
    assert metrics['longest_stable_run'] >= metrics['consecutive_stable_samples']
    assert metrics['stable_ratio'] == pytest.approx(
        metrics['stable_samples'] / metrics['samples']
    )
    assert metrics['expansion_ratio'] == pytest.approx(
        metrics['expansions'] / metrics['samples']
    )
    assert metrics['contraction_ratio'] == pytest.approx(
        metrics['contractions'] / metrics['samples']
    )
    assert metrics['volatility_ratio'] == pytest.approx(
        (metrics['expansions'] + metrics['contractions']) / metrics['samples']
    )

    recent = metrics['recent_durations']
    assert len(recent) == min(5, metrics['samples'])
    assert recent[-1] == pytest.approx(stable_duration)
    assert metrics['recent_average_duration'] == pytest.approx(
        sum(recent) / len(recent)
    )
    assert metrics['recent_max_duration'] == pytest.approx(max(recent))
    assert metrics['recent_min_duration'] == pytest.approx(min(recent))
    assert metrics['recent_duration_span'] == pytest.approx(
        metrics['recent_max_duration'] - metrics['recent_min_duration']
    )
    if metrics['runtime_floor'] > 0:
        assert metrics['jitter_ratio'] == pytest.approx(
            metrics['duration_span'] / metrics['runtime_floor']
        )
        assert metrics['recent_jitter_ratio'] == pytest.approx(
            metrics['recent_duration_span'] / metrics['runtime_floor']
        )

    assert metrics['recent_samples'] == len(recent)
    assert metrics['recent_events'][-1] == 'stable'
    assert metrics['recent_stable_samples'] <= metrics['recent_samples']
    assert metrics['recent_stable_ratio'] == pytest.approx(
        metrics['recent_stable_samples'] / metrics['recent_samples']
    )
    assert metrics['stability_trend'] == 'regressing'
