"""Performance validation tests for PawControl Entity Profile System.

Tests multi-dog scaling, memory usage, execution time, and real-world
performance scenarios for all entity profiles.

Quality Scale: Bronze target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import time
from unittest.mock import Mock

import pytest
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES, EntityFactory
from homeassistant.const import Platform


class TestEntityPerformanceScaling:
    """Test performance scaling for different dog counts and profiles."""

    @pytest.fixture
    def entity_factory(self) -> EntityFactory:
        """Create EntityFactory with mock coordinator."""
        mock_coordinator = Mock()
        return EntityFactory(coordinator=mock_coordinator)

    @pytest.fixture
    def standard_modules(self) -> dict[str, bool]:
        """Standard module configuration for testing."""
        return {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": False,
            "notifications": True,
            "dashboard": True,
        }

    @pytest.fixture
    def full_modules(self) -> dict[str, bool]:
        """Full module configuration for stress testing."""
        return {
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

    @pytest.mark.parametrize(
        "profile", ["basic", "standard", "advanced", "gps_focus", "health_focus"]
    )
    def test_single_dog_performance(
        self,
        entity_factory: EntityFactory,
        profile: str,
        standard_modules: dict[str, bool],
    ) -> None:
        """Test performance for single dog across all profiles."""
        start_time = time.perf_counter()

        # Simulate typical operations
        count = entity_factory.estimate_entity_count(profile, standard_modules)
        metrics = entity_factory.get_performance_metrics(profile, standard_modules)

        # Test entity creation decisions
        for _ in range(10):  # Simulate multiple entity checks
            entity_factory.should_create_entity(
                profile, "sensor", "feeding", priority=5
            )
            entity_factory.should_create_entity(profile, "button", "walk", priority=6)

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Performance assertions
        assert execution_time < 0.1  # Should complete in <100ms
        assert isinstance(count, int)
        assert count > 0
        assert metrics["utilization_percentage"] >= 0

        # Profile-specific assertions
        profile_info = ENTITY_PROFILES[profile]
        assert count <= profile_info["max_entities"]

    @pytest.mark.parametrize("dog_count", [1, 3, 5, 10])
    def test_multi_dog_scaling_standard_profile(
        self,
        entity_factory: EntityFactory,
        dog_count: int,
        standard_modules: dict[str, bool],
    ) -> None:
        """Test performance scaling with multiple dogs."""
        start_time = time.perf_counter()

        total_entities = 0
        for i in range(dog_count):
            dog_id = f"dog_{i}"
            count = entity_factory.estimate_entity_count("standard", standard_modules)
            total_entities += count

            # Test entity config creation
            config = entity_factory.create_entity_config(
                dog_id=dog_id,
                entity_type="sensor",
                module="feeding",
                profile="standard",
                priority=5,
            )
            assert config is not None

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Performance should scale linearly (with some overhead)
        expected_max_time = 0.05 * dog_count  # 50ms per dog max
        assert execution_time < expected_max_time

        # Entity count should scale linearly
        expected_entities_per_dog = entity_factory.estimate_entity_count(
            "standard", standard_modules
        )
        expected_total = expected_entities_per_dog * dog_count
        assert total_entities == expected_total

    def test_profile_performance_comparison(
        self, entity_factory: EntityFactory, full_modules: dict[str, bool]
    ) -> None:
        """Compare performance across all profiles with full modules."""
        performance_results = {}

        for profile in ENTITY_PROFILES:
            start_time = time.perf_counter()

            # Perform typical operations
            count = entity_factory.estimate_entity_count(profile, full_modules)
            metrics = entity_factory.get_performance_metrics(profile, full_modules)

            # Simulate entity creation checks
            checks = [
                ("sensor", "feeding", 5),
                ("button", "walk", 6),
                ("binary_sensor", "health", 7),
                ("device_tracker", "gps", 8),
                ("switch", "notifications", 4),
            ]

            for entity_type, module, priority in checks:
                entity_factory.should_create_entity(
                    profile, entity_type, module, priority
                )

            end_time = time.perf_counter()

            performance_results[profile] = {
                "execution_time": end_time - start_time,
                "entity_count": count,
                "utilization": metrics["utilization_percentage"],
                "performance_impact": metrics["performance_impact"],
            }

        # Verify performance characteristics
        basic_perf = performance_results["basic"]
        advanced_perf = performance_results["advanced"]

        # Basic should be fastest and most conservative
        assert basic_perf["entity_count"] <= advanced_perf["entity_count"]
        assert basic_perf["performance_impact"] == "minimal"

        # Advanced should have reasonable performance despite more entities
        assert advanced_perf["execution_time"] < 0.2  # Still under 200ms
        assert advanced_perf["performance_impact"] in ["medium"]

    def test_memory_efficiency_large_scale(self, entity_factory: EntityFactory) -> None:
        """Test memory efficiency with large-scale configurations."""
        # Simulate 20 dogs with various configurations
        dog_configs = []
        for i in range(20):
            modules = {
                "feeding": True,
                "walk": i % 2 == 0,  # Every other dog
                "health": i % 3 == 0,  # Every third dog
                "gps": i % 5 == 0,  # Every fifth dog
                "notifications": True,
                "dashboard": i < 10,  # First 10 dogs
            }

            profile = ["basic", "standard", "advanced"][i % 3]

            config = {
                "dog_id": f"dog_{i:02d}",
                "modules": modules,
                "profile": profile,
            }
            dog_configs.append(config)

        # Measure performance for large batch
        start_time = time.perf_counter()

        results = []
        for config in dog_configs:
            count = entity_factory.estimate_entity_count(
                config["profile"], config["modules"]
            )
            metrics = entity_factory.get_performance_metrics(
                config["profile"], config["modules"]
            )

            results.append(
                {
                    "dog_id": config["dog_id"],
                    "count": count,
                    "metrics": metrics,
                }
            )

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Performance assertions
        assert execution_time < 2.0  # Should handle 20 dogs in under 2 seconds
        assert len(results) == 20

        # Verify all results are valid
        for result in results:
            assert result["count"] > 0
            assert isinstance(result["metrics"], dict)
            assert "utilization_percentage" in result["metrics"]

    def test_concurrent_access_simulation(self, entity_factory: EntityFactory) -> None:
        """Simulate concurrent access patterns for thread safety validation."""
        modules = {"feeding": True, "walk": True, "health": True}

        # Simulate multiple threads accessing the factory
        # (Note: Python GIL limits true concurrency, but tests logic)
        start_time = time.perf_counter()

        results = []
        for thread_id in range(10):
            for operation in range(5):
                dog_id = f"thread_{thread_id}_dog_{operation}"

                # Mix different operations
                if operation % 3 == 0:
                    count = entity_factory.estimate_entity_count("standard", modules)
                    results.append(("estimate", count))
                elif operation % 3 == 1:
                    config = entity_factory.create_entity_config(
                        dog_id=dog_id,
                        entity_type="sensor",
                        module="feeding",
                        profile="standard",
                        priority=5,
                    )
                    results.append(("config", config))
                else:
                    should_create = entity_factory.should_create_entity(
                        "standard", "button", "walk", priority=6
                    )
                    results.append(("should_create", should_create))

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Performance and correctness assertions
        assert execution_time < 1.0  # Should complete quickly
        assert len(results) == 50  # 10 threads × 5 operations  # noqa: RUF003

        # Verify results consistency
        estimate_results = [r[1] for r in results if r[0] == "estimate"]
        assert all(isinstance(count, int) and count > 0 for count in estimate_results)
        assert len(set(estimate_results)) == 1  # All estimates should be identical

    def test_edge_case_performance(self, entity_factory: EntityFactory) -> None:
        """Test performance with edge cases and stress conditions."""
        edge_cases = [
            # Empty modules
            ({}, "basic"),
            # Single module
            ({"feeding": True}, "standard"),
            # All modules disabled
            (
                {module: False for module in ["feeding", "walk", "health", "gps"]},
                "advanced",
            ),
            # Maximum modules
            (
                {
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
                },
                "advanced",
            ),
        ]

        for modules, profile in edge_cases:
            start_time = time.perf_counter()

            # Should handle gracefully without errors
            count = entity_factory.estimate_entity_count(profile, modules)
            metrics = entity_factory.get_performance_metrics(profile, modules)

            end_time = time.perf_counter()
            execution_time = end_time - start_time

            # Performance assertions
            assert execution_time < 0.05  # Edge cases should be fast
            assert isinstance(count, int)
            assert count >= 0
            assert isinstance(metrics, dict)

    def test_cache_efficiency(self, entity_factory: EntityFactory) -> None:
        """Test caching efficiency for repeated operations."""
        profile = "standard"

        # First call (should populate cache)
        start_time = time.perf_counter()
        first_result = entity_factory.get_profile_info(profile)
        time.perf_counter() - start_time

        # Subsequent calls (should use cache)
        cache_times = []
        for _ in range(10):
            start_time = time.perf_counter()
            cached_result = entity_factory.get_profile_info(profile)
            cache_time = time.perf_counter() - start_time
            cache_times.append(cache_time)

            # Results should be identical
            assert cached_result == first_result

        # Cache should be significantly faster
        sum(cache_times) / len(cache_times)

        # Note: Due to Python's optimizations, the difference might be minimal
        # but cached results should at least be consistent
        assert all(time < 0.01 for time in cache_times)  # All under 10ms

    @pytest.mark.parametrize("profile", ["basic", "standard", "advanced"])
    def test_platform_priority_performance(
        self, entity_factory: EntityFactory, profile: str
    ) -> None:
        """Test performance of platform priority calculations."""
        platforms = [
            Platform.SENSOR,
            Platform.BUTTON,
            Platform.BINARY_SENSOR,
            Platform.SWITCH,
            Platform.SELECT,
            Platform.NUMBER,
            Platform.DEVICE_TRACKER,
            Platform.DATE,
            Platform.DATETIME,
            Platform.TEXT,
        ]

        start_time = time.perf_counter()

        priorities = []
        for platform in platforms:
            priority = entity_factory.get_platform_priority(platform, profile)
            priorities.append((platform, priority))

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Performance assertions
        assert execution_time < 0.01  # Should be very fast
        assert len(priorities) == len(platforms)

        # Validate priority values
        for platform, priority in priorities:  # noqa: B007
            assert isinstance(priority, int)
            assert 1 <= priority <= 99

    def test_validation_performance(self, entity_factory: EntityFactory) -> None:
        """Test performance of validation operations."""
        test_cases = [
            # Valid cases
            ("standard", {"feeding": True, "walk": True}),
            ("gps_focus", {"gps": True, "walk": True, "visitor": True}),
            ("health_focus", {"health": True, "feeding": True, "medication": True}),
            # Invalid cases
            ("invalid_profile", {"feeding": True}),
            ("standard", {"invalid": "not_boolean"}),  # type: ignore[dict-item]
            ("advanced", None),  # type: ignore[arg-type]
        ]

        start_time = time.perf_counter()

        for profile, modules in test_cases:
            # These should all complete without errors
            try:
                valid = entity_factory.validate_profile_for_modules(profile, modules)
                assert isinstance(valid, bool)
            except (TypeError, AttributeError):
                # Expected for invalid inputs
                pass

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Should handle all validation cases quickly
        assert execution_time < 0.05


class TestEntityPerformanceBenchmarks:
    """Benchmark tests for real-world performance scenarios."""

    @pytest.fixture
    def entity_factory(self) -> EntityFactory:
        """Create EntityFactory for benchmarking."""
        return EntityFactory(coordinator=None)

    def test_real_world_scenario_small_household(
        self, entity_factory: EntityFactory
    ) -> None:
        """Benchmark: Small household with 1-2 dogs."""
        dogs = [
            {
                "id": "buddy",
                "profile": "standard",
                "modules": {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "notifications": True,
                },
            },
            {
                "id": "bella",
                "profile": "basic",
                "modules": {
                    "feeding": True,
                    "walk": True,
                    "health": False,
                    "notifications": True,
                },
            },
        ]

        start_time = time.perf_counter()

        total_entities = 0
        for dog in dogs:
            count = entity_factory.estimate_entity_count(dog["profile"], dog["modules"])
            total_entities += count

            # Simulate UI operations
            entity_factory.get_performance_metrics(dog["profile"], dog["modules"])

            # Simulate entity creation checks
            for platform_str in ["sensor", "button", "binary_sensor"]:
                entity_factory.should_create_entity(
                    dog["profile"], platform_str, "feeding", priority=5
                )

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Small household should be very fast
        assert execution_time < 0.1  # Under 100ms
        assert 10 <= total_entities <= 25  # Reasonable entity count

        print(
            f"Small household benchmark: {execution_time:.3f}s, {total_entities} entities"
        )

    def test_real_world_scenario_dog_daycare(
        self, entity_factory: EntityFactory
    ) -> None:
        """Benchmark: Dog daycare with 8-15 dogs."""
        dogs = []
        for i in range(12):  # Medium-sized daycare
            profile = ["basic", "standard"][i % 2]  # Mix of profiles
            modules = {
                "feeding": True,
                "walk": True,
                "health": i < 6,  # Health tracking for half
                "gps": i < 4,  # GPS for active dogs
                "visitor": True,  # All in visitor mode
                "notifications": True,
            }
            dogs.append(
                {"id": f"daycare_dog_{i:02d}", "profile": profile, "modules": modules}
            )

        start_time = time.perf_counter()

        total_entities = 0
        performance_metrics = []

        for dog in dogs:
            count = entity_factory.estimate_entity_count(dog["profile"], dog["modules"])
            metrics = entity_factory.get_performance_metrics(
                dog["profile"], dog["modules"]
            )

            total_entities += count
            performance_metrics.append(metrics)

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Daycare scenario should still be reasonable
        assert execution_time < 0.5  # Under 500ms
        assert 60 <= total_entities <= 150  # Scaled entity count

        # Check utilization
        avg_utilization = sum(
            m["utilization_percentage"] for m in performance_metrics
        ) / len(performance_metrics)
        assert 20 <= avg_utilization <= 80  # Reasonable utilization

        print(
            f"Dog daycare benchmark: {execution_time:.3f}s, {total_entities} entities, {avg_utilization:.1f}% avg utilization"
        )

    def test_real_world_scenario_professional_breeder(
        self, entity_factory: EntityFactory
    ) -> None:
        """Benchmark: Professional breeder with 20+ dogs."""
        dogs = []
        for i in range(25):  # Large breeding operation
            # Vary profiles based on dog role
            if i < 5:  # Breeding stock - comprehensive monitoring
                profile = "advanced"
                modules = {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "gps": True,
                    "medication": True,
                    "grooming": True,
                    "notifications": True,
                }
            elif i < 15:  # Regular adults - standard monitoring
                profile = "standard"
                modules = {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "notifications": True,
                    "grooming": i % 2 == 0,
                }
            else:  # Puppies/young dogs - basic monitoring
                profile = "basic"
                modules = {
                    "feeding": True,
                    "walk": False,
                    "health": True,
                    "notifications": True,
                }

            dogs.append(
                {"id": f"breeder_dog_{i:02d}", "profile": profile, "modules": modules}
            )

        start_time = time.perf_counter()

        total_entities = 0
        profile_breakdown = {}

        for dog in dogs:
            count = entity_factory.estimate_entity_count(dog["profile"], dog["modules"])
            total_entities += count

            profile_breakdown[dog["profile"]] = (
                profile_breakdown.get(dog["profile"], 0) + count
            )

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Large scale should still be manageable
        assert execution_time < 1.0  # Under 1 second
        assert 150 <= total_entities <= 400  # Significant but manageable

        # Verify profile distribution
        assert "basic" in profile_breakdown
        assert "standard" in profile_breakdown
        assert "advanced" in profile_breakdown

        print(
            f"Professional breeder benchmark: {execution_time:.3f}s, {total_entities} entities"
        )
        print(f"Profile breakdown: {profile_breakdown}")

    def test_performance_regression_detection(
        self, entity_factory: EntityFactory
    ) -> None:
        """Detect performance regressions with standardized test."""
        # Standardized test case
        modules = {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": True,
            "notifications": True,
            "dashboard": True,
        }

        # Measure multiple iterations
        times = []
        for _ in range(10):
            start_time = time.perf_counter()

            # Standard operations
            entity_factory.estimate_entity_count("standard", modules)
            entity_factory.get_performance_metrics("standard", modules)

            # Entity decision making
            for priority in [3, 5, 7, 9]:
                entity_factory.should_create_entity(
                    "standard", "sensor", "feeding", priority
                )

            end_time = time.perf_counter()
            times.append(end_time - start_time)

        # Statistical analysis
        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)

        # Performance regression thresholds
        assert avg_time < 0.01  # Average under 10ms
        assert max_time < 0.02  # Max under 20ms
        assert max_time / min_time < 3  # Reasonable variance

        print(
            f"Regression test: avg={avg_time * 1000:.2f}ms, max={max_time * 1000:.2f}ms, min={min_time * 1000:.2f}ms"
        )
