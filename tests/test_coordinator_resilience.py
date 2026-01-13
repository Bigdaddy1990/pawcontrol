"""Tests for coordinator resilience handling."""

from __future__ import annotations

import asyncio
import logging
from typing import cast
from unittest.mock import AsyncMock

from custom_components.pawcontrol.coordinator_runtime import (
    AdaptivePollingController,
    CoordinatorRuntime,
)
from custom_components.pawcontrol.coordinator_support import (
    CoordinatorMetrics,
    DogConfigRegistry,
)
from custom_components.pawcontrol.exceptions import NetworkError, RateLimitError
from custom_components.pawcontrol.module_adapters import CoordinatorModuleAdapters
from custom_components.pawcontrol.resilience import ResilienceManager, RetryConfig
from custom_components.pawcontrol.types import CoordinatorDogData


def _build_runtime(
    hass: object,
    dog_ids: list[str],
) -> tuple[CoordinatorRuntime, DogConfigRegistry]:
    registry = DogConfigRegistry(
        [
            {
                'dog_id': dog_id,
                'dog_name': dog_id.title(),
            }
            for dog_id in dog_ids
        ]
    )

    runtime = CoordinatorRuntime(
        registry=registry,
        modules=cast(CoordinatorModuleAdapters, object()),
        resilience_manager=ResilienceManager(hass),
        retry_config=RetryConfig(
            max_attempts=1,
            initial_delay=0.0,
            max_delay=0.0,
            jitter=False,
        ),
        metrics=CoordinatorMetrics(),
        adaptive_polling=AdaptivePollingController(initial_interval_seconds=60.0),
        logger=logging.getLogger('tests.pawcontrol.resilience'),
    )
    return runtime, registry


def _baseline_data(
    registry: DogConfigRegistry, dog_id: str, status: str
) -> CoordinatorDogData:
    dog_info = registry.get(dog_id)
    return {
        'dog_info': dog_info if dog_info is not None else {'dog_id': dog_id},
        'status': status,
        'last_update': 'previous',
    }


def test_execute_cycle_handles_offline_errors(mock_hass: object) -> None:
    runtime, registry = _build_runtime(mock_hass, ['buddy', 'offline'])

    current_data: dict[str, CoordinatorDogData] = {
        'buddy': _baseline_data(registry, 'buddy', 'online'),
        'offline': _baseline_data(registry, 'offline', 'offline'),
    }

    async def fake_execute(_func: object, dog_id: str, **_kwargs: object) -> object:
        if dog_id == 'offline':
            raise ConnectionError('Device offline')
        return {
            'dog_info': registry.get(dog_id),
            'status': 'online',
            'last_update': 'now',
        }

    runtime._resilience.execute_with_resilience = AsyncMock(side_effect=fake_execute)

    data, cycle = asyncio.run(
        runtime.execute_cycle(
            ['buddy', 'offline'],
            current_data,
            empty_payload_factory=registry.empty_payload,
        )
    )

    assert data['offline'] == current_data['offline']
    assert data['buddy']['status'] == 'online'
    assert cycle.errors == 1
    assert cycle.success


def test_execute_cycle_handles_rate_limit_errors(mock_hass: object) -> None:
    runtime, registry = _build_runtime(mock_hass, ['buddy', 'rate'])

    current_data: dict[str, CoordinatorDogData] = {
        'buddy': _baseline_data(registry, 'buddy', 'online'),
        'rate': _baseline_data(registry, 'rate', 'online'),
    }

    async def fake_execute(_func: object, dog_id: str, **_kwargs: object) -> object:
        if dog_id == 'rate':
            raise RateLimitError('dog_data', limit='1/min', retry_after=60)
        return {
            'dog_info': registry.get(dog_id),
            'status': 'online',
            'last_update': 'now',
        }

    runtime._resilience.execute_with_resilience = AsyncMock(side_effect=fake_execute)

    data, cycle = asyncio.run(
        runtime.execute_cycle(
            ['buddy', 'rate'],
            current_data,
            empty_payload_factory=registry.empty_payload,
        )
    )

    assert data['rate'] == current_data['rate']
    assert data['buddy']['status'] == 'online'
    assert cycle.errors == 1
    assert cycle.success


def test_execute_cycle_handles_network_errors(mock_hass: object) -> None:
    runtime, registry = _build_runtime(mock_hass, ['buddy', 'network'])

    current_data: dict[str, CoordinatorDogData] = {
        'buddy': _baseline_data(registry, 'buddy', 'online'),
        'network': _baseline_data(registry, 'network', 'offline'),
    }

    async def fake_execute(_func: object, dog_id: str, **_kwargs: object) -> object:
        if dog_id == 'network':
            raise NetworkError('Temporary network failure')
        return {
            'dog_info': registry.get(dog_id),
            'status': 'online',
            'last_update': 'now',
        }

    runtime._resilience.execute_with_resilience = AsyncMock(side_effect=fake_execute)

    data, cycle = asyncio.run(
        runtime.execute_cycle(
            ['buddy', 'network'],
            current_data,
            empty_payload_factory=registry.empty_payload,
        )
    )

    assert data['network'] == current_data['network']
    assert data['buddy']['status'] == 'online'
    assert cycle.errors == 1
    assert cycle.success


def test_execute_cycle_backs_off_on_errors(mock_hass: object) -> None:
    runtime, registry = _build_runtime(mock_hass, ['buddy', 'flaky'])

    current_data: dict[str, CoordinatorDogData] = {
        'buddy': _baseline_data(registry, 'buddy', 'online'),
        'flaky': _baseline_data(registry, 'flaky', 'online'),
    }

    async def fake_execute(_func: object, dog_id: str, **_kwargs: object) -> object:
        if dog_id == 'flaky':
            raise NetworkError('Intermittent connectivity')
        return {
            'dog_info': registry.get(dog_id),
            'status': 'online',
            'last_update': 'now',
        }

    runtime._resilience.execute_with_resilience = AsyncMock(side_effect=fake_execute)

    initial_interval = runtime._adaptive_polling.current_interval
    data, cycle = asyncio.run(
        runtime.execute_cycle(
            ['buddy', 'flaky'],
            current_data,
            empty_payload_factory=registry.empty_payload,
        )
    )

    assert data['flaky'] == current_data['flaky']
    assert cycle.errors == 1
    assert cycle.success
    assert cycle.new_interval > initial_interval
