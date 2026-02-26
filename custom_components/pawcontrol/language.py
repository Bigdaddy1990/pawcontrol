"""Language normalization helpers for PawControl translations."""

from collections.abc import Collection

__all__ = ["normalize_language"]


def _normalize_code(value: str | None) -> str:
    """Normalize a language code to its lowercase base language."""
    if value is None:
        return ""

    return (
        str(value)
        .replace(
            "_",
            "-",
        )
        .split("-", 1)[0]
        .strip()
        .lower()
    )


def normalize_language(
    language: str | None,
    *,
    supported: Collection[str] | None = None,
    default: str = "en",
) -> str:
    """Return a normalized language code constrained to ``supported`` values."""
    if default == "":
        msg = "default language must be a non-empty string"
        raise ValueError(msg)

    if isinstance(default, str) and not default.strip():
        normalized_default = default
    else:
        normalized_default = _normalize_code(default)
    if not normalized_default:
        msg = "default language must be a non-empty string"
        raise ValueError(msg)

    if not language:
        return normalized_default

    normalized = _normalize_code(language)
    if not normalized:
        return normalized_default

    if supported is None:
        return normalized

    normalized_supported = {_normalize_code(code) for code in supported}
    normalized_supported.discard("")

    if normalized in normalized_supported:
        return normalized

    return normalized_default
