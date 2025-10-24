"""Language normalization helpers for PawControl translations."""

from __future__ import annotations

from collections.abc import Collection

__all__ = ["normalize_language"]


def normalize_language(
    language: str | None,
    *,
    supported: Collection[str] | None = None,
    default: str = "en",
) -> str:
    """Return a normalized language code constrained to ``supported`` values."""

    if not default:
        msg = "default language must be a non-empty string"
        raise ValueError(msg)

    if not language:
        return default

    normalized = str(language).replace("_", "-").split("-", 1)[0].strip().lower()
    if not normalized:
        return default

    if supported is None:
        return normalized

    if normalized in supported:
        return normalized

    return default
