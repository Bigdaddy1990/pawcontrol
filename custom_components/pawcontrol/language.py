"""Language normalization helpers for PawControl translations."""

from collections.abc import Collection

__all__ = ["normalize_language"]


def normalize_language(
  language: str | None,
  *,
  supported: Collection[str] | None = None,
  default: str = "en",
) -> str:
  """Return a normalized language code constrained to ``supported`` values."""  # noqa: E111

  if not default:  # noqa: E111
    msg = "default language must be a non-empty string"
    raise ValueError(msg)

  if not language:  # noqa: E111
    return default

  normalized = (  # noqa: E111
    str(language)
    .replace(
      "_",
      "-",
    )
    .split("-", 1)[0]
    .strip()
    .lower()
  )
  if not normalized:  # noqa: E111
    return default

  if supported is None:  # noqa: E111
    return normalized

  if normalized in supported:  # noqa: E111
    return normalized

  return default  # noqa: E111
