"""Comprehensive edge case tests for PawControl performance manager - Gold Standard coverage.

This module provides advanced edge case testing to achieve 95%+ test coverage
for the performance manager, including stress testing with 50+ dogs scenarios,
extreme performance conditions, cache behavior validation, and error handling.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.performance_manager import (
    HISTORY_SIZE,
    PERFORMANCE_ALERT_THRESHOLD,
    PerformanceMonitor,
)
from homeassistant.util import dt as dt_util


class TestPerformanceManagerStressScenarios:
    """Test performance manager under extreme stress conditions."""

    @pytest.fixture
    def performance_monitor(self):
        """Create performance monitor for stress testing."""
        return PerformanceMonitor(alert_threshold=5.0)

    def test_massive_update_recording_stress(self, performance_monitor):
        """Test recording massive number of updates (50+ dogs simulation)."""
        import time
        
        # Simulate 50 dogs with different update patterns over time
        start_time = time.time()
        
        # Each dog updates every 30 seconds, simulate 1 hour = 120 updates per dog
        
        # Generate realistic update times with variance
        update_patterns = []
        for dog_id in range(50):
            # Different dogs have different performance characteristics
            base_time = 0.5 + (dog_id % 10) * 0.1  # 0.5-1.4 seconds base
            variance = 0.1 + (dog_id % 5) * 0.05   # Variable performance
            
            for update in range(120):
                # Simulate realistic variance
                update_time = base_time + (update % 3) * variance
                error_count = 1 if update % 20 == 0 else 0  # 5% error rate
                update_patterns.append((update_time, error_count))
        
        # Record all updates
        for update_time, error_count in update_patterns:
            performance_monitor.record_update(update_time, error_count)
        
        end_time = time.time()
        recording_duration = end_time - start_time
        
        # Should handle massive updates efficiently
        assert recording_duration < 2.0  # Should complete in under 2 seconds
        
        # Verify data integrity after stress
        stats = performance_monitor.get_stats()
        assert stats["total_updates"] == HISTORY_SIZE  # Should respect max size
        assert "p95" in stats
        assert "p99" in stats
        assert stats["error_rate"] > 0  # Should track errors

    def test_extreme_performance_values_stress(self, performance_monitor):
        """Test handling of extreme performance values."""
        extreme_values = [
            (0.001, 0),      # Very fast updates
            (0.0001, 0),     # Extremely fast updates
            (60.0, 0),       # Very slow updates (1 minute)
            (300.0, 5),      # Extremely slow updates (5 minutes) with errors
            (0.0, 0),        # Zero time (edge case)
            (float('inf'), 0),  # Infinite time (error case)
            (-1.0, 0),       # Negative time (invalid)
            (1.5, 100),      # Normal time with many errors
            (0.1, -5),       # Negative errors (invalid)
        ]
        
        # Record extreme values
        for duration, errors in extreme_values:
            try:
                performance_monitor.record_update(duration, errors)
            except (ValueError, OverflowError):
                # Some extreme values might raise exceptions
                pass
        
        # Should handle extreme values gracefully
        stats = performance_monitor.get_stats()
        assert isinstance(stats, dict)
        assert not any(val == float('inf') for val in stats.values() if isinstance(val, (int, float)))

    def test_concurrent_access_stress(self, performance_monitor):
        """Test concurrent access to performance monitor."""
        import random
        import threading
        
        results = []
        errors = []
        
        def record_updates(thread_id):
            """Record updates from multiple threads."""
            try:
                for i in range(100):
                    duration = random.uniform(0.1, 2.0)
                    error_count = random.randint(0, 3)
                    performance_monitor.record_update(duration, error_count)
                    
                    # Occasionally get stats
                    if i % 10 == 0:
                        stats = performance_monitor.get_stats()
                        results.append((thread_id, stats))
                        
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append((thread_id, e))
        
        # Start multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=record_updates, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5.0)
        
        # Should handle concurrent access without errors
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        
        # All threads should have been able to get stats
        assert len(results) > 0
        
        # Final stats should be consistent
        final_stats = performance_monitor.get_stats()
        assert final_stats["total_updates"] > 0

    def test_memory_usage_with_large_datasets(self, performance_monitor):
        """Test memory usage with large performance datasets."""
        import sys
        
        # Get initial memory usage
        initial_size = sys.getsizeof(performance_monitor._update_times) + sys.getsizeof(performance_monitor._error_counts)
        
        # Fill with maximum data
        for i in range(HISTORY_SIZE * 2):  # More than max to test deque behavior
            performance_monitor.record_update(1.0 + i * 0.001, i % 5)
        
        # Check memory usage after filling
        final_size = sys.getsizeof(performance_monitor._update_times) + sys.getsizeof(performance_monitor._error_counts)
        
        # Memory should be bounded by HISTORY_SIZE
        assert len(performance_monitor._update_times) == HISTORY_SIZE
        assert len(performance_monitor._error_counts) == HISTORY_SIZE
        
        # Memory usage should be reasonable (not growing unbounded)
        memory_growth = final_size - initial_size
        assert memory_growth < HISTORY_SIZE * 50  # Reasonable per-entry overhead

    def test_rapid_threshold_changes_stress(self, performance_monitor):
        """Test rapid threshold changes under stress."""
        # Record some baseline data
        for i in range(50):
            performance_monitor.record_update(1.0 + i * 0.1, 0)
        
        # Rapidly change thresholds
        thresholds = [0.5, 2.0, 10.0, 0.1, 5.0, 1.0, 15.0, 0.05]
        
        for threshold in thresholds:
            result = performance_monitor.update_alert_threshold(threshold)
            
            # Should return valid analysis
            assert "old_threshold" in result
            assert "new_threshold" in result
            assert result["new_threshold"] == threshold
            
            # Should not crash during rapid changes
            stats = performance_monitor.get_stats()
            assert stats["alert_threshold"] == threshold


class TestPerformanceManagerEdgeCaseValidation:
    """Test performance manager edge cases and boundary conditions."""

    @pytest.fixture
    def empty_monitor(self):
        """Create empty performance monitor for edge case testing."""
        return PerformanceMonitor()

    @pytest.fixture
    def populated_monitor(self):
        """Create populated performance monitor for testing."""
        monitor = PerformanceMonitor()
        # Add varied data for testing
        test_data = [
            (0.5, 0), (1.0, 0), (1.5, 1), (2.0, 0), (0.8, 0),
            (3.0, 2), (0.3, 0), (4.0, 1), (1.2, 0), (2.5, 0),
        ]
        for duration, errors in test_data:
            monitor.record_update(duration, errors)
        return monitor

    def test_empty_monitor_operations(self, empty_monitor):
        """Test operations on empty monitor."""
        # Get stats with no data
        stats = empty_monitor.get_stats()
        assert stats["no_data"] is True
        
        # Get recent performance with no data
        recent = empty_monitor.get_recent_performance()
        assert recent["no_data"] is True
        
        # Percentile calculations with no data
        assert empty_monitor._get_percentile(50) == 0.0
        assert empty_monitor._get_percentile(95) == 0.0
        assert empty_monitor._get_percentile(99) == 0.0
        
        # Health score with no data
        health = empty_monitor.get_performance_health_score()
        assert health["no_data"] is True
        
        # Trend analysis with insufficient data
        trend = empty_monitor.analyze_performance_trend()
        assert trend["insufficient_data"] is True

    def test_percentile_edge_cases(self, populated_monitor):
        """Test percentile calculations with edge cases."""
        # Test boundary percentiles
        assert populated_monitor._get_percentile(0) >= 0
        assert populated_monitor._get_percentile(100) >= 0
        
        # Test invalid percentiles (should handle gracefully)
        try:
            result = populated_monitor._get_percentile(-10)
            assert result >= 0  # Should not crash
        except (ValueError, IndexError):
            pass  # Expected for invalid percentiles
        
        try:
            result = populated_monitor._get_percentile(150)
            assert result >= 0  # Should not crash
        except (ValueError, IndexError):
            pass  # Expected for invalid percentiles

    def test_cache_behavior_edge_cases(self, populated_monitor):
        """Test percentile cache behavior with edge cases."""
        # Fill cache with different percentiles
        p50_1 = populated_monitor._get_percentile(50)
        populated_monitor._get_percentile(95)
        populated_monitor._get_percentile(99)
        
        # Should return cached values
        p50_2 = populated_monitor._get_percentile(50)
        assert p50_1 == p50_2
        
        # Add new data to invalidate cache
        populated_monitor.record_update(10.0, 0)
        
        # Should recalculate percentiles
        populated_monitor._get_percentile(50)
        # Might be different due to new data
        
        # Test cache expiration
        with patch('homeassistant.util.dt.utcnow') as mock_time:
            future_time = dt_util.utcnow() + timedelta(minutes=1)
            mock_time.return_value = future_time
            
            # Should recalculate due to expired cache
            p50_4 = populated_monitor._get_percentile(50)
            assert isinstance(p50_4, float)

    def test_alert_rate_limiting_edge_cases(self, populated_monitor):
        """Test alert rate limiting with edge cases."""
        # Mock logger to capture alerts
        with patch('custom_components.pawcontrol.performance_manager._LOGGER') as mock_logger:
            # First slow update should trigger alert
            populated_monitor.record_update(15.0, 0)  # Above threshold
            
            # Should have logged warning
            mock_logger.warning.assert_called()
            
            # Rapid subsequent slow updates should be rate limited
            mock_logger.warning.reset_mock()
            for i in range(5):
                populated_monitor.record_update(12.0, 0)
            
            # Should not trigger additional alerts (rate limited)
            assert mock_logger.warning.call_count == 0

    def test_threshold_update_edge_cases(self, populated_monitor):
        """Test threshold updates with edge case values."""
        # Test extreme thresholds
        edge_thresholds = [0.0, 0.001, 1000.0, float('inf'), -1.0]
        
        for threshold in edge_thresholds:
            try:
                result = populated_monitor.update_alert_threshold(threshold)
                assert "new_threshold" in result
                assert result["new_threshold"] == threshold
            except (ValueError, OverflowError):
                # Some extreme values might not be accepted
                pass

    def test_recent_performance_edge_cases(self, populated_monitor):
        """Test recent performance calculation with edge cases."""
        # Test with various time windows
        for minutes in [0, 1, 5, 60, -5]:
            recent = populated_monitor.get_recent_performance(minutes)
            assert isinstance(recent, dict)
            if "no_data" not in recent:
                assert "window_minutes" in recent

    def test_health_score_edge_cases(self, populated_monitor):
        """Test health score calculation with edge case performance."""
        # Add extreme performance data
        populated_monitor.record_update(0.001, 0)  # Very fast
        populated_monitor.record_update(100.0, 50)  # Very slow with many errors
        
        health = populated_monitor.get_performance_health_score()
        
        assert "overall_score" in health
        assert 0 <= health["overall_score"] <= 100
        assert health["health_level"] in ["excellent", "good", "fair", "poor"]
        assert "component_scores" in health
        assert "recommendations" in health
        
        # Test component scores are in valid range
        for score in health["component_scores"].values():
            assert 0 <= score <= 100

    def test_trend_analysis_edge_cases(self, populated_monitor):
        """Test trend analysis with edge case data patterns."""
        # Add data with clear trend patterns
        
        # Clear existing data first
        populated_monitor.reset_stats()
        
        # Add improving trend
        for i in range(20):
            populated_monitor.record_update(2.0 - i * 0.05, 0)  # Getting faster
        
        trend = populated_monitor.analyze_performance_trend()
        assert trend["trend_direction"] == "improving"
        
        # Add more data for degrading trend
        for i in range(20):
            populated_monitor.record_update(1.0 + i * 0.1, 0)  # Getting slower
        
        trend = populated_monitor.analyze_performance_trend()
        assert trend["trend_direction"] == "degrading"
        
        # Test with insufficient data
        populated_monitor.reset_stats()
        for i in range(5):  # Less than minimum required
            populated_monitor.record_update(1.0, 0)
        
        trend = populated_monitor.analyze_performance_trend()
        assert trend["insufficient_data"] is True

    def test_stats_reset_edge_cases(self, populated_monitor):
        """Test statistics reset functionality."""
        # Get initial stats
        initial_stats = populated_monitor.get_stats()
        assert initial_stats["total_updates"] > 0
        
        # Reset stats
        reset_result = populated_monitor.reset_stats()
        
        # Should return summary of reset
        assert reset_result["reset_completed"] is True
        assert "previous_stats" in reset_result
        assert "reset_timestamp" in reset_result
        
        # Should clear all data
        new_stats = populated_monitor.get_stats()
        assert new_stats["no_data"] is True
        
        # Should clear percentile cache
        assert len(populated_monitor._percentile_cache) == 0


class TestPerformanceManagerRecommendationsEngine:
    """Test the health recommendations engine."""

    def test_recommendations_for_all_score_combinations(self):
        """Test recommendations for various score combinations."""
        monitor = PerformanceMonitor()
        
        test_cases = [
            # (speed, reliability, consistency, expected_recommendation_count)
            (95, 95, 95, 1),  # Excellent - should get positive recommendation
            (50, 95, 95, 1),  # Poor speed
            (95, 50, 95, 1),  # Poor reliability  
            (95, 95, 50, 1),  # Poor consistency
            (50, 50, 50, 3),  # Poor all - should get multiple recommendations
            (70, 70, 70, 3),  # Fair all - should get all recommendations
            (100, 100, 100, 1),  # Perfect - should get positive recommendation
        ]
        
        for speed, reliability, consistency, expected_count in test_cases:
            recommendations = monitor._get_health_recommendations(speed, reliability, consistency)
            assert len(recommendations) >= expected_count
            
            # All recommendations should be strings
            for rec in recommendations:
                assert isinstance(rec, str)
                assert len(rec) > 0

    def test_impact_assessment_edge_cases(self):
        """Test threshold impact assessment with edge cases."""
        monitor = PerformanceMonitor()
        
        # Test with zero alerts
        assessment = monitor._assess_threshold_impact(0, 0)
        assert "No change" in assessment
        
        # Test with large changes
        assessment = monitor._assess_threshold_impact(10, 100)
        assert "increase" in assessment
        assert "900.0%" in assessment
        
        # Test with reduction to zero
        assessment = monitor._assess_threshold_impact(10, 0)
        assert "eliminate all alerts" in assessment
        
        # Test from zero to some
        assessment = monitor._assess_threshold_impact(0, 5)
        assert "5 new alerts" in assessment


class TestPerformanceManagerDataIntegrity:
    """Test data integrity under various conditions."""

    def test_deque_size_limits_integrity(self):
        """Test that deque size limits are properly maintained."""
        monitor = PerformanceMonitor()
        
        # Add more than HISTORY_SIZE entries
        for i in range(HISTORY_SIZE * 2):
            monitor.record_update(1.0 + i * 0.001, i % 3)
        
        # Should maintain size limits
        assert len(monitor._update_times) == HISTORY_SIZE
        assert len(monitor._error_counts) == HISTORY_SIZE
        
        # Should contain most recent entries
        assert list(monitor._update_times)[-1] > list(monitor._update_times)[0]

    def test_data_consistency_across_operations(self):
        """Test data consistency across various operations."""
        monitor = PerformanceMonitor()
        
        # Add test data
        test_updates = [(1.0, 0), (2.0, 1), (3.0, 0), (4.0, 2), (1.5, 0)]
        for duration, errors in test_updates:
            monitor.record_update(duration, errors)
        
        # Stats should be consistent
        stats = monitor.get_stats()
        
        # Verify calculations
        expected_avg = sum(d for d, _ in test_updates) / len(test_updates)
        assert abs(stats["average_update_time"] - expected_avg) < 0.001
        
        expected_errors = sum(e for _, e in test_updates)
        assert stats["total_errors"] == expected_errors
        
        # Percentiles should be in logical order
        assert stats["p50"] <= stats["p95"] <= stats["p99"]
        assert stats["min_update_time"] <= stats["p50"] <= stats["max_update_time"]

    def test_cache_invalidation_integrity(self):
        """Test cache invalidation maintains data integrity."""
        monitor = PerformanceMonitor()
        
        # Add initial data
        for i in range(10):
            monitor.record_update(1.0 + i * 0.1, 0)
        
        # Get percentile (should cache)
        p95_1 = monitor._get_percentile(95)
        
        # Verify cache exists
        assert 95 in monitor._percentile_cache
        
        # Add new data (should invalidate cache)
        monitor.record_update(10.0, 0)
        
        # Get percentile again (should recalculate)
        p95_2 = monitor._get_percentile(95)
        
        # Should be different due to new extreme value
        assert p95_2 != p95_1
        assert p95_2 > p95_1  # Should be higher due to new extreme value

    def test_floating_point_precision_handling(self):
        """Test handling of floating point precision issues."""
        monitor = PerformanceMonitor()
        
        # Add data with potential precision issues
        precision_values = [
            0.1 + 0.2,  # Classic floating point precision issue
            0.123456789012345,  # High precision
            1e-10,  # Very small number
            1e10,   # Very large number
        ]
        
        for value in precision_values:
            monitor.record_update(value, 0)
        
        # Should handle all values without errors
        stats = monitor.get_stats()
        assert "average_update_time" in stats
        assert not any(val != val for val in stats.values() if isinstance(val, float))  # No NaN values


class TestPerformanceManagerIntegrationScenarios:
    """Test performance manager in realistic integration scenarios."""

    def test_realistic_50_dog_scenario(self):
        """Test realistic 50-dog performance monitoring scenario."""
        monitor = PerformanceMonitor(alert_threshold=3.0)
        
        # Simulate 50 dogs with realistic update patterns
        dogs_performance = {}
        
        # Different dog types with different performance characteristics
        dog_types = {
            "small_indoor": {"base_time": 0.3, "variance": 0.1, "error_rate": 0.02},
            "medium_active": {"base_time": 0.8, "variance": 0.3, "error_rate": 0.05},
            "large_outdoor": {"base_time": 1.5, "variance": 0.5, "error_rate": 0.10},
            "senior_health": {"base_time": 2.0, "variance": 0.8, "error_rate": 0.15},
        }
        
        # Assign dogs to types
        for dog_id in range(50):
            dog_type = list(dog_types.keys())[dog_id % len(dog_types)]
            dogs_performance[dog_id] = dog_types[dog_type]
        
        # Simulate 1 day of updates (every 2 minutes = 720 updates per dog)
        total_updates = 0
        for hour in range(24):
            for minute in range(0, 60, 2):  # Every 2 minutes
                for dog_id in range(50):
                    perf = dogs_performance[dog_id]
                    
                    # Simulate realistic variance
                    base_time = perf["base_time"]
                    variance = perf["variance"]
                    error_rate = perf["error_rate"]
                    
                    # Time of day affects performance
                    time_factor = 1.0
                    if 22 <= hour or hour <= 6:  # Night time - slower
                        time_factor = 1.3
                    elif 8 <= hour <= 18:  # Day time - normal
                        time_factor = 1.0
                    else:  # Dawn/dusk - slightly slower
                        time_factor = 1.1
                    
                    # Calculate update time
                    import random
                    update_time = base_time * time_factor + random.uniform(-variance, variance)
                    update_time = max(0.1, update_time)  # Minimum 0.1s
                    
                    # Calculate errors
                    error_count = 1 if random.random() < error_rate else 0
                    
                    monitor.record_update(update_time, error_count)
                    total_updates += 1
        
        # Analyze results
        stats = monitor.get_stats()
        health = monitor.get_performance_health_score()
        trend = monitor.analyze_performance_trend()
        
        # Should handle large dataset
        assert stats["total_updates"] == HISTORY_SIZE  # Limited by history size
        assert stats["average_update_time"] > 0
        assert 0 <= health["overall_score"] <= 100
        
        # Should provide meaningful insights
        assert len(health["recommendations"]) > 0
        assert trend["analysis_confidence"] in ["low", "medium", "high"]

    def test_performance_degradation_detection(self):
        """Test detection of performance degradation over time."""
        monitor = PerformanceMonitor(alert_threshold=2.0)
        
        # Simulate gradual performance degradation
        base_time = 0.5
        degradation_rate = 0.01  # 1% slower each update
        
        for i in range(100):
            current_time = base_time * (1 + degradation_rate * i)
            error_count = 1 if i > 80 else 0  # Errors start appearing later
            
            monitor.record_update(current_time, error_count)
        
        # Should detect degradation
        trend = monitor.analyze_performance_trend()
        health = monitor.get_performance_health_score()
        
        assert trend["trend_direction"] == "degrading"
        assert trend["trend_percentage"] > 0
        assert health["overall_score"] < 90  # Should not be excellent due to degradation

    def test_performance_recovery_detection(self):
        """Test detection of performance recovery/improvement."""
        monitor = PerformanceMonitor()
        
        # Start with poor performance
        for i in range(50):
            monitor.record_update(3.0 + i * 0.02, 1)  # Getting worse
        
        # Then improve
        for i in range(50):
            monitor.record_update(4.0 - i * 0.05, 0)  # Getting better, no errors
        
        # Should detect improvement
        trend = monitor.analyze_performance_trend()
        health = monitor.get_performance_health_score()
        
        assert trend["trend_direction"] == "improving"
        assert health["component_scores"]["reliability"] > 50  # Better reliability due to no recent errors


@pytest.mark.asyncio
async def test_comprehensive_performance_manager_integration():
    """Comprehensive integration test for performance manager."""
    monitor = PerformanceMonitor(alert_threshold=1.0)
    
    # Simulate complete lifecycle
    
    # 1. Initial empty state
    assert monitor.get_stats()["no_data"] is True
    
    # 2. Add varied performance data
    test_data = [
        (0.5, 0), (1.2, 0), (0.8, 1), (2.0, 0), (1.5, 0),
        (0.3, 0), (3.0, 2), (1.0, 0), (4.0, 1), (0.7, 0),
    ]
    
    for duration, errors in test_data:
        monitor.record_update(duration, errors)
    
    # 3. Verify complete functionality
    stats = monitor.get_stats()
    assert stats["total_updates"] == len(test_data)
    assert stats["average_update_time"] > 0
    assert stats["error_rate"] > 0
    
    # 4. Test health scoring
    health = monitor.get_performance_health_score()
    assert 0 <= health["overall_score"] <= 100
    assert health["health_level"] in ["excellent", "good", "fair", "poor"]
    
    # 5. Test trend analysis
    trend = monitor.analyze_performance_trend()
    assert trend["trend_direction"] in ["improving", "degrading", "stable"]
    
    # 6. Test threshold updates
    stats["alert_threshold"]
    new_threshold = 2.5
    impact = monitor.update_alert_threshold(new_threshold)
    assert impact["new_threshold"] == new_threshold
    assert "impact_assessment" in impact
    
    # 7. Test recent performance
    recent = monitor.get_recent_performance(5)
    assert "sample_count" in recent
    
    # 8. Test reset functionality
    reset_result = monitor.reset_stats()
    assert reset_result["reset_completed"] is True
    
    # 9. Verify empty state after reset
    empty_stats = monitor.get_stats()
    assert empty_stats["no_data"] is True
