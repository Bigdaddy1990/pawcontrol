"""Performance benchmarks for PawControl integration.

This module contains performance tests and benchmarks to ensure the integration
meets quality standards for response time, throughput, and resource usage.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any

import pytest
from tests.helpers.factories import (
  create_mock_coordinator,
  create_test_coordinator_data,
  create_test_entry_data,
  create_test_entry_options,
)


@dataclass
class BenchmarkResult:
  """Performance benchmark result.

  Attributes:
      name: Benchmark name
      duration_ms: Duration in milliseconds
      iterations: Number of iterations
      avg_ms: Average time per iteration
      min_ms: Minimum time
      max_ms: Maximum time
      ops_per_sec: Operations per second
  """

  name: str
  duration_ms: float
  iterations: int
  avg_ms: float
  min_ms: float
  max_ms: float
  ops_per_sec: float

  def meets_target(self, target_ms: float) -> bool:
    """Check if benchmark meets target performance.

    Args:
        target_ms: Target time in milliseconds

    Returns:
        True if average time is under target
    """
    return self.avg_ms <= target_ms

  def __str__(self) -> str:
    """String representation of benchmark result."""
    return (
      f"{self.name}: {self.avg_ms:.2f}ms avg "
      f"({self.min_ms:.2f}-{self.max_ms:.2f}ms, "
      f"{self.ops_per_sec:.0f} ops/sec)"
    )


def benchmark(
  func: Any,
  *args: Any,
  iterations: int = 100,
  warmup: int = 10,
  **kwargs: Any,
) -> BenchmarkResult:
  """Benchmark a function.

  Args:
      func: Function to benchmark
      *args: Positional arguments
      iterations: Number of iterations
      warmup: Number of warmup iterations
      **kwargs: Keyword arguments

  Returns:
      BenchmarkResult

  Examples:
      >>> result = benchmark(lambda: sum(range(1000)), iterations=100)
      >>> assert result.avg_ms < 1.0
  """
  # Warmup
  for _ in range(warmup):
    func(*args, **kwargs)

  # Benchmark
  times: list[float] = []
  start_total = time.perf_counter()

  for _ in range(iterations):
    start = time.perf_counter()
    func(*args, **kwargs)
    end = time.perf_counter()
    times.append((end - start) * 1000)  # Convert to ms

  end_total = time.perf_counter()

  duration_ms = (end_total - start_total) * 1000
  avg_ms = sum(times) / len(times)
  min_ms = min(times)
  max_ms = max(times)
  ops_per_sec = iterations / ((end_total - start_total) or 0.001)

  return BenchmarkResult(
    name=func.__name__,
    duration_ms=duration_ms,
    iterations=iterations,
    avg_ms=avg_ms,
    min_ms=min_ms,
    max_ms=max_ms,
    ops_per_sec=ops_per_sec,
  )


async def benchmark_async(
  func: Any,
  *args: Any,
  iterations: int = 100,
  warmup: int = 10,
  **kwargs: Any,
) -> BenchmarkResult:
  """Benchmark an async function.

  Args:
      func: Async function to benchmark
      *args: Positional arguments
      iterations: Number of iterations
      warmup: Number of warmup iterations
      **kwargs: Keyword arguments

  Returns:
      BenchmarkResult
  """
  # Warmup
  for _ in range(warmup):
    await func(*args, **kwargs)

  # Benchmark
  times: list[float] = []
  start_total = time.perf_counter()

  for _ in range(iterations):
    start = time.perf_counter()
    await func(*args, **kwargs)
    end = time.perf_counter()
    times.append((end - start) * 1000)

  end_total = time.perf_counter()

  duration_ms = (end_total - start_total) * 1000
  avg_ms = sum(times) / len(times)
  min_ms = min(times)
  max_ms = max(times)
  ops_per_sec = iterations / ((end_total - start_total) or 0.001)

  return BenchmarkResult(
    name=func.__name__,
    duration_ms=duration_ms,
    iterations=iterations,
    avg_ms=avg_ms,
    min_ms=min_ms,
    max_ms=max_ms,
    ops_per_sec=ops_per_sec,
  )


class TestCoordinatorPerformance:
  """Performance tests for coordinator operations."""

  @pytest.mark.benchmark
  async def test_coordinator_update_performance(self):
    """Benchmark coordinator update operation.

    Target: < 500ms average
    """
    coordinator = create_mock_coordinator()

    async def update_operation():
      # Simulate coordinator update
      coordinator.data = create_test_coordinator_data(dog_ids=["dog_1", "dog_2"])
      await asyncio.sleep(0.001)  # Simulate network delay

    result = await benchmark_async(update_operation, iterations=50, warmup=5)

    print(f"\n{result}")
    assert result.meets_target(500.0), (
      f"Coordinator update too slow: {result.avg_ms:.2f}ms"
    )

  @pytest.mark.benchmark
  async def test_coordinator_data_access_performance(self):
    """Benchmark coordinator data access.

    Target: < 1ms average
    """
    coordinator = create_mock_coordinator(
      data=create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(10)])
    )

    def access_operation():
      # Access data for all dogs
      for dog_id in coordinator.data:
        _ = coordinator.data[dog_id]

    result = benchmark(access_operation, iterations=1000, warmup=100)

    print(f"\n{result}")
    assert result.meets_target(1.0), f"Data access too slow: {result.avg_ms:.2f}ms"

  @pytest.mark.benchmark
  def test_large_dataset_handling(self):
    """Benchmark handling of large number of dogs.

    Target: < 100ms for 100 dogs
    """

    def create_large_dataset():
      return create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(100)])

    result = benchmark(create_large_dataset, iterations=50, warmup=5)

    print(f"\n{result}")
    assert result.meets_target(100.0), (
      f"Large dataset creation too slow: {result.avg_ms:.2f}ms"
    )


class TestValidationPerformance:
  """Performance tests for validation operations."""

  @pytest.mark.benchmark
  def test_gps_validation_performance(self):
    """Benchmark GPS coordinate validation.

    Target: < 0.1ms average
    """
    from custom_components.pawcontrol.validation import validate_gps_coordinates

    def validate_operation():
      validate_gps_coordinates(45.5231, -122.6765)

    result = benchmark(validate_operation, iterations=10000, warmup=1000)

    print(f"\n{result}")
    assert result.meets_target(0.1), f"GPS validation too slow: {result.avg_ms:.2f}ms"

  @pytest.mark.benchmark
  def test_dog_name_validation_performance(self):
    """Benchmark dog name validation.

    Target: < 0.1ms average
    """
    from custom_components.pawcontrol.validation import validate_dog_name

    def validate_operation():
      validate_dog_name("Test Dog")

    result = benchmark(validate_operation, iterations=10000, warmup=1000)

    print(f"\n{result}")
    assert result.meets_target(0.1), f"Name validation too slow: {result.avg_ms:.2f}ms"

  @pytest.mark.benchmark
  def test_entity_id_validation_performance(self):
    """Benchmark entity ID validation.

    Target: < 0.1ms average
    """
    from custom_components.pawcontrol.validation import validate_entity_id

    def validate_operation():
      validate_entity_id("sensor.test_sensor")

    result = benchmark(validate_operation, iterations=10000, warmup=1000)

    print(f"\n{result}")
    assert result.meets_target(0.1), (
      f"Entity ID validation too slow: {result.avg_ms:.2f}ms"
    )


class TestDiffingPerformance:
  """Performance tests for diffing operations."""

  @pytest.mark.benchmark
  def test_coordinator_diff_performance(self):
    """Benchmark coordinator data diffing.

    Target: < 5ms for 10 dogs
    """
    from custom_components.pawcontrol.coordinator_diffing import (
      compute_coordinator_diff,
    )

    old_data = create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(10)])
    new_data = create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(10)])

    # Modify one dog's data
    new_data["dog_5"]["gps"]["latitude"] = 46.0

    def diff_operation():
      compute_coordinator_diff(old_data, new_data)

    result = benchmark(diff_operation, iterations=1000, warmup=100)

    print(f"\n{result}")
    assert result.meets_target(5.0), f"Diffing too slow: {result.avg_ms:.2f}ms"

  @pytest.mark.benchmark
  def test_diff_large_dataset_performance(self):
    """Benchmark diffing with large datasets.

    Target: < 50ms for 100 dogs
    """
    from custom_components.pawcontrol.coordinator_diffing import (
      compute_coordinator_diff,
    )

    old_data = create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(100)])
    new_data = create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(100)])

    # Modify some data
    for i in range(0, 100, 10):
      new_data[f"dog_{i}"]["gps"]["latitude"] += 0.01

    def diff_operation():
      compute_coordinator_diff(old_data, new_data)

    result = benchmark(diff_operation, iterations=100, warmup=10)

    print(f"\n{result}")
    assert result.meets_target(50.0), f"Large diff too slow: {result.avg_ms:.2f}ms"


class TestSerializationPerformance:
  """Performance tests for serialization operations."""

  @pytest.mark.benchmark
  def test_coordinator_data_serialization(self):
    """Benchmark coordinator data serialization.

    Target: < 10ms for 10 dogs
    """
    import json

    data = create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(10)])

    def serialize_operation():
      # Convert to JSON-serializable format
      serializable = {}
      for dog_id, dog_data in data.items():
        serializable[dog_id] = {
          "gps": dog_data.get("gps", {}),
          "walk": dog_data.get("walk", {}),
        }
      json.dumps(serializable)

    result = benchmark(serialize_operation, iterations=1000, warmup=100)

    print(f"\n{result}")
    assert result.meets_target(10.0), f"Serialization too slow: {result.avg_ms:.2f}ms"


class TestMemoryUsage:
  """Memory usage tests."""

  @pytest.mark.benchmark
  def test_coordinator_memory_usage(self):
    """Test memory usage with large number of dogs.

    Target: < 50MB for 100 dogs
    """
    import sys

    # Create large dataset
    data = create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(100)])

    # Estimate memory usage (rough approximation)
    size_bytes = sys.getsizeof(data)
    for dog_id, dog_data in data.items():
      size_bytes += sys.getsizeof(dog_id)
      size_bytes += sys.getsizeof(dog_data)
      for key, value in dog_data.items():
        size_bytes += sys.getsizeof(key)
        size_bytes += sys.getsizeof(value)

    size_mb = size_bytes / (1024 * 1024)

    print(f"\nMemory usage for 100 dogs: {size_mb:.2f} MB")
    assert size_mb < 50.0, f"Memory usage too high: {size_mb:.2f} MB"


class TestConcurrency:
  """Concurrency performance tests."""

  @pytest.mark.benchmark
  async def test_concurrent_updates(self):
    """Test concurrent coordinator updates.

    Target: < 1000ms for 10 concurrent updates
    """
    coordinator = create_mock_coordinator()

    async def concurrent_update():
      tasks = []
      for i in range(10):

        async def update(idx):
          coordinator.data = create_test_coordinator_data(dog_ids=[f"dog_{idx}"])
          await asyncio.sleep(0.001)

        tasks.append(update(i))

      await asyncio.gather(*tasks)

    result = await benchmark_async(concurrent_update, iterations=10, warmup=2)

    print(f"\n{result}")
    assert result.meets_target(1000.0), (
      f"Concurrent updates too slow: {result.avg_ms:.2f}ms"
    )


# Performance targets summary

PERFORMANCE_TARGETS = {
  "coordinator_update": 500.0,  # ms
  "data_access": 1.0,  # ms
  "large_dataset": 100.0,  # ms
  "gps_validation": 0.1,  # ms
  "name_validation": 0.1,  # ms
  "entity_validation": 0.1,  # ms
  "diffing": 5.0,  # ms
  "large_diff": 50.0,  # ms
  "serialization": 10.0,  # ms
  "concurrent_updates": 1000.0,  # ms
  "memory_100_dogs": 50.0,  # MB
}


def print_performance_summary(results: list[BenchmarkResult]) -> None:
  """Print performance benchmark summary.

  Args:
      results: List of benchmark results
  """
  print("\n" + "=" * 80)
  print("PERFORMANCE BENCHMARK SUMMARY")
  print("=" * 80)

  for result in results:
    status = "✓" if result.avg_ms < 100 else "⚠"
    print(f"{status} {result}")

  print("=" * 80)
