"""Intelligent batch update manager for PawControl integration.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Priority-based batch processing with intelligent queuing.
Extracted from monolithic coordinator for better maintainability.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Batch processing constants
MAX_BATCH_SIZE = 15
FORCE_BATCH_INTERVAL = 30  # seconds


class BatchManager:
    """Intelligent batch update manager with priority queuing."""

    def __init__(self, max_batch_size: int = MAX_BATCH_SIZE) -> None:
        """Initialize with priority-based batching.

        Args:
            max_batch_size: Maximum batch size
        """
        self._max_batch_size = max_batch_size
        self._pending_updates: dict[str, int] = {}  # dog_id -> priority
        self._update_lock = asyncio.Lock()
        self._last_batch_time = dt_util.utcnow()

        _LOGGER.debug("BatchManager initialized with max_batch_size=%d", max_batch_size)

    async def add_to_batch(self, dog_id: str, priority: int = 0) -> None:
        """Add dog to pending updates with priority.

        Args:
            dog_id: Dog identifier
            priority: Update priority (higher = more urgent)
        """
        async with self._update_lock:
            # Keep highest priority
            if dog_id in self._pending_updates:
                self._pending_updates[dog_id] = max(
                    self._pending_updates[dog_id], priority
                )
            else:
                self._pending_updates[dog_id] = priority

    async def get_batch(self) -> list[str]:
        """Get prioritized batch.

        Returns:
            List of dog IDs in priority order
        """
        async with self._update_lock:
            # Sort by priority (descending)
            sorted_dogs = sorted(
                self._pending_updates.items(), key=lambda x: x[1], reverse=True
            )

            # Take top N by priority
            batch = [dog_id for dog_id, _ in sorted_dogs[: self._max_batch_size]]

            # Remove from pending
            for dog_id in batch:
                self._pending_updates.pop(dog_id, None)

            self._last_batch_time = dt_util.utcnow()
            return batch

    async def has_pending(self) -> bool:
        """Check if updates are pending.

        Returns:
            True if there are pending updates
        """
        async with self._update_lock:
            return len(self._pending_updates) > 0

    async def should_batch_now(
        self, force_interval: int = FORCE_BATCH_INTERVAL
    ) -> bool:
        """Check if batch should be processed now.

        Args:
            force_interval: Force batch after this many seconds

        Returns:
            True if batch should be processed
        """
        async with self._update_lock:
            if not self._pending_updates:
                return False

            # Process if batch is full
            if len(self._pending_updates) >= self._max_batch_size:
                return True

            # Process if timeout reached
            elapsed = (dt_util.utcnow() - self._last_batch_time).total_seconds()
            return elapsed >= force_interval

    async def clear_pending(self) -> int:
        """Clear all pending updates.

        Returns:
            Number of pending updates cleared
        """
        async with self._update_lock:
            count = len(self._pending_updates)
            self._pending_updates.clear()
            return count

    async def get_pending_count(self) -> int:
        """Get number of pending updates.

        Returns:
            Number of pending updates
        """
        async with self._update_lock:
            return len(self._pending_updates)

    async def get_pending_with_priorities(self) -> dict[str, int]:
        """Get pending updates with their priorities.

        Returns:
            Dictionary mapping dog_id to priority
        """
        async with self._update_lock:
            return self._pending_updates.copy()

    async def remove_from_batch(self, dog_id: str) -> bool:
        """Remove specific dog from pending updates.

        Args:
            dog_id: Dog identifier to remove

        Returns:
            True if dog was pending and removed
        """
        async with self._update_lock:
            if dog_id in self._pending_updates:
                del self._pending_updates[dog_id]
                return True
            return False

    async def update_priority(self, dog_id: str, new_priority: int) -> bool:
        """Update priority for pending dog.

        Args:
            dog_id: Dog identifier
            new_priority: New priority value

        Returns:
            True if priority was updated
        """
        async with self._update_lock:
            if dog_id in self._pending_updates:
                self._pending_updates[dog_id] = new_priority
                return True
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get batch manager statistics.

        Returns:
            Dictionary with batch statistics
        """
        elapsed_since_batch = (dt_util.utcnow() - self._last_batch_time).total_seconds()

        return {
            "max_batch_size": self._max_batch_size,
            "pending_updates": len(self._pending_updates),
            "last_batch_seconds_ago": round(elapsed_since_batch, 1),
            "force_interval": FORCE_BATCH_INTERVAL,
            "pending_breakdown": dict(self._pending_updates)
            if self._pending_updates
            else {},
        }

    async def get_next_batch_time(self) -> datetime:
        """Calculate when next batch should be processed.

        Returns:
            Datetime when next batch should be processed
        """
        async with self._update_lock:
            if not self._pending_updates:
                # No pending updates, return far future
                return dt_util.utcnow() + dt_util.dt.timedelta(hours=1)

            if len(self._pending_updates) >= self._max_batch_size:
                # Batch is full, process immediately
                return dt_util.utcnow()

            # Calculate based on force interval
            return self._last_batch_time + dt_util.dt.timedelta(
                seconds=FORCE_BATCH_INTERVAL
            )

    async def optimize_batching(self) -> dict[str, Any]:
        """Optimize batch settings based on current load.

        Returns:
            Optimization report
        """
        async with self._update_lock:
            current_load = len(self._pending_updates)

            # Adjust batch size based on load
            old_batch_size = self._max_batch_size

            if current_load > 30:
                # High load - increase batch size
                self._max_batch_size = min(25, self._max_batch_size + 5)
            elif current_load < 5:
                # Low load - decrease batch size for responsiveness
                self._max_batch_size = max(10, self._max_batch_size - 2)

            optimization_made = old_batch_size != self._max_batch_size

            return {
                "optimization_performed": optimization_made,
                "old_batch_size": old_batch_size,
                "new_batch_size": self._max_batch_size,
                "current_load": current_load,
                "recommendation": self._get_load_recommendation(current_load),
            }

    def _get_load_recommendation(self, load: int) -> str:
        """Get load-based recommendation.

        Args:
            load: Current pending update count

        Returns:
            Recommendation string
        """
        if load > 50:
            return "Very high load - consider reducing update frequency"
        elif load > 20:
            return "High load - batch processing optimized"
        elif load > 10:
            return "Normal load - standard processing"
        elif load > 0:
            return "Low load - responsive processing"
        else:
            return "No load - system idle"
