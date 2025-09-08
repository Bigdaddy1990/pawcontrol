"""Comprehensive stress tests for PawControl PerformanceMonitor.

Tests performance characteristics under extreme load scenarios including
50+ dogs, 500+ entities, memory management, concurrent access patterns,
and long-running performance degradation scenarios.

Test Areas:
- High-load scenarios (50+ dogs, 500+ entities)
- Memory usage and cleanup under stress
- Percentile calculation performance with large datasets
- Cache behavior under heavy load and invalidation
- Alert throttling and rate limiting effectiveness
- Trend analysis accuracy with extensive data
- Health scoring under various load conditions
- Concurrent access and thread safety
- Data structure limits and boundary conditions
- Performance degradation pattern detection
"""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from custom_components.pawcontrol.performance_manager import (
    HISTORY_SIZE,
    PerformanceMonitor,
)
from homeassistant.util import dt as dt_util


class TestHighLoadScenarios:
    """Test performance monitor under high load scenarios."""

    def test_50_dogs_scenario_performance(self):
        """Test performance monitoring with 50 dogs scenario."""
        monitor = PerformanceMonitor()

        # Simulate 50 dogs with varying performance characteristics
        dogs_count = 50
        entities_per_dog = 12  # Average entities per dog
        total_entities = dogs_count * entities_per_dog  # 600 entities

        # Simulate update cycles for 50 dogs
        update_cycles = 100
        start_time = time.time()

        for cycle in range(update_cycles):
            # Simulate update time based on entity count (realistic scaling)
            base_time = 0.1  # 100ms base
            entity_overhead = total_entities * 0.002  # 2ms per entity
            random_variation = random.uniform(0.8, 1.5)  # ±50% variation

            update_duration = (base_time + entity_overhead) * random_variation
            error_count = 1 if random.random() < 0.05 else 0  # 5% error rate

            monitor.record_update(update_duration, error_count)

        performance_time = time.time() - start_time

        # Verify performance characteristics
        stats = monitor.get_stats()

        assert stats["total_updates"] == update_cycles
        assert "average_update_time" in stats
        assert "p95" in stats

        # Performance should complete quickly even with 50 dogs
        assert performance_time < 1.0  # Less than 1 second

        # Average update time should scale reasonably
        assert stats["average_update_time"] < 5.0  # Should be under 5 seconds

        # Error rate should be within expected range
        assert 0 <= stats["error_rate"] <= 10  # Up to 10% due to randomness

    def test_500_entities_load_simulation(self):
        """Test with extreme 500+ entities load."""
        monitor = PerformanceMonitor(alert_threshold=2.0)  # Lower threshold for testing

        # Simulate extreme load: 50 dogs * 10 entities each = 500 entities
        entity_count = 500
        update_cycles = 50

        for cycle in range(update_cycles):
            # Simulate realistic scaling: O(n) with some overhead
            base_time = 0.05  # 50ms base
            linear_scaling = entity_count * 0.003  # 3ms per entity
            overhead = entity_count * 0.0001  # Small overhead factor

            # Add realistic variance and occasional spikes
            if random.random() < 0.1:  # 10% chance of spike
                spike_factor = random.uniform(2.0, 5.0)
            else:
                spike_factor = random.uniform(0.8, 1.2)

            update_duration = (base_time + linear_scaling + overhead) * spike_factor

            # More errors under heavy load
            error_count = random.randint(0, 3) if random.random() < 0.15 else 0

            monitor.record_update(update_duration, error_count)

        stats = monitor.get_stats()

        # Verify system handles extreme load
        assert stats["total_updates"] == update_cycles
        assert stats["max_update_time"] > 0

        # Performance metrics should be reasonable
        assert stats["average_update_time"] < 10.0  # Should complete within 10s
        assert stats["p99"] < 20.0  # 99th percentile under 20s

        # Should detect slow updates
        assert stats["slow_updates"] >= 0

    def test_memory_usage_large_dataset(self):
        """Test memory usage with large dataset."""
        monitor = PerformanceMonitor()

        # Fill history to maximum capacity
        large_dataset_size = HISTORY_SIZE * 2  # Exceed capacity

        memory_baseline = self._get_monitor_memory_usage(monitor)

        # Add many measurements
        for i in range(large_dataset_size):
            update_time = random.uniform(0.1, 10.0)
            error_count = random.randint(0, 5)
            monitor.record_update(update_time, error_count)

        memory_after = self._get_monitor_memory_usage(monitor)

        # Verify deque limits are respected (memory doesn't grow unbounded)
        assert len(monitor._update_times) == HISTORY_SIZE
        assert len(monitor._error_counts) == HISTORY_SIZE

        # Memory should not grow excessively
        memory_growth = memory_after - memory_baseline
        assert memory_growth < 1000  # Less than 1KB growth (reasonable for deque)

        # Verify data integrity
        stats = monitor.get_stats()
        assert stats["total_updates"] == HISTORY_SIZE  # Only last HISTORY_SIZE kept

    def test_percentile_calculation_performance(self):
        """Test percentile calculation performance with large datasets."""
        monitor = PerformanceMonitor()

        # Fill with large dataset
        for i in range(HISTORY_SIZE):
            # Create realistic distribution
            if i < HISTORY_SIZE * 0.8:  # 80% normal updates
                update_time = random.uniform(0.1, 2.0)
            elif i < HISTORY_SIZE * 0.95:  # 15% slow updates
                update_time = random.uniform(2.0, 5.0)
            else:  # 5% very slow updates
                update_time = random.uniform(5.0, 15.0)

            monitor.record_update(update_time)

        # Test percentile calculation performance
        start_time = time.time()

        percentiles = []
        for _ in range(100):  # Multiple calculations to test caching
            p50 = monitor._get_percentile(50)
            p95 = monitor._get_percentile(95)
            p99 = monitor._get_percentile(99)
            percentiles.extend([p50, p95, p99])

        calculation_time = time.time() - start_time

        # Should be fast due to caching
        assert calculation_time < 0.1  # Under 100ms for 300 calculations

        # Verify percentiles make sense
        assert (
            percentiles[-3] <= percentiles[-2] <= percentiles[-1]
        )  # p50 <= p95 <= p99

    def test_cache_invalidation_under_load(self):
        """Test cache behavior under high invalidation load."""
        monitor = PerformanceMonitor()

        # Fill initial data
        for i in range(50):
            monitor.record_update(random.uniform(0.5, 2.0))

        # Rapid updates that invalidate cache frequently
        cache_hit_count = 0
        cache_miss_count = 0

        for cycle in range(100):
            # Force cache miss by recording new data
            monitor.record_update(random.uniform(0.1, 5.0))

            # Multiple reads (should hit cache after first)
            for _ in range(5):
                start_time = time.time()
                p95 = monitor._get_percentile(95)
                calc_time = time.time() - start_time

                if calc_time < 0.001:  # Very fast = cache hit
                    cache_hit_count += 1
                else:  # Slower = cache miss
                    cache_miss_count += 1

                assert p95 > 0  # Valid percentile

        # Should have reasonable cache hit ratio
        total_ops = cache_hit_count + cache_miss_count
        cache_hit_ratio = cache_hit_count / total_ops if total_ops > 0 else 0

        # With 5 reads per cycle, should get ~80% cache hits
        assert cache_hit_ratio > 0.5  # At least 50% cache hits

    def _get_monitor_memory_usage(self, monitor: PerformanceMonitor) -> int:
        """Estimate memory usage of monitor (simplified)."""
        # Simplified memory estimation
        update_times_size = len(monitor._update_times) * 8  # float64
        error_counts_size = len(monitor._error_counts) * 4  # int32
        cache_size = len(monitor._percentile_cache) * 16  # key + value

        return update_times_size + error_counts_size + cache_size


class TestAlertingUnderStress:
    """Test alerting system under stress conditions."""

    def test_alert_throttling_effectiveness(self):
        """Test alert throttling under heavy slow update load."""
        with patch(
            "custom_components.pawcontrol.performance_manager._LOGGER"
        ) as mock_logger:
            monitor = PerformanceMonitor(alert_threshold=1.0)

            # Generate many slow updates in short time
            slow_updates = 50
            for i in range(slow_updates):
                # All updates are slow (above threshold)
                update_time = random.uniform(2.0, 10.0)
                monitor.record_update(update_time)

            # Count warning log calls (alerts)
            warning_calls = [call for call in mock_logger.warning.call_args_list]

            # Should throttle alerts (not 50 alerts)
            assert len(warning_calls) <= 5  # Maximum reasonable alert count

            # Verify throttling logic
            stats = monitor.get_stats()
            assert stats["slow_updates"] == slow_updates  # All recorded

            # But alerts should be limited
            if warning_calls:
                # Check alert content includes performance context
                last_alert = str(warning_calls[-1])
                assert "p95=" in last_alert
                assert "threshold=" in last_alert

    def test_alert_rate_limiting_timing(self):
        """Test alert rate limiting timing accuracy."""
        with patch(
            "custom_components.pawcontrol.performance_manager._LOGGER"
        ) as mock_logger:
            with patch(
                "custom_components.pawcontrol.performance_manager.dt_util"
            ) as mock_dt:
                # Control time progression
                base_time = datetime(2025, 1, 1, 12, 0, 0)
                time_progression = [
                    base_time,
                    base_time + timedelta(minutes=5),  # 5 min later
                    base_time
                    + timedelta(minutes=11),  # 11 min later (should allow new alert)
                ]
                mock_dt.utcnow.side_effect = time_progression

                monitor = PerformanceMonitor(alert_threshold=1.0)

                # First slow update - should alert
                monitor.record_update(5.0)

                # Second slow update within 10 min - should not alert
                monitor.record_update(6.0)

                # Third slow update after 10 min - should alert again
                monitor.record_update(7.0)

                # Should have exactly 2 alerts
                warning_calls = mock_logger.warning.call_args_list
                assert len(warning_calls) == 2

    def test_alert_content_accuracy(self):
        """Test alert content accuracy under various conditions."""
        with patch(
            "custom_components.pawcontrol.performance_manager._LOGGER"
        ) as mock_logger:
            monitor = PerformanceMonitor(alert_threshold=2.0)

            # Build performance history
            for i in range(20):
                monitor.record_update(random.uniform(0.5, 1.8))  # Normal updates

            # Trigger alert with slow update
            monitor.record_update(5.0)

            # Verify alert content
            warning_calls = mock_logger.warning.call_args_list
            if warning_calls:
                alert_message = str(warning_calls[-1])

                # Should contain key metrics
                assert "5.00s" in alert_message  # Current duration
                assert "p95=" in alert_message  # Percentile context
                assert "threshold=2.0" in alert_message  # Threshold
                assert "Slow updates:" in alert_message  # Count info


class TestTrendAnalysisStress:
    """Test trend analysis under various stress conditions."""

    def test_trend_analysis_large_dataset(self):
        """Test trend analysis with large dataset."""
        monitor = PerformanceMonitor()

        # Create clear performance degradation pattern
        for i in range(HISTORY_SIZE):
            # Gradual performance degradation
            base_time = 0.5
            degradation_factor = 1 + (i / HISTORY_SIZE) * 2  # Up to 3x slower
            noise = random.uniform(0.9, 1.1)  # ±10% noise

            update_time = base_time * degradation_factor * noise
            monitor.record_update(update_time)

        trend = monitor.analyze_performance_trend()

        # Should detect degradation
        assert trend["trend_direction"] == "degrading"
        assert trend["trend_percentage"] > 10  # Significant degradation
        assert trend["analysis_confidence"] == "high"  # Full dataset

        # Verify trend magnitude makes sense
        assert trend["second_half_avg"] > trend["first_half_avg"]

    def test_trend_analysis_volatile_performance(self):
        """Test trend analysis with highly volatile performance."""
        monitor = PerformanceMonitor()

        # Create volatile but stable average performance
        for i in range(HISTORY_SIZE):
            if i % 2 == 0:
                update_time = random.uniform(0.1, 0.5)  # Fast
            else:
                update_time = random.uniform(2.0, 5.0)  # Slow

            monitor.record_update(update_time)

        trend = monitor.analyze_performance_trend()

        # Should handle volatility gracefully
        assert trend["trend_direction"] in ["stable", "improving", "degrading"]
        assert isinstance(trend["trend_percentage"], (int, float))
        assert trend["analysis_confidence"] == "high"

    def test_trend_analysis_insufficient_data(self):
        """Test trend analysis with insufficient data."""
        monitor = PerformanceMonitor()

        # Add only a few data points
        for i in range(5):
            monitor.record_update(random.uniform(0.5, 2.0))

        trend = monitor.analyze_performance_trend()

        # Should indicate insufficient data
        assert trend["insufficient_data"] is True
        assert trend["minimum_required"] == 10

    def test_trend_analysis_edge_cases(self):
        """Test trend analysis edge cases."""
        monitor = PerformanceMonitor()

        # Edge case: All identical performance
        for i in range(50):
            monitor.record_update(1.0)  # Exactly 1 second every time

        trend = monitor.analyze_performance_trend()

        assert trend["trend_direction"] == "stable"
        assert trend["trend_percentage"] == 0.0
        assert trend["first_half_avg"] == trend["second_half_avg"]


class TestHealthScoringStress:
    """Test health scoring under various stress conditions."""

    def test_health_scoring_perfect_performance(self):
        """Test health scoring with perfect performance."""
        monitor = PerformanceMonitor(alert_threshold=5.0)

        # Perfect performance: fast, consistent, no errors
        for i in range(100):
            update_time = random.uniform(0.8, 1.2)  # Very consistent
            monitor.record_update(update_time, error_count=0)

        health = monitor.get_performance_health_score()

        assert health["overall_score"] >= 90  # Should be excellent
        assert health["health_level"] == "excellent"
        assert health["component_scores"]["speed"] >= 90
        assert health["component_scores"]["reliability"] == 100  # No errors
        assert health["component_scores"]["consistency"] >= 90

    def test_health_scoring_poor_performance(self):
        """Test health scoring with poor performance."""
        monitor = PerformanceMonitor(alert_threshold=1.0)

        # Poor performance: slow, inconsistent, many errors
        for i in range(100):
            if i % 3 == 0:  # Very slow updates
                update_time = random.uniform(5.0, 15.0)
                error_count = random.randint(2, 5)
            elif i % 3 == 1:  # Moderate updates
                update_time = random.uniform(2.0, 4.0)
                error_count = random.randint(0, 2)
            else:  # Occasional fast updates
                update_time = random.uniform(0.5, 1.5)
                error_count = 0

            monitor.record_update(update_time, error_count)

        health = monitor.get_performance_health_score()

        assert health["overall_score"] < 75  # Should be poor/fair
        assert health["health_level"] in ["poor", "fair"]
        assert len(health["recommendations"]) > 0  # Should have recommendations

    def test_health_scoring_edge_cases(self):
        """Test health scoring edge cases."""
        monitor = PerformanceMonitor()

        # No data
        health = monitor.get_performance_health_score()
        assert health["no_data"] is True

        # Single data point
        monitor.record_update(1.0)
        health = monitor.get_performance_health_score()
        assert "overall_score" in health

        # Extreme values
        monitor = PerformanceMonitor(alert_threshold=1.0)
        monitor.record_update(100.0, error_count=50)  # Extremely bad
        health = monitor.get_performance_health_score()
        assert health["overall_score"] >= 0  # Should not go negative

    def test_health_recommendations_accuracy(self):
        """Test health recommendation accuracy."""
        monitor = PerformanceMonitor(alert_threshold=2.0)

        # Specific performance issues
        test_scenarios = [
            # Slow but reliable
            {"updates": [(5.0, 0)] * 50, "should_recommend": "optimizing"},
            # Fast but unreliable
            {"updates": [(0.5, 3)] * 50, "should_recommend": "reliability"},
            # Inconsistent performance
            {
                "updates": [(0.1, 0)] * 25 + [(10.0, 0)] * 25,
                "should_recommend": "variance",
            },
        ]

        for scenario in test_scenarios:
            monitor.reset_stats()

            for update_time, error_count in scenario["updates"]:
                monitor.record_update(update_time, error_count)

            health = monitor.get_performance_health_score()
            recommendations = " ".join(health["recommendations"]).lower()

            if scenario["should_recommend"] == "optimizing":
                assert (
                    "optimizing" in recommendations or "algorithms" in recommendations
                )
            elif scenario["should_recommend"] == "reliability":
                assert "reliability" in recommendations or "error" in recommendations
            elif scenario["should_recommend"] == "variance":
                assert "variance" in recommendations or "resource" in recommendations


class TestConcurrencyStress:
    """Test concurrent access patterns and thread safety."""

    def test_concurrent_record_update(self):
        """Test concurrent record_update calls."""
        monitor = PerformanceMonitor()

        def record_updates(thread_id: int, count: int):
            """Record updates from a specific thread."""
            for i in range(count):
                update_time = random.uniform(0.1, 2.0) + thread_id * 0.1
                error_count = random.randint(0, 2)
                monitor.record_update(update_time, error_count)

        # Run concurrent threads
        threads = []
        thread_count = 10
        updates_per_thread = 50

        for thread_id in range(thread_count):
            thread = threading.Thread(
                target=record_updates, args=(thread_id, updates_per_thread)
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5.0)  # 5 second timeout

        # Verify data integrity
        stats = monitor.get_stats()
        expected_total = min(thread_count * updates_per_thread, HISTORY_SIZE)
        assert stats["total_updates"] == expected_total

        # Verify no corruption
        assert stats["average_update_time"] > 0
        assert stats["max_update_time"] >= stats["min_update_time"]

    def test_concurrent_stats_access(self):
        """Test concurrent statistics access."""
        monitor = PerformanceMonitor()

        # Pre-populate data
        for i in range(100):
            monitor.record_update(random.uniform(0.1, 3.0), random.randint(0, 2))

        stats_results = []

        def get_stats_repeatedly():
            """Get stats repeatedly from different threads."""
            for _ in range(20):
                try:
                    stats = monitor.get_stats()
                    stats_results.append(stats)
                    time.sleep(0.001)  # Small delay
                except Exception as e:
                    stats_results.append(f"Error: {e}")

        # Run concurrent stats access
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=get_stats_repeatedly)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=5.0)

        # Verify no errors and consistent results
        error_results = [r for r in stats_results if isinstance(r, str)]
        assert len(error_results) == 0  # No errors

        valid_results = [r for r in stats_results if isinstance(r, dict)]
        assert len(valid_results) > 0

        # All results should have consistent total_updates
        update_counts = [r["total_updates"] for r in valid_results]
        assert len(set(update_counts)) <= 2  # Should be very consistent

    def test_concurrent_percentile_calculation(self):
        """Test concurrent percentile calculation performance."""
        monitor = PerformanceMonitor()

        # Fill with data
        for i in range(HISTORY_SIZE):
            monitor.record_update(random.uniform(0.1, 5.0))

        percentile_results = []

        def calculate_percentiles():
            """Calculate percentiles concurrently."""
            for _ in range(50):
                try:
                    p50 = monitor._get_percentile(50)
                    p95 = monitor._get_percentile(95)
                    p99 = monitor._get_percentile(99)
                    percentile_results.append((p50, p95, p99))
                except Exception as e:
                    percentile_results.append(f"Error: {e}")

        # Run concurrent percentile calculations
        threads = []
        for _ in range(4):
            thread = threading.Thread(target=calculate_percentiles)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=5.0)

        # Verify cache effectiveness and correctness
        error_results = [r for r in percentile_results if isinstance(r, str)]
        assert len(error_results) == 0

        valid_results = [r for r in percentile_results if isinstance(r, tuple)]
        assert len(valid_results) > 0

        # All results should be identical (cached)
        unique_results = set(valid_results)
        assert len(unique_results) <= 2  # Very few unique results due to caching


class TestDataStructureLimits:
    """Test data structure limits and boundary conditions."""

    def test_deque_maximum_capacity(self):
        """Test deque behavior at maximum capacity."""
        monitor = PerformanceMonitor()

        # Fill beyond capacity
        excess_data = HISTORY_SIZE + 50

        # Track first and last values
        first_values = []
        for i in range(10):
            update_time = float(i)
            monitor.record_update(update_time, i)
            first_values.append(update_time)

        # Fill to capacity and beyond
        for i in range(10, excess_data):
            monitor.record_update(float(i), i)

        # Verify deque limits
        assert len(monitor._update_times) == HISTORY_SIZE
        assert len(monitor._error_counts) == HISTORY_SIZE

        # First values should be evicted
        current_times = list(monitor._update_times)
        for first_value in first_values:
            assert first_value not in current_times

        # Last values should be preserved
        last_values = list(range(excess_data - HISTORY_SIZE, excess_data))
        for last_value in last_values:
            assert float(last_value) in current_times

    def test_extreme_values_handling(self):
        """Test handling of extreme values."""
        monitor = PerformanceMonitor()

        extreme_cases = [
            (0.0, 0),  # Minimum values
            (1e-6, 0),  # Very small positive
            (1e6, 1000),  # Very large values
            (float("inf"), 0),  # Infinity (should handle gracefully)
        ]

        for update_time, error_count in extreme_cases:
            try:
                monitor.record_update(update_time, error_count)
            except Exception:
                # Some extreme values might be rejected, which is acceptable
                pass

        # Should handle normal operations after extreme values
        monitor.record_update(1.0, 0)
        stats = monitor.get_stats()

        assert isinstance(stats, dict)
        assert "average_update_time" in stats

    def test_memory_cleanup_effectiveness(self):
        """Test memory cleanup and garbage collection effectiveness."""
        import gc

        # Create multiple monitors to test cleanup
        monitors = []
        for i in range(10):
            monitor = PerformanceMonitor()

            # Fill each monitor
            for j in range(HISTORY_SIZE):
                monitor.record_update(random.uniform(0.1, 2.0))

            monitors.append(monitor)

        # Get memory baseline
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Clear references and force cleanup
        monitors.clear()
        gc.collect()

        final_objects = len(gc.get_objects())

        # Memory should be cleaned up effectively
        # (Exact numbers may vary, but significant cleanup should occur)
        assert final_objects <= initial_objects + 100

    def test_percentile_cache_limits(self):
        """Test percentile cache memory limits."""
        monitor = PerformanceMonitor()

        # Fill with data
        for i in range(50):
            monitor.record_update(random.uniform(0.1, 2.0))

        # Generate many different percentile requests
        percentiles_requested = []
        for percentile in range(1, 100):  # 99 different percentiles
            result = monitor._get_percentile(percentile)
            percentiles_requested.append(result)

        # Cache should not grow unbounded
        cache_size = len(monitor._percentile_cache)
        assert cache_size <= 99  # One entry per percentile requested

        # Verify cache TTL cleanup
        original_cache_size = len(monitor._percentile_cache)

        # Simulate time passage (mock future time)
        with patch(
            "custom_components.pawcontrol.performance_manager.dt_util"
        ) as mock_dt:
            future_time = dt_util.utcnow() + timedelta(minutes=5)
            mock_dt.utcnow.return_value = future_time

            # Request new percentile (should clean cache due to TTL)
            monitor._get_percentile(50)

            # Cache should have been cleaned and rebuilt
            new_cache_size = len(monitor._percentile_cache)
            assert new_cache_size <= original_cache_size


class TestPerformanceDegradationPatterns:
    """Test detection of various performance degradation patterns."""

    def test_gradual_degradation_detection(self):
        """Test detection of gradual performance degradation."""
        monitor = PerformanceMonitor()

        # Simulate gradual degradation over time
        for i in range(HISTORY_SIZE):
            # Linear degradation: 0.5s to 5.0s over full history
            base_time = 0.5
            degradation = (i / HISTORY_SIZE) * 4.5  # 0 to 4.5s additional
            noise = random.uniform(0.9, 1.1)

            update_time = (base_time + degradation) * noise
            monitor.record_update(update_time)

        # Analyze degradation
        trend = monitor.analyze_performance_trend()
        health = monitor.get_performance_health_score()

        # Should detect degradation
        assert trend["trend_direction"] == "degrading"
        assert trend["trend_percentage"] > 50  # Significant degradation
        assert health["overall_score"] < 75  # Poor health

        # Should recommend optimization
        recommendations = " ".join(health["recommendations"]).lower()
        assert "optimizing" in recommendations or "algorithms" in recommendations

    def test_sudden_performance_drop(self):
        """Test detection of sudden performance drops."""
        monitor = PerformanceMonitor()

        # Good performance for first half
        half_point = HISTORY_SIZE // 2
        for i in range(half_point):
            update_time = random.uniform(0.3, 0.7)  # Fast and consistent
            monitor.record_update(update_time, 0)

        # Sudden drop in second half
        for i in range(half_point, HISTORY_SIZE):
            update_time = random.uniform(5.0, 8.0)  # Much slower
            error_count = random.randint(1, 3)  # More errors
            monitor.record_update(update_time, error_count)

        trend = monitor.analyze_performance_trend()
        health = monitor.get_performance_health_score()

        # Should detect severe degradation
        assert trend["trend_direction"] == "degrading"
        assert trend["trend_percentage"] > 100  # Very large change
        assert health["overall_score"] < 50  # Poor health
        assert health["health_level"] in ["poor", "fair"]

    def test_performance_recovery_detection(self):
        """Test detection of performance recovery."""
        monitor = PerformanceMonitor()

        # Poor performance for first half
        half_point = HISTORY_SIZE // 2
        for i in range(half_point):
            update_time = random.uniform(5.0, 8.0)  # Slow
            error_count = random.randint(1, 3)
            monitor.record_update(update_time, error_count)

        # Recovery in second half
        for i in range(half_point, HISTORY_SIZE):
            update_time = random.uniform(0.5, 1.0)  # Much better
            monitor.record_update(update_time, 0)

        trend = monitor.analyze_performance_trend()

        # Should detect improvement
        assert trend["trend_direction"] == "improving"
        assert trend["trend_percentage"] > 50  # Significant improvement

    def test_cyclical_performance_pattern(self):
        """Test handling of cyclical performance patterns."""
        monitor = PerformanceMonitor()

        # Create cyclical pattern (e.g., daily load cycles)
        cycle_length = 20
        for i in range(HISTORY_SIZE):
            cycle_position = i % cycle_length

            if cycle_position < 5:  # Peak load
                update_time = random.uniform(3.0, 5.0)
            elif cycle_position < 15:  # Normal load
                update_time = random.uniform(0.8, 1.5)
            else:  # Low load
                update_time = random.uniform(0.3, 0.8)

            monitor.record_update(update_time)

        # Should handle cyclical patterns reasonably
        stats = monitor.get_stats()
        trend = monitor.analyze_performance_trend()

        # Trend analysis may show stable or slight variation
        assert trend["trend_direction"] in ["stable", "improving", "degrading"]
        assert abs(trend["trend_percentage"]) < 100  # Not extreme change

        # Statistics should reflect the cyclical nature
        assert stats["p95"] > stats["average_update_time"]  # High variance


class TestRealisticsScenarios:
    """Test realistic production-like scenarios."""

    def test_realistic_50_dog_production_load(self):
        """Test realistic 50-dog production scenario."""
        monitor = PerformanceMonitor(alert_threshold=3.0)

        # Realistic production parameters
        dogs_count = 50
        average_entities_per_dog = 12
        total_entities = dogs_count * average_entities_per_dog

        # Simulate realistic update patterns over time
        simulation_cycles = 200  # Longer simulation

        for cycle in range(simulation_cycles):
            # Realistic performance model
            base_update_time = 0.2  # 200ms base
            entity_processing_time = total_entities * 0.003  # 3ms per entity

            # Add realistic variations
            if cycle % 50 == 0:  # Periodic heavy operations (GC, etc.)
                gc_overhead = random.uniform(1.0, 3.0)
            else:
                gc_overhead = 0

            if random.random() < 0.1:  # 10% chance of network delays
                network_delay = random.uniform(0.5, 2.0)
            else:
                network_delay = 0

            # Random system load variations
            system_load_factor = random.uniform(0.8, 1.5)

            total_time = (
                base_update_time + entity_processing_time + gc_overhead + network_delay
            ) * system_load_factor

            # Realistic error patterns
            error_count = 0
            if random.random() < 0.02:  # 2% chance of errors
                error_count = random.randint(1, 3)

            monitor.record_update(total_time, error_count)

        # Analyze results
        stats = monitor.get_stats()
        health = monitor.get_performance_health_score()
        monitor.analyze_performance_trend()

        # Verify realistic performance characteristics
        assert stats["average_update_time"] < 10.0  # Should be reasonable
        assert stats["error_rate"] < 5.0  # Low error rate
        assert health["overall_score"] > 30  # Should be manageable

        # Performance should scale reasonably with entity count
        expected_base_time = 0.2 + (total_entities * 0.003)
        assert (
            stats["min_update_time"] >= expected_base_time * 0.5
        )  # Within reasonable bounds

    def test_weekend_vs_weekday_patterns(self):
        """Test different performance patterns (weekend vs weekday)."""
        monitor = PerformanceMonitor()

        # Simulate mixed load patterns
        for day in range(7):  # One week
            if day < 5:  # Weekday - higher load
                daily_pattern = [
                    (8, 3.0),  # Morning peak
                    (12, 2.5),  # Lunch peak
                    (18, 3.5),  # Evening peak
                    (22, 1.0),  # Night low
                ]
            else:  # Weekend - different pattern
                daily_pattern = [
                    (10, 1.5),  # Late morning
                    (14, 2.0),  # Afternoon
                    (20, 2.5),  # Evening
                    (2, 0.8),  # Night
                ]

            for hour, load_factor in daily_pattern:
                # Multiple updates per time period
                for _ in range(3):
                    base_time = 0.5
                    update_time = base_time * load_factor * random.uniform(0.8, 1.2)
                    monitor.record_update(update_time)

        # Should handle varied patterns gracefully
        stats = monitor.get_stats()
        assert stats["total_updates"] == 7 * 4 * 3  # 84 updates
        assert stats["max_update_time"] > stats["min_update_time"]


class TestEntityProfileScalingScenarios:
    """Test performance scaling across different entity profiles."""

    def test_entity_profile_performance_scaling(self):
        """Test performance scaling across entity profiles with 50+ dogs."""
        # Entity profile configurations with realistic scaling
        entity_profiles = {
            "basic": {"max_entities": 8, "processing_overhead": 0.001},
            "standard": {"max_entities": 15, "processing_overhead": 0.002},
            "advanced": {"max_entities": 25, "processing_overhead": 0.003},
            "gps_focus": {"max_entities": 20, "processing_overhead": 0.004},
            "health_focus": {"max_entities": 18, "processing_overhead": 0.0025},
        }

        for profile_name, profile_config in entity_profiles.items():
            monitor = PerformanceMonitor(alert_threshold=5.0)

            # Simulate 50+ dogs with this entity profile
            dogs_count = 55
            entities_per_dog = profile_config["max_entities"]
            total_entities = dogs_count * entities_per_dog
            processing_overhead = profile_config["processing_overhead"]

            # Test multiple update cycles
            for cycle in range(100):
                # Calculate realistic update time based on entity profile
                base_time = 0.1  # 100ms base
                entity_processing = total_entities * processing_overhead
                profile_overhead = total_entities * 0.0001  # Additional overhead

                # Add realistic variance
                variance = random.uniform(0.7, 1.4)
                update_time = (
                    base_time + entity_processing + profile_overhead
                ) * variance

                # Profile-specific error rates
                error_probability = {
                    "basic": 0.01,
                    "standard": 0.02,
                    "advanced": 0.04,
                    "gps_focus": 0.06,
                    "health_focus": 0.03,
                }[profile_name]

                error_count = 1 if random.random() < error_probability else 0
                monitor.record_update(update_time, error_count)

            # Verify scaling characteristics
            stats = monitor.get_stats()
            health = monitor.get_performance_health_score()

            # Performance should scale appropriately with entity count
            expected_min_time = 0.1 + (total_entities * processing_overhead * 0.5)
            expected_max_time = expected_min_time * 3  # Allow 3x variance

            assert stats["min_update_time"] >= expected_min_time * 0.8
            assert stats["average_update_time"] < expected_max_time

            # Health should be reasonable for all profiles
            assert health["overall_score"] > 20  # Minimum acceptable health

            # Advanced profiles should have higher processing times but acceptable health
            if profile_name == "advanced":
                assert stats["average_update_time"] > 1.0  # Should be measurable
                assert health["overall_score"] > 50  # Should still be manageable

    def test_mixed_entity_profile_performance(self):
        """Test performance with mixed entity profiles across dogs."""
        monitor = PerformanceMonitor(alert_threshold=4.0)

        # Simulate scenario with mixed profiles
        # 20 basic dogs, 15 standard dogs, 10 advanced dogs, 5 GPS-focused dogs
        dog_profiles = (
            ["basic"] * 20
            + ["standard"] * 15
            + ["advanced"] * 10
            + ["gps_focus"] * 8
            + ["health_focus"] * 7
        )  # Total: 60 dogs

        entity_counts = {
            "basic": 8,
            "standard": 15,
            "advanced": 25,
            "gps_focus": 20,
            "health_focus": 18,
        }

        # Calculate total entity load
        sum(entity_counts[profile] for profile in dog_profiles)

        # Simulate coordinated updates across all dogs
        for cycle in range(150):
            # Process all dogs in batches (realistic coordinator behavior)
            batch_size = 15  # Process 15 dogs per update cycle

            for batch_start in range(0, len(dog_profiles), batch_size):
                batch_profiles = dog_profiles[batch_start : batch_start + batch_size]

                # Calculate batch processing time
                batch_entities = sum(
                    entity_counts[profile] for profile in batch_profiles
                )

                base_time = 0.05  # 50ms base per batch
                entity_processing = batch_entities * 0.002  # 2ms per entity
                batch_overhead = len(batch_profiles) * 0.01  # 10ms per dog overhead

                # Add realistic variations
                if random.random() < 0.15:  # 15% chance of slow batch
                    slow_factor = random.uniform(2.0, 4.0)
                else:
                    slow_factor = random.uniform(0.8, 1.3)

                batch_time = (
                    base_time + entity_processing + batch_overhead
                ) * slow_factor

                # Batch error probability increases with complexity
                complexity_factor = (
                    len(set(batch_profiles)) / 5.0
                )  # More profiles = more complexity
                error_probability = 0.02 * complexity_factor
                error_count = (
                    random.randint(0, 2) if random.random() < error_probability else 0
                )

                monitor.record_update(batch_time, error_count)

        # Analyze mixed profile performance
        stats = monitor.get_stats()
        health = monitor.get_performance_health_score()
        monitor.analyze_performance_trend()

        # Should handle mixed complexity well
        assert stats["total_updates"] > 100
        assert stats["average_update_time"] < 8.0  # Should be manageable
        assert health["overall_score"] > 40  # Reasonable health with complexity

        # Error rate should be acceptable
        assert stats["error_rate"] < 8.0  # Under 8% error rate


class TestExtendedMemoryLeakDetection:
    """Test memory leak detection over extended periods."""

    def test_long_running_memory_stability(self):
        """Test memory stability over extended operation periods."""
        import gc

        monitor = PerformanceMonitor()

        # Simulate very long-running operation
        extended_cycles = HISTORY_SIZE * 10  # 10x normal history

        # Track memory usage over time
        memory_samples = []

        for cycle in range(extended_cycles):
            # Realistic update pattern
            update_time = random.uniform(0.5, 3.0)
            error_count = 1 if random.random() < 0.03 else 0

            monitor.record_update(update_time, error_count)

            # Sample memory every 100 cycles
            if cycle % 100 == 0:
                gc.collect()  # Force garbage collection
                memory_usage = self._get_monitor_memory_usage(monitor)
                memory_samples.append(memory_usage)

        # Analyze memory growth pattern
        if len(memory_samples) > 5:
            # Should not have significant memory growth after initial stabilization
            stabilized_samples = memory_samples[2:]  # Skip initial growth
            memory_growth = max(stabilized_samples) - min(stabilized_samples)

            # Memory should be stable (growth < 50% of initial)
            initial_memory = (
                memory_samples[1] if len(memory_samples) > 1 else memory_samples[0]
            )
            assert memory_growth < initial_memory * 0.5

        # Verify data structures are properly bounded
        assert len(monitor._update_times) == HISTORY_SIZE
        assert len(monitor._error_counts) == HISTORY_SIZE

        # Cache should not grow unbounded
        assert len(monitor._percentile_cache) < 100

    def test_memory_pressure_recovery(self):
        """Test recovery from memory pressure situations."""
        import gc

        # Create multiple monitors to simulate memory pressure
        monitors = []

        try:
            # Create many monitors with full data
            for i in range(50):  # 50 concurrent monitors
                monitor = PerformanceMonitor()

                # Fill each monitor to capacity
                for j in range(HISTORY_SIZE):
                    update_time = random.uniform(0.1, 5.0)
                    error_count = random.randint(0, 3)
                    monitor.record_update(update_time, error_count)

                monitors.append(monitor)

            # Force memory pressure
            gc.collect()

            # All monitors should still function correctly
            for i, monitor in enumerate(monitors):
                stats = monitor.get_stats()
                assert stats["total_updates"] == HISTORY_SIZE
                assert "average_update_time" in stats

                # Add more data to test continued operation
                monitor.record_update(1.0 + i * 0.01, 0)
                new_stats = monitor.get_stats()
                assert new_stats["total_updates"] == HISTORY_SIZE  # Still bounded

        finally:
            # Cleanup
            monitors.clear()
            gc.collect()

    def _get_monitor_memory_usage(self, monitor: PerformanceMonitor) -> int:
        """Estimate memory usage of monitor (simplified)."""
        # Simplified memory estimation
        update_times_size = len(monitor._update_times) * 8  # float64
        error_counts_size = len(monitor._error_counts) * 4  # int32
        cache_size = len(monitor._percentile_cache) * 16  # key + value

        return update_times_size + error_counts_size + cache_size


class TestCrossDogPerformanceImpact:
    """Test performance impact analysis across multiple dogs."""

    def test_dog_count_scaling_impact(self):
        """Test performance impact as dog count scales."""
        # Test different dog counts: 10, 25, 50, 75, 100
        dog_counts = [10, 25, 50, 75, 100]
        scaling_results = []

        for dog_count in dog_counts:
            monitor = PerformanceMonitor()

            # Simulate realistic entity distribution
            entities_per_dog = 12  # Average
            total_entities = dog_count * entities_per_dog

            # Test performance for this scale
            test_cycles = 50
            start_time = time.time()

            for cycle in range(test_cycles):
                # Realistic scaling model: O(n) with some overhead
                base_time = 0.1
                linear_time = total_entities * 0.002
                overhead_time = dog_count * 0.005  # Per-dog overhead
                network_time = random.uniform(0, 0.2) if random.random() < 0.1 else 0

                total_time = (
                    base_time + linear_time + overhead_time + network_time
                ) * random.uniform(0.8, 1.3)

                monitor.record_update(total_time)

            test_duration = time.time() - start_time
            stats = monitor.get_stats()

            scaling_results.append(
                {
                    "dog_count": dog_count,
                    "total_entities": total_entities,
                    "avg_update_time": stats["average_update_time"],
                    "p95_time": stats["p95"],
                    "test_duration": test_duration,
                }
            )

        # Analyze scaling characteristics
        for i in range(1, len(scaling_results)):
            current = scaling_results[i]
            previous = scaling_results[i - 1]

            # Performance should scale sub-linearly (not worse than O(n))
            entity_ratio = current["total_entities"] / previous["total_entities"]
            time_ratio = current["avg_update_time"] / previous["avg_update_time"]

            # Time scaling should not be worse than entity scaling
            assert time_ratio <= entity_ratio * 1.5  # Allow 50% overhead

        # Final scale (100 dogs) should still be manageable
        final_result = scaling_results[-1]
        assert final_result["avg_update_time"] < 15.0  # Under 15 seconds
        assert final_result["p95_time"] < 25.0  # 95th percentile under 25 seconds

    def test_module_complexity_impact(self):
        """Test performance impact of different module combinations."""
        # Define module complexity scenarios
        module_scenarios = [
            {"name": "minimal", "modules": ["feeding"], "complexity": 1.0},
            {
                "name": "standard",
                "modules": ["feeding", "walk", "health"],
                "complexity": 1.5,
            },
            {
                "name": "gps_enabled",
                "modules": ["feeding", "walk", "health", "gps"],
                "complexity": 2.0,
            },
            {
                "name": "comprehensive",
                "modules": [
                    "feeding",
                    "walk",
                    "health",
                    "gps",
                    "medication",
                    "grooming",
                ],
                "complexity": 2.5,
            },
            {
                "name": "maximum",
                "modules": [
                    "feeding",
                    "walk",
                    "health",
                    "gps",
                    "medication",
                    "grooming",
                    "training",
                    "visitor",
                ],
                "complexity": 3.0,
            },
        ]

        scenario_results = []

        for scenario in module_scenarios:
            monitor = PerformanceMonitor()

            # Simulate 50 dogs with this module configuration
            dogs_count = 50
            entities_per_module = 3  # Average entities per module
            total_entities = dogs_count * len(scenario["modules"]) * entities_per_module
            complexity_factor = scenario["complexity"]

            # Test performance with this configuration
            for cycle in range(75):
                base_time = 0.1
                module_processing = total_entities * 0.002 * complexity_factor
                complexity_overhead = dogs_count * 0.01 * complexity_factor

                # Complexity affects variance and error rates
                variance_factor = 1.0 + (complexity_factor - 1.0) * 0.5
                variance = random.uniform(1.0 / variance_factor, variance_factor)

                total_time = (
                    base_time + module_processing + complexity_overhead
                ) * variance

                # More complex configurations have higher error rates
                error_probability = 0.01 * complexity_factor
                error_count = 1 if random.random() < error_probability else 0

                monitor.record_update(total_time, error_count)

            stats = monitor.get_stats()
            health = monitor.get_performance_health_score()

            scenario_results.append(
                {
                    "scenario": scenario["name"],
                    "complexity": complexity_factor,
                    "total_entities": total_entities,
                    "avg_time": stats["average_update_time"],
                    "p95_time": stats["p95"],
                    "error_rate": stats["error_rate"],
                    "health_score": health["overall_score"],
                }
            )

        # Verify performance scaling with complexity
        for i in range(1, len(scenario_results)):
            current = scenario_results[i]
            previous = scenario_results[i - 1]

            # More complex scenarios should take longer but remain manageable
            assert current["avg_time"] >= previous["avg_time"]  # Should increase
            assert current["avg_time"] < 20.0  # But stay under 20 seconds

            # Health should decrease with complexity but remain acceptable
            assert (
                current["health_score"] <= previous["health_score"] + 10
            )  # Allow some variance
            assert current["health_score"] > 25  # Minimum acceptable health

        # Maximum complexity should still be usable
        max_complexity = scenario_results[-1]
        assert max_complexity["avg_time"] < 18.0
        assert max_complexity["health_score"] > 30
        assert max_complexity["error_rate"] < 15.0


class TestIntegrationWithCoordinatorPatterns:
    """Test integration patterns with coordinator update cycles."""

    def test_coordinator_batch_update_simulation(self):
        """Test performance monitoring with coordinator-style batch updates."""
        monitor = PerformanceMonitor(alert_threshold=5.0)

        # Simulate realistic coordinator update patterns
        dogs_count = 60
        batch_size = 15  # Process 15 dogs per batch

        # Simulate one hour of operations (120 update cycles)
        for hour_cycle in range(120):
            # Each cycle processes all dogs in batches
            for batch_start in range(0, dogs_count, batch_size):
                batch_end = min(batch_start + batch_size, dogs_count)
                dogs_in_batch = batch_end - batch_start

                # Simulate batch processing time
                base_time = 0.1  # 100ms base
                per_dog_time = dogs_in_batch * 0.05  # 50ms per dog
                entity_processing = (
                    dogs_in_batch * 12 * 0.003
                )  # 3ms per entity (12 entities/dog avg)

                # Add realistic variations
                if hour_cycle % 20 == 0:  # Every 10 minutes, slower updates
                    maintenance_overhead = random.uniform(1.0, 2.0)
                else:
                    maintenance_overhead = 0

                # Network and system variations
                system_factor = random.uniform(0.7, 1.8)

                batch_time = (
                    base_time + per_dog_time + entity_processing + maintenance_overhead
                ) * system_factor

                # Batch error simulation
                error_count = 0
                if random.random() < 0.05:  # 5% chance of batch errors
                    error_count = random.randint(1, dogs_in_batch)

                monitor.record_update(batch_time, error_count)

        # Analyze coordinator-style performance
        stats = monitor.get_stats()
        health = monitor.get_performance_health_score()
        monitor.analyze_performance_trend()

        # Should handle coordinator patterns well
        total_batches = (120 * dogs_count) // batch_size
        expected_updates = min(total_batches, HISTORY_SIZE)
        assert stats["total_updates"] == expected_updates

        # Performance should be reasonable for batch processing
        assert stats["average_update_time"] < 8.0  # Under 8 seconds per batch
        assert stats["p95"] < 15.0  # 95th percentile under 15 seconds

        # Health should be good for realistic workload
        assert health["overall_score"] > 50

        # Error rate should be low
        assert stats["error_rate"] < 10.0

    def test_selective_update_performance(self):
        """Test performance with selective entity updates (realistic optimization)."""
        monitor = PerformanceMonitor()

        # Simulate selective updates where only changed entities are updated
        dogs_count = 50
        total_entities = dogs_count * 15  # 15 entities per dog

        for cycle in range(200):
            # Realistic selective update: only 20-40% of entities change per cycle
            change_rate = random.uniform(0.2, 0.4)
            entities_to_update = int(total_entities * change_rate)

            # Calculate update time based on entities that actually need updating
            base_time = 0.05  # 50ms base
            selective_processing = entities_to_update * 0.004  # 4ms per changed entity
            coordination_overhead = dogs_count * 0.002  # 2ms per dog coordination

            # Add variance
            variance = random.uniform(0.8, 1.4)
            update_time = (
                base_time + selective_processing + coordination_overhead
            ) * variance

            # Selective updates should have lower error rates
            error_count = 1 if random.random() < 0.01 else 0  # 1% error rate

            monitor.record_update(update_time, error_count)

        stats = monitor.get_stats()
        health = monitor.get_performance_health_score()

        # Selective updates should be faster than full updates
        assert stats["average_update_time"] < 5.0  # Should be much faster
        assert stats["p95"] < 8.0  # Even 95th percentile should be reasonable

        # Should have excellent health with selective updates
        assert health["overall_score"] > 70
        assert health["health_level"] in ["good", "excellent"]

        # Very low error rate
        assert stats["error_rate"] < 3.0


if __name__ == "__main__":
    pytest.main([__file__])
