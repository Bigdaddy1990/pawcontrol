"""Walk helper utilities for Paw Control flows."""

from __future__ import annotations

from typing import Final

WALK_SETTINGS_FIELDS: Final[tuple[str, ...]] = (
  "walk_detection_timeout",
  "minimum_walk_duration",
  "maximum_walk_duration",
  "auto_end_walks",
)
