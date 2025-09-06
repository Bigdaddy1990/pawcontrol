"""Advanced performance monitoring for PawControl integration.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Percentile tracking and smart alerting system.
Extracted from monolithic coordinator for better maintainability.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import timedelta
from typing import Any

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Performance monitoring constants
PERFORMANCE_ALERT_THRESHOLD = 10.0  # seconds
HISTORY_SIZE = 100  # number of measurements to keep


class PerformanceMonitor:
    """Advanced performance monitoring with percentile tracking."""

    def __init__(self, alert_threshold: float = PERFORMANCE_ALERT_THRESHOLD) -> None:
        """Initialize with percentile tracking.

        Args:
            alert_threshold: Alert threshold in seconds
        """
        self._alert_threshold = alert_threshold
        self._update_times = deque(maxlen=HISTORY_SIZE)
        self._error_counts = deque(maxlen=HISTORY_SIZE)
        self._slow_updates = 0
        self._last_alert = dt_util.utcnow() - timedelta(minutes=10)

        # Percentile cache for better monitoring
        self._percentile_cache: dict[int, float] = {}
        self._cache_valid_until = dt_util.utcnow()

        _LOGGER.debug(
            "PerformanceMonitor initialized with threshold=%.1fs", alert_threshold
        )

    def record_update(self, duration: float, error_count: int = 0) -> None:
        """Record update with percentile cache invalidation.

        Args:
            duration: Update duration in seconds
            error_count: Number of errors during update
        """
        self._update_times.append(duration)
        self._error_counts.append(error_count)

        # Invalidate percentile cache
        self._cache_valid_until = dt_util.utcnow()

        if duration > self._alert_threshold:
            self._slow_updates += 1
            self._maybe_send_alert(duration)

    def _maybe_send_alert(self, duration: float) -> None:
        """Send smart performance alerts.

        Args:
            duration: Current update duration that triggered alert
        """
        now = dt_util.utcnow()

        # Rate limit alerts to every 10 minutes
        if (now - self._last_alert).total_seconds() > 600:
            # Calculate percentiles for context
            p95 = self._get_percentile(95)

            _LOGGER.warning(
                "Performance alert: %.2fs (p95=%.2fs, threshold=%.2fs). "
                "Slow updates: %d/%d",
                duration,
                p95,
                self._alert_threshold,
                self._slow_updates,
                len(self._update_times),
            )
            self._last_alert = now

    def _get_percentile(self, percentile: int) -> float:
        """Get percentile with caching.

        Args:
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value
        """
        now = dt_util.utcnow()

        # Check cache validity (30 second cache)
        if now < self._cache_valid_until and percentile in self._percentile_cache:
            return self._percentile_cache[percentile]

        if not self._update_times:
            return 0.0

        # Calculate percentile
        sorted_times = sorted(self._update_times)
        index = int(len(sorted_times) * percentile / 100)
        value = sorted_times[min(index, len(sorted_times) - 1)]

        # Cache for 30 seconds
        self._percentile_cache[percentile] = value
        self._cache_valid_until = now + timedelta(seconds=30)

        return value

    def get_stats(self) -> dict[str, Any]:
        """Get advanced performance statistics.

        Returns:
            Dictionary with comprehensive performance stats
        """
        if not self._update_times:
            return {"no_data": True}

        times = list(self._update_times)
        errors = list(self._error_counts)

        return {
            "average_update_time": sum(times) / len(times),
            "max_update_time": max(times),
            "min_update_time": min(times),
            "p50": self._get_percentile(50),
            "p95": self._get_percentile(95),
            "p99": self._get_percentile(99),
            "slow_updates": self._slow_updates,
            "total_errors": sum(errors),
            "error_rate": sum(errors) / len(errors) * 100 if errors else 0,
            "total_updates": len(times),
            "alert_threshold": self._alert_threshold,
        }

    def get_recent_performance(self, minutes: int = 5) -> dict[str, Any]:
        """Get performance for recent time window.

        Args:
            minutes: Time window in minutes

        Returns:
            Recent performance statistics
        """
        if not self._update_times:
            return {"no_data": True, "window_minutes": minutes}

        # For deque, we approximate recent data (would need timestamps for exact)
        # This is a simplified version - in production might want to store timestamps
        recent_count = min(len(self._update_times), int(len(self._update_times) * 0.2))
        recent_times = (
            list(self._update_times)[-recent_count:] if recent_count > 0 else []
        )
        recent_errors = (
            list(self._error_counts)[-recent_count:] if recent_count > 0 else []
        )

        if not recent_times:
            return {"no_data": True, "window_minutes": minutes}

        return {
            "window_minutes": minutes,
            "sample_count": len(recent_times),
            "average_time": sum(recent_times) / len(recent_times),
            "max_time": max(recent_times),
            "min_time": min(recent_times),
            "total_errors": sum(recent_errors),
            "error_rate": sum(recent_errors) / len(recent_errors) * 100
            if recent_errors
            else 0,
        }

    def update_alert_threshold(self, new_threshold: float) -> dict[str, Any]:
        """Update alert threshold and return impact analysis.

        Args:
            new_threshold: New threshold in seconds

        Returns:
            Impact analysis of threshold change
        """
        old_threshold = self._alert_threshold
        self._alert_threshold = new_threshold

        # Analyze impact on existing data
        if self._update_times:
            times = list(self._update_times)
            old_alerts = sum(1 for t in times if t > old_threshold)
            new_alerts = sum(1 for t in times if t > new_threshold)

            return {
                "old_threshold": old_threshold,
                "new_threshold": new_threshold,
                "threshold_change": new_threshold - old_threshold,
                "old_alert_count": old_alerts,
                "new_alert_count": new_alerts,
                "alert_count_change": new_alerts - old_alerts,
                "impact_assessment": self._assess_threshold_impact(
                    old_alerts, new_alerts
                ),
            }
        else:
            return {
                "old_threshold": old_threshold,
                "new_threshold": new_threshold,
                "no_historical_data": True,
            }

    def _assess_threshold_impact(self, old_alerts: int, new_alerts: int) -> str:
        """Assess impact of threshold change.

        Args:
            old_alerts: Alert count with old threshold
            new_alerts: Alert count with new threshold

        Returns:
            Impact assessment string
        """
        if new_alerts == old_alerts:
            return "No change in alert frequency"
        elif new_alerts > old_alerts:
            increase = new_alerts - old_alerts
            return (
                f"Will increase alerts by {increase} ({increase / old_alerts * 100:.1f}% more)"
                if old_alerts > 0
                else f"Will generate {new_alerts} new alerts"
            )
        else:
            decrease = old_alerts - new_alerts
            return (
                f"Will reduce alerts by {decrease} ({decrease / old_alerts * 100:.1f}% fewer)"
                if old_alerts > 0
                else "Will eliminate all alerts"
            )

    def reset_stats(self) -> dict[str, Any]:
        """Reset all performance statistics.

        Returns:
            Summary of reset statistics
        """
        old_stats = self.get_stats()

        self._update_times.clear()
        self._error_counts.clear()
        self._slow_updates = 0
        self._percentile_cache.clear()
        self._cache_valid_until = dt_util.utcnow()

        return {
            "reset_completed": True,
            "previous_stats": old_stats,
            "reset_timestamp": dt_util.utcnow().isoformat(),
        }

    def analyze_performance_trend(self) -> dict[str, Any]:
        """Analyze performance trend over time.

        Returns:
            Performance trend analysis
        """
        if len(self._update_times) < 10:
            return {"insufficient_data": True, "minimum_required": 10}

        times = list(self._update_times)

        # Split into first and second half for trend analysis
        midpoint = len(times) // 2
        first_half = times[:midpoint]
        second_half = times[midpoint:]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        trend_direction = (
            "improving"
            if second_avg < first_avg
            else "degrading"
            if second_avg > first_avg
            else "stable"
        )
        trend_magnitude = abs(second_avg - first_avg)
        trend_percentage = (trend_magnitude / first_avg * 100) if first_avg > 0 else 0

        return {
            "trend_direction": trend_direction,
            "trend_magnitude": round(trend_magnitude, 3),
            "trend_percentage": round(trend_percentage, 1),
            "first_half_avg": round(first_avg, 3),
            "second_half_avg": round(second_avg, 3),
            "sample_size": len(times),
            "analysis_confidence": "high"
            if len(times) >= 50
            else "medium"
            if len(times) >= 20
            else "low",
        }

    def get_performance_health_score(self) -> dict[str, Any]:
        """Calculate overall performance health score (0-100).

        Returns:
            Performance health assessment
        """
        if not self._update_times:
            return {"no_data": True}

        stats = self.get_stats()

        # Calculate components of health score
        speed_score = 100  # Start at perfect
        if stats["average_update_time"] > self._alert_threshold:
            speed_score = max(
                0, 100 - (stats["average_update_time"] / self._alert_threshold - 1) * 50
            )

        reliability_score = max(
            0, 100 - stats["error_rate"] * 2
        )  # 2% penalty per 1% error rate

        consistency_score = 100
        if stats["p95"] > 0:
            # Penalty for high variance (p95 much higher than average)
            variance_factor = stats["p95"] / stats["average_update_time"]
            if variance_factor > 2:
                consistency_score = max(0, 100 - (variance_factor - 2) * 25)

        # Weighted overall score
        overall_score = (
            speed_score * 0.4 + reliability_score * 0.4 + consistency_score * 0.2
        )

        # Determine health level
        if overall_score >= 90:
            health_level = "excellent"
        elif overall_score >= 75:
            health_level = "good"
        elif overall_score >= 50:
            health_level = "fair"
        else:
            health_level = "poor"

        return {
            "overall_score": round(overall_score, 1),
            "health_level": health_level,
            "component_scores": {
                "speed": round(speed_score, 1),
                "reliability": round(reliability_score, 1),
                "consistency": round(consistency_score, 1),
            },
            "recommendations": self._get_health_recommendations(
                speed_score, reliability_score, consistency_score
            ),
        }

    def _get_health_recommendations(
        self, speed: float, reliability: float, consistency: float
    ) -> list[str]:
        """Get health-based recommendations.

        Args:
            speed: Speed score (0-100)
            reliability: Reliability score (0-100)
            consistency: Consistency score (0-100)

        Returns:
            List of recommendations
        """
        recommendations = []

        if speed < 75:
            recommendations.append(
                "Consider optimizing update algorithms or reducing data processing load"
            )

        if reliability < 75:
            recommendations.append(
                "Investigate and fix error sources to improve reliability"
            )

        if consistency < 75:
            recommendations.append(
                "Reduce performance variance through better resource management"
            )

        if speed > 90 and reliability > 90 and consistency > 90:
            recommendations.append(
                "Performance is excellent - consider monitoring trends for early degradation detection"
            )

        return recommendations
