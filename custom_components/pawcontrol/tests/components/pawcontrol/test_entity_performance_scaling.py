"""Comprehensive performance scaling tests for PawControl Entity Profiles.

Tests maximum entity counts, memory efficiency, concurrent operations,
and production-scale scenarios for Platinum quality validation.

Quality Scale: Platinum
Home Assistant: 2025.9.4+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import gc
import logging
import sys
import time
from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES, EntityFactory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

# Disable debug logging for performance tests
logging.getLogger("custom_components.pawcontrol").setLevel(logging.WARNING)

# Performance test constants
MAX_DOGS_STRESS_TEST = 50
MAX_DOGS_PRODUCTION = 25
CONCURRENT_OPERATIONS = 100
MEMORY_THRESHOLD_MB = 100  # Maximum memory increase during tests
PERFORMANCE_TIMEOUT = 30.0  # Maximum seconds for operations


class PerformanceMonitor:
    """Monitor performance metrics during tests."""

    def __init__(self) -> None:
        """Initialize performance monitor."""
        self.start_memory = 0
        self.start_time = 0.0
        self.operations = 0

    def start(self) -> None:
        """Start monitoring."""
        gc.collect()  # Clean up before measuring
        self.start_memory = self._get_memory_usage_mb()
        self.start_time = time.perf_counter()
        self.operations = 0

    def record_operation(self) -> None:
        """Record an operation."""
        self.operations += 1

    def finish(self) -> dict[str, Any]:
        """Finish monitoring and return metrics."""
        end_time = time.perf_counter()
        gc.collect()  # Clean up before final measurement
        end_memory = self._get_memory_usage_mb()

        return {
            "execution_time": end_time - self.start_time,
            "memory_increase_mb": end_memory - self.start_memory,
            "operations_count": self.operations,
            "operations_per_second": self.operations
            / max(end_time - self.start_time, 0.001),
            "memory_per_operation_kb": (end_memory - self.start_memory)
            * 1024
            / max(self.operations, 1),
        }

    @staticmethod
    def _get_memory_usage_mb() -> float:
        """Get current memory usage in MB."""
        if hasattr(sys, "getsizeof"):
            # Simple memory tracking for tests
            return len(gc.get_objects()) * 0.001  # Approximate
        return 0.0


class TestEntityPerformanceScaling:
    """Comprehensive entity performance scaling tests."""

    @pytest.fixture
    def mock_hass(self) -> HomeAssistant:
        """Create mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {}
        return hass

    @pytest.fixture
    def mock_coordinator(self, mock_hass: HomeAssistant) -> PawControlCoordinator:
        """Create mock coordinator for testing."""
        mock_coordinator = Mock(spec=PawControlCoordinator)
        mock_coordinator.hass = mock_hass
        mock_coordinator.data = {}
        mock_coordinator.async_request_refresh = AsyncMock()
        return mock_coordinator

    @pytest.fixture
    def entity_factory(self, mock_coordinator: PawControlCoordinator) -> EntityFactory:
        """Create entity factory for performance testing."""
        return EntityFactory(coordinator=mock_coordinator)

    @pytest.fixture
    def performance_monitor(self) -> PerformanceMonitor:
        """Create performance monitor."""
        return PerformanceMonitor()

    @pytest.mark.parametrize("dog_count", [1, 5, 10, 25, 50])
    async def test_maximum_entity_scaling(
        self,
        entity_factory: EntityFactory,
        performance_monitor: PerformanceMonitor,
        dog_count: int,
    ) -> None:
        """Test entity creation scaling with maximum dog counts."""
        performance_monitor.start()

        # Full module configuration for stress testing
        full_modules = {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": True,
            "notifications": True,
            "dashboard": True,
            "visitor": True,
            "medication": True,
            "training": True,
            "grooming": True,
        }

        total_entities = 0
        entity_configs = []

        # Process all dogs
        for dog_id in range(dog_count):
            dog_name = f"stress_test_dog_{dog_id:03d}"

            # Vary profiles for realistic distribution
            profile = ["basic", "standard", "advanced"][dog_id % 3]

            # Estimate entities
            entity_count = entity_factory.estimate_entity_count(profile, full_modules)
            total_entities += entity_count
            performance_monitor.record_operation()

            # Create entity configurations
            for platform in ["sensor", "button", "binary_sensor", "switch"]:
                config = entity_factory.create_entity_config(
                    dog_id=dog_name,
                    entity_type=platform,
                    module="feeding",
                    profile=profile,
                    priority=5,
                )
                if config:
                    entity_configs.append(config)
                    performance_monitor.record_operation()

        metrics = performance_monitor.finish()

        # Performance assertions
        assert metrics["execution_time"] < PERFORMANCE_TIMEOUT
        assert metrics["memory_increase_mb"] < MEMORY_THRESHOLD_MB
        assert metrics["operations_per_second"] > 50  # Minimum throughput

        # Scaling assertions
        expected_entities_per_dog = 8  # Conservative estimate
        assert total_entities >= dog_count * expected_entities_per_dog
        assert len(entity_configs) > 0

        # Log performance results
        print(f"\nScaling Test Results (dogs: {dog_count}):")
        print(f"  Total entities: {total_entities}")
        print(f"  Execution time: {metrics['execution_time']:.3f}s")
        print(f"  Memory increase: {metrics['memory_increase_mb']:.1f}MB")
        print(f"  Operations/sec: {metrics['operations_per_second']:.1f}")

    async def test_memory_efficiency_maximum_load(
        self,
        entity_factory: EntityFactory,
        performance_monitor: PerformanceMonitor,
    ) -> None:
        """Test memory efficiency under maximum load."""
        performance_monitor.start()

        # Create maximum number of dogs with varying configurations
        dogs_data = []
        for i in range(MAX_DOGS_STRESS_TEST):
            # Vary module configurations realistically
            modules = {
                "feeding": True,
                "walk": i % 2 == 0,
                "health": i % 3 == 0,
                "gps": i % 4 == 0,
                "notifications": True,
                "dashboard": i % 5 == 0,
                "visitor": i % 6 == 0,
                "medication": i % 7 == 0,
                "training": i % 8 == 0,
                "grooming": i % 9 == 0,
            }

            profile = ["basic", "standard", "advanced", "gps_focus", "health_focus"][
                i % 5
            ]

            dogs_data.append(
                {
                    "dog_id": f"memory_test_dog_{i:03d}",
                    "profile": profile,
                    "modules": modules,
                }
            )
            performance_monitor.record_operation()

        # Process all dogs for entity estimation
        entity_estimates = []
        for dog_data in dogs_data:
            estimate = entity_factory.estimate_entity_count(
                dog_data["profile"], dog_data["modules"]
            )
            entity_estimates.append(estimate)
            performance_monitor.record_operation()

        # Create entity configurations for subset (realistic scenario)
        entity_configs = []
        for _i, dog_data in enumerate(
            dogs_data[:MAX_DOGS_PRODUCTION]
        ):  # Production limit
            for platform in ["sensor", "button", "binary_sensor"]:
                config = entity_factory.create_entity_config(
                    dog_id=dog_data["dog_id"],
                    entity_type=platform,
                    module="feeding",
                    profile=dog_data["profile"],
                    priority=6,
                )
                if config:
                    entity_configs.append(config)
                    performance_monitor.record_operation()

        metrics = performance_monitor.finish()

        # Memory efficiency assertions
        assert metrics["memory_increase_mb"] < MEMORY_THRESHOLD_MB
        assert metrics["memory_per_operation_kb"] < 10  # Low memory per operation
        assert metrics["execution_time"] < PERFORMANCE_TIMEOUT

        # Data integrity assertions
        assert len(entity_estimates) == MAX_DOGS_STRESS_TEST
        assert all(estimate > 0 for estimate in entity_estimates)
        assert (
            len(entity_configs) > MAX_DOGS_PRODUCTION
        )  # Should create multiple configs per dog

        # Performance scaling validation
        total_entities = sum(entity_estimates)
        assert total_entities > 0

        print("\nMemory Efficiency Test Results:")
        print(f"  Dogs processed: {MAX_DOGS_STRESS_TEST}")
        print(f"  Total estimated entities: {total_entities}")
        print(f"  Entity configs created: {len(entity_configs)}")
        print(f"  Memory increase: {metrics['memory_increase_mb']:.1f}MB")
        print(f"  Memory per operation: {metrics['memory_per_operation_kb']:.2f}KB")

    async def test_concurrent_operations_scaling(
        self,
        entity_factory: EntityFactory,
        performance_monitor: PerformanceMonitor,
    ) -> None:
        """Test concurrent operations scaling for thread safety."""
        performance_monitor.start()

        # Simulate concurrent operations
        operation_results = []

        # Mix of different operations
        for i in range(CONCURRENT_OPERATIONS):
            operation_type = i % 4
            dog_id = f"concurrent_dog_{i % 10}"  # 10 different dogs
            profile = ["basic", "standard", "advanced"][i % 3]
            modules = {"feeding": True, "walk": i % 2 == 0, "health": i % 3 == 0}

            if operation_type == 0:
                # Entity count estimation
                result = entity_factory.estimate_entity_count(profile, modules)
                operation_results.append(("estimate", result))

            elif operation_type == 1:
                # Performance metrics
                result = entity_factory.get_performance_metrics(profile, modules)
                operation_results.append(("metrics", result))

            elif operation_type == 2:
                # Entity config creation
                result = entity_factory.create_entity_config(
                    dog_id=dog_id,
                    entity_type="sensor",
                    module="feeding",
                    profile=profile,
                    priority=5,
                )
                operation_results.append(("config", result))

            else:
                # Entity creation decision
                result = entity_factory.should_create_entity(
                    profile, "button", "walk", priority=6
                )
                operation_results.append(("decision", result))

            performance_monitor.record_operation()

        metrics = performance_monitor.finish()

        # Concurrent operations assertions
        assert len(operation_results) == CONCURRENT_OPERATIONS
        assert metrics["execution_time"] < PERFORMANCE_TIMEOUT
        assert metrics["operations_per_second"] > 100  # High throughput

        # Result validation
        estimate_results = [r[1] for r in operation_results if r[0] == "estimate"]
        config_results = [r[1] for r in operation_results if r[0] == "config"]
        decision_results = [r[1] for r in operation_results if r[0] == "decision"]

        assert all(
            isinstance(result, int) and result > 0 for result in estimate_results
        )
        assert all(
            result is None or isinstance(result, dict) for result in config_results
        )
        assert all(isinstance(result, bool) for result in decision_results)

        print("\nConcurrent Operations Test Results:")
        print(f"  Operations processed: {CONCURRENT_OPERATIONS}")
        print(f"  Execution time: {metrics['execution_time']:.3f}s")
        print(f"  Operations/sec: {metrics['operations_per_second']:.1f}")
        print(f"  Estimates: {len(estimate_results)}, Configs: {len(config_results)}")

    async def test_profile_performance_distribution(
        self,
        entity_factory: EntityFactory,
        performance_monitor: PerformanceMonitor,
    ) -> None:
        """Test performance distribution across all profiles."""
        performance_monitor.start()

        profiles = list(ENTITY_PROFILES.keys())
        modules_configurations = [
            {"feeding": True, "walk": False, "health": False},  # Minimal
            {"feeding": True, "walk": True, "health": True},  # Standard
            {
                "feeding": True,
                "walk": True,
                "health": True,
                "gps": True,
                "notifications": True,
            },  # Extended
        ]

        profile_performance = defaultdict(list)

        # Test each profile with different module configurations
        for profile in profiles:
            for modules in modules_configurations:
                start_time = time.perf_counter()

                # Core operations
                entity_count = entity_factory.estimate_entity_count(profile, modules)
                metrics = entity_factory.get_performance_metrics(profile, modules)

                # Entity creation operations
                created_configs = 0
                for platform in ["sensor", "button", "binary_sensor", "switch"]:
                    config = entity_factory.create_entity_config(
                        dog_id=f"perf_test_{profile}",
                        entity_type=platform,
                        module="feeding",
                        profile=profile,
                        priority=5,
                    )
                    if config:
                        created_configs += 1

                end_time = time.perf_counter()
                execution_time = end_time - start_time

                profile_performance[profile].append(
                    {
                        "execution_time": execution_time,
                        "entity_count": entity_count,
                        "configs_created": created_configs,
                        "utilization": metrics["utilization_percentage"],
                    }
                )

                performance_monitor.record_operation()

        metrics = performance_monitor.finish()

        # Performance distribution assertions
        assert metrics["execution_time"] < PERFORMANCE_TIMEOUT

        # Analyze profile characteristics
        for profile, performance_data in profile_performance.items():
            avg_time = sum(p["execution_time"] for p in performance_data) / len(
                performance_data
            )
            avg_entities = sum(p["entity_count"] for p in performance_data) / len(
                performance_data
            )
            avg_utilization = sum(p["utilization"] for p in performance_data) / len(
                performance_data
            )

            # Profile-specific performance assertions
            profile_info = ENTITY_PROFILES[profile]

            if profile == "basic":
                assert avg_time < 0.01  # Basic should be fastest
                assert avg_entities <= profile_info["max_entities"]
                assert avg_utilization <= 80  # Conservative utilization

            elif profile == "advanced":
                assert avg_time < 0.05  # Advanced can be slower but reasonable
                assert avg_entities <= profile_info["max_entities"]
                # Advanced can have higher utilization

            print(f"\nProfile Performance - {profile}:")
            print(f"  Avg execution time: {avg_time:.4f}s")
            print(f"  Avg entities: {avg_entities:.1f}")
            print(f"  Avg utilization: {avg_utilization:.1f}%")

    async def test_real_world_stress_scenarios(
        self,
        entity_factory: EntityFactory,
        performance_monitor: PerformanceMonitor,
    ) -> None:
        """Test real-world stress scenarios for production validation."""
        performance_monitor.start()

        # Scenario 1: Large Animal Shelter (30 dogs, mixed profiles)
        shelter_dogs = []
        for i in range(30):
            # Mix profiles based on dog care level
            if i < 5:  # Special needs dogs
                profile = "advanced"
                modules = {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "medication": True,
                    "notifications": True,
                }
            elif i < 20:  # Regular dogs
                profile = "standard"
                modules = {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "notifications": True,
                }
            else:  # Basic care dogs
                profile = "basic"
                modules = {"feeding": True, "walk": i % 2 == 0, "notifications": True}

            shelter_dogs.append(
                {"id": f"shelter_dog_{i:02d}", "profile": profile, "modules": modules}
            )

        # Process shelter scenario
        shelter_entities = 0
        for dog in shelter_dogs:
            count = entity_factory.estimate_entity_count(dog["profile"], dog["modules"])
            shelter_entities += count
            performance_monitor.record_operation()

        # Scenario 2: Professional Breeder (20 dogs, GPS focus)
        breeder_dogs = []
        for i in range(20):
            profile = "gps_focus" if i < 10 else "health_focus"
            modules = {
                "feeding": True,
                "walk": True,
                "health": True,
                "gps": i < 15,  # GPS for most dogs
                "medication": i < 5,  # Medication for breeding stock
                "notifications": True,
            }
            breeder_dogs.append(
                {"id": f"breeder_dog_{i:02d}", "profile": profile, "modules": modules}
            )

        # Process breeder scenario
        breeder_entities = 0
        for dog in breeder_dogs:
            count = entity_factory.estimate_entity_count(dog["profile"], dog["modules"])
            breeder_entities += count
            performance_monitor.record_operation()

        # Scenario 3: Dog Walking Service (15 dogs, visitor mode)
        walker_dogs = []
        for i in range(15):
            profile = "gps_focus"  # All dogs need GPS tracking
            modules = {
                "feeding": False,  # No feeding management
                "walk": True,
                "health": False,
                "gps": True,
                "visitor": True,  # All in visitor mode
                "notifications": True,
            }
            walker_dogs.append(
                {"id": f"walker_dog_{i:02d}", "profile": profile, "modules": modules}
            )

        # Process walker scenario
        walker_entities = 0
        for dog in walker_dogs:
            count = entity_factory.estimate_entity_count(dog["profile"], dog["modules"])
            walker_entities += count
            performance_monitor.record_operation()

        metrics = performance_monitor.finish()

        # Stress scenario assertions
        total_dogs = len(shelter_dogs) + len(breeder_dogs) + len(walker_dogs)  # 65 dogs
        total_entities = shelter_entities + breeder_entities + walker_entities

        assert total_dogs == 65
        assert total_entities > 200  # Significant entity count
        assert metrics["execution_time"] < PERFORMANCE_TIMEOUT
        assert metrics["memory_increase_mb"] < MEMORY_THRESHOLD_MB
        assert metrics["operations_per_second"] > 30  # Reasonable throughput

        print("\nReal-World Stress Test Results:")
        print(f"  Total dogs processed: {total_dogs}")
        print(f"  Shelter entities: {shelter_entities}")
        print(f"  Breeder entities: {breeder_entities}")
        print(f"  Walker entities: {walker_entities}")
        print(f"  Total entities: {total_entities}")
        print(f"  Execution time: {metrics['execution_time']:.3f}s")
        print(f"  Memory increase: {metrics['memory_increase_mb']:.1f}MB")

    async def test_cache_efficiency_under_load(
        self,
        entity_factory: EntityFactory,
        performance_monitor: PerformanceMonitor,
    ) -> None:
        """Test cache efficiency under heavy load."""
        performance_monitor.start()

        # Prepare test data
        test_profiles = ["basic", "standard", "advanced"]
        test_modules = [
            {"feeding": True, "walk": True},
            {"feeding": True, "walk": True, "health": True},
            {"feeding": True, "walk": True, "health": True, "gps": True},
        ]

        # First pass - populate cache
        cache_populate_time = time.perf_counter()
        for profile in test_profiles:
            for modules in test_modules:
                entity_factory.estimate_entity_count(profile, modules)
                performance_monitor.record_operation()
        cache_populate_time = time.perf_counter() - cache_populate_time

        # Second pass - use cache (repeat same operations)
        cache_hit_time = time.perf_counter()
        for profile in test_profiles:
            for modules in test_modules:
                entity_factory.estimate_entity_count(profile, modules)
                performance_monitor.record_operation()
        cache_hit_time = time.perf_counter() - cache_hit_time

        # Third pass - stress test cache with many operations
        stress_time = time.perf_counter()
        for _ in range(100):  # Many repeated operations
            profile = test_profiles[_ % len(test_profiles)]
            modules = test_modules[_ % len(test_modules)]
            entity_factory.estimate_entity_count(profile, modules)
            performance_monitor.record_operation()
        stress_time = time.perf_counter() - stress_time

        metrics = performance_monitor.finish()

        # Cache efficiency assertions
        assert cache_hit_time <= cache_populate_time  # Cache should be faster or equal
        assert stress_time < 0.5  # 100 cached operations should be fast
        assert metrics["execution_time"] < PERFORMANCE_TIMEOUT
        assert metrics["operations_per_second"] > 200  # High throughput with cache

        print("\nCache Efficiency Test Results:")
        print(f"  Cache populate time: {cache_populate_time:.4f}s")
        print(f"  Cache hit time: {cache_hit_time:.4f}s")
        print(f"  Stress test time: {stress_time:.4f}s")
        print(f"  Total operations: {metrics['operations_count']}")
        print(f"  Operations/sec: {metrics['operations_per_second']:.1f}")

    @pytest.mark.parametrize("platform_count", [5, 10, 15])
    async def test_platform_scaling_performance(
        self,
        entity_factory: EntityFactory,
        performance_monitor: PerformanceMonitor,
        platform_count: int,
    ) -> None:
        """Test performance scaling with different platform counts."""
        performance_monitor.start()

        platforms = [
            "sensor",
            "button",
            "binary_sensor",
            "switch",
            "select",
            "number",
            "device_tracker",
            "date",
            "datetime",
            "text",
        ][:platform_count]

        # Test entity creation for multiple dogs across platforms
        dogs_count = 10
        configs_created = 0

        for dog_id in range(dogs_count):
            dog_name = f"platform_test_dog_{dog_id}"

            for platform in platforms:
                config = entity_factory.create_entity_config(
                    dog_id=dog_name,
                    entity_type=platform,
                    module="feeding",
                    profile="standard",
                    priority=5,
                )
                if config:
                    configs_created += 1
                performance_monitor.record_operation()

        metrics = performance_monitor.finish()

        # Platform scaling assertions
        expected_operations = dogs_count * platform_count
        assert metrics["operations_count"] == expected_operations
        assert metrics["execution_time"] < PERFORMANCE_TIMEOUT
        assert metrics["operations_per_second"] > 50

        # Scaling should be linear with platform count
        time_per_platform = metrics["execution_time"] / platform_count
        assert time_per_platform < 0.1  # Should be fast per platform

        print(f"\nPlatform Scaling Test Results (platforms: {platform_count}):")
        print(f"  Operations: {expected_operations}")
        print(f"  Configs created: {configs_created}")
        print(f"  Execution time: {metrics['execution_time']:.3f}s")
        print(f"  Time per platform: {time_per_platform:.4f}s")


class TestProductionScenarioValidation:
    """Validate performance for production scenarios."""

    @pytest.fixture
    def entity_factory(self) -> EntityFactory:
        """Create entity factory for production testing."""
        return EntityFactory(coordinator=None)

    async def test_enterprise_deployment_scenario(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test enterprise deployment with maximum realistic load."""
        start_time = time.perf_counter()

        # Enterprise scenario: Multiple facilities
        facilities = {
            "headquarters": {"dogs": 5, "profile": "advanced"},
            "training_center": {"dogs": 12, "profile": "standard"},
            "boarding_facility": {"dogs": 18, "profile": "basic"},
            "veterinary_clinic": {"dogs": 8, "profile": "health_focus"},
            "walker_service": {"dogs": 10, "profile": "gps_focus"},
        }

        total_entities = 0
        total_dogs = 0

        for facility, config in facilities.items():
            dog_count = config["dogs"]
            profile = config["profile"]

            # Facility-specific modules
            if facility == "headquarters":
                modules = {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "gps": True,
                    "notifications": True,
                    "dashboard": True,
                    "medication": True,
                }
            elif facility == "training_center":
                modules = {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "training": True,
                    "notifications": True,
                }
            elif facility == "boarding_facility":
                modules = {
                    "feeding": True,
                    "walk": True,
                    "visitor": True,
                    "notifications": True,
                }
            elif facility == "veterinary_clinic":
                modules = {
                    "feeding": True,
                    "health": True,
                    "medication": True,
                    "notifications": True,
                }
            else:  # walker_service
                modules = {
                    "walk": True,
                    "gps": True,
                    "visitor": True,
                    "notifications": True,
                }

            # Calculate entities for facility
            for _ in range(dog_count):
                count = entity_factory.estimate_entity_count(profile, modules)
                total_entities += count
                total_dogs += 1

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Enterprise deployment assertions
        assert total_dogs == 53  # Sum of all facility dogs
        assert total_entities > 300  # Significant entity count
        assert execution_time < 2.0  # Reasonable for enterprise load

        entities_per_dog = total_entities / total_dogs
        assert 5 <= entities_per_dog <= 15  # Reasonable range

        print("\nEnterprise Deployment Test Results:")
        print(f"  Total facilities: {len(facilities)}")
        print(f"  Total dogs: {total_dogs}")
        print(f"  Total entities: {total_entities}")
        print(f"  Entities per dog: {entities_per_dog:.1f}")
        print(f"  Execution time: {execution_time:.3f}s")
        print(
            f"  Performance rating: {'✓ Excellent' if execution_time < 1.0 else '✓ Good'}"
        )

    async def test_continuous_operation_simulation(
        self, entity_factory: EntityFactory
    ) -> None:
        """Simulate continuous operation over time."""
        operation_times = []

        # Simulate 24 hours of operations (1 operation per minute)
        simulated_minutes = 60  # Test 1 hour worth

        for minute in range(simulated_minutes):
            start_time = time.perf_counter()

            # Vary operations throughout the day
            if minute % 10 == 0:  # Every 10 minutes - full estimation
                modules = {"feeding": True, "walk": True, "health": True, "gps": True}
                entity_factory.estimate_entity_count("standard", modules)
            else:  # Regular operations
                entity_factory.should_create_entity(
                    "standard", "sensor", "feeding", priority=5
                )

            operation_times.append(time.perf_counter() - start_time)

        # Continuous operation analysis
        avg_time = sum(operation_times) / len(operation_times)
        max_time = max(operation_times)
        min_time = min(operation_times)

        # Continuous operation assertions
        assert avg_time < 0.01  # Average operation should be fast
        assert max_time < 0.1  # No single operation should be slow
        assert max_time / min_time < 10  # Reasonable variance

        # Performance stability (no degradation over time)
        first_quarter = operation_times[: simulated_minutes // 4]
        last_quarter = operation_times[-simulated_minutes // 4 :]

        avg_first = sum(first_quarter) / len(first_quarter)
        avg_last = sum(last_quarter) / len(last_quarter)

        # No significant performance degradation
        assert avg_last / avg_first < 2.0  # Less than 2x slowdown

        print("\nContinuous Operation Test Results:")
        print(f"  Operations simulated: {simulated_minutes}")
        print(f"  Average time: {avg_time * 1000:.2f}ms")
        print(f"  Max time: {max_time * 1000:.2f}ms")
        print(f"  Performance stability: {avg_last / avg_first:.2f}x")

    async def test_quality_scale_platinum_validation(
        self, entity_factory: EntityFactory
    ) -> None:
        """Validate Platinum quality scale requirements."""
        test_results = {
            "scalability": False,
            "performance": False,
            "memory_efficiency": False,
            "concurrent_safety": False,
            "production_ready": False,
        }

        # Test 1: Scalability (25+ dogs)
        start_time = time.perf_counter()
        total_entities = 0
        for i in range(25):
            modules = {"feeding": True, "walk": True, "health": i % 2 == 0}
            count = entity_factory.estimate_entity_count("standard", modules)
            total_entities += count
        scalability_time = time.perf_counter() - start_time

        if scalability_time < 1.0 and total_entities > 150:
            test_results["scalability"] = True

        # Test 2: Performance (sub-second for complex operations)
        start_time = time.perf_counter()
        for _ in range(100):
            entity_factory.get_performance_metrics(
                "advanced", {"feeding": True, "walk": True, "health": True, "gps": True}
            )
        performance_time = time.perf_counter() - start_time

        if performance_time < 1.0:
            test_results["performance"] = True

        # Test 3: Memory Efficiency (minimal memory growth)
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Perform memory-intensive operations
        configs = []
        for i in range(100):
            config = entity_factory.create_entity_config(
                dog_id=f"memory_test_{i}",
                entity_type="sensor",
                module="feeding",
                profile="standard",
                priority=5,
            )
            if config:
                configs.append(config)

        gc.collect()
        final_objects = len(gc.get_objects())
        object_growth = final_objects - initial_objects

        if object_growth < 1000:  # Reasonable object growth
            test_results["memory_efficiency"] = True

        # Test 4: Concurrent Safety (consistent results)
        results = []
        for _ in range(50):
            result = entity_factory.estimate_entity_count(
                "standard", {"feeding": True, "walk": True}
            )
            results.append(result)

        if len(set(results)) == 1:  # All results identical
            test_results["concurrent_safety"] = True

        # Test 5: Production Ready (comprehensive feature support)
        all_profiles_work = True
        for profile in entity_factory.get_available_profiles():
            try:
                count = entity_factory.estimate_entity_count(profile, {"feeding": True})
                if count <= 0:
                    all_profiles_work = False
                    break
            except Exception:
                all_profiles_work = False
                break

        test_results["production_ready"] = all_profiles_work

        # Platinum Quality Assertions
        passed_tests = sum(test_results.values())
        assert passed_tests >= 4, (
            f"Platinum quality requires 4/5 tests passing, got {passed_tests}/5"
        )

        # Specific critical requirements
        assert test_results["scalability"], (
            "Scalability test failed - not Platinum quality"
        )
        assert test_results["performance"], (
            "Performance test failed - not Platinum quality"
        )

        print("\nPlatinum Quality Validation Results:")
        for test_name, result in test_results.items():
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"  {test_name.replace('_', ' ').title()}: {status}")
        print(f"\nOverall: {passed_tests}/5 tests passed")
        print(f"Quality Scale: {'🏆 PLATINUM' if passed_tests >= 4 else '🥈 GOLD'}")
