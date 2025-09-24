"""Minimal annotated YAML loader stub for tests."""

from __future__ import annotations

from typing import Any


def load_yaml(path: str, *, secrets: Any | None = None) -> Any:
    """Load YAML content from the provided path.

    This stub implementation simply raises ``FileNotFoundError`` because the
    real Home Assistant implementation reads files from disk. The tests patch
    this function with a custom loader, so under test it never reaches this
    fallback implementation.
    """

    raise FileNotFoundError(path)
