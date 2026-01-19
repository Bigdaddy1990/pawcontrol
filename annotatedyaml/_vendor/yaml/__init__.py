"""Minimal vendored YAML parser for test fallbacks."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any


class FullLoader:
  """Placeholder loader type for compatibility."""


class SafeLoader(FullLoader):
  """Placeholder safe loader type."""


class UnsafeLoader(FullLoader):
  """Placeholder unsafe loader type."""


class Dumper:
  """Placeholder dumper type."""


def _validate_brackets(value: str) -> None:
  if value.count("[") != value.count("]") or value.count("{") != value.count("}"):
    raise ValueError("Invalid YAML content")


def _parse_mapping(content: str) -> dict[str, Any]:
  result: dict[str, Any] = {}
  for raw_line in content.splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or line == "---":
      continue
    if ":" not in line:
      raise ValueError("Invalid YAML content")
    key, value = line.split(":", 1)
    key = key.strip()
    value = value.strip()
    if not key:
      raise ValueError("Invalid YAML content")
    _validate_brackets(value)
    if value.isdigit():
      result[key] = int(value)
    else:
      result[key] = value
  return result


def _split_documents(content: str) -> list[str]:
  if "---" not in content:
    return [content]
  docs = []
  current: list[str] = []
  for line in content.splitlines():
    if line.strip() == "---":
      if current:
        docs.append("\n".join(current))
        current = []
      continue
    current.append(line)
  if current:
    docs.append("\n".join(current))
  return docs


def _extract_legacy_loader(func_name: str, kwargs: dict[str, Any]) -> type | None:
  if "Loader" not in kwargs:
    return None
  if len(kwargs) > 1:
    unexpected = next(key for key in kwargs if key != "Loader")
    raise TypeError(f"{func_name}() got unexpected keyword argument '{unexpected}'")
  return kwargs.pop("Loader")


def _select_loader(
  func_name: str,
  *,
  loader_cls: type | None,
  legacy_loader: type | None,
  default_loader: type | None = None,
  required: bool = False,
) -> type | None:
  if loader_cls is not None and legacy_loader is not None:
    raise TypeError(f"{func_name}() received both 'Loader' and its replacement")
  if loader_cls is None and legacy_loader is None:
    if required and default_loader is None:
      raise TypeError(f"{func_name}() missing 1 required positional argument: 'Loader'")
    return default_loader
  return loader_cls or legacy_loader


def load(stream: str, loader_cls: type | None = None, **kwargs: Any) -> dict[str, Any]:
  legacy_loader = _extract_legacy_loader("load", kwargs)
  loader = _select_loader(
    "load",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    required=True,
  )
  _ = loader
  return _parse_mapping(stream)


def load_all(
  stream: str, loader_cls: type | None = None, **kwargs: Any
) -> Generator[dict[str, Any]]:
  legacy_loader = _extract_legacy_loader("load_all", kwargs)
  loader = _select_loader(
    "load_all",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    required=True,
  )
  _ = loader
  for doc in _split_documents(stream):
    yield _parse_mapping(doc)


def safe_load(
  stream: str, loader_cls: type | None = None, **kwargs: Any
) -> dict[str, Any]:
  legacy_loader = _extract_legacy_loader("safe_load", kwargs)
  loader = _select_loader(
    "safe_load",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    default_loader=SafeLoader,
  )
  if loader is not None and not issubclass(loader, SafeLoader):
    raise ValueError("safe_load() custom Loader must be a subclass")
  return _parse_mapping(stream)


def safe_load_all(
  stream: str, loader_cls: type | None = None, **kwargs: Any
) -> Generator[dict[str, Any]]:
  legacy_loader = _extract_legacy_loader("safe_load_all", kwargs)
  loader = _select_loader(
    "safe_load_all",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    default_loader=SafeLoader,
  )
  if loader is not None and not issubclass(loader, SafeLoader):
    raise ValueError("safe_load_all() custom Loader must be a subclass")
  for doc in _split_documents(stream):
    yield _parse_mapping(doc)


def dump(data: dict[str, Any], *_args: Any, **_kwargs: Any) -> str:
  return "\n".join(f"{key}: {value}" for key, value in data.items())


__all__ = [
  "Dumper",
  "FullLoader",
  "SafeLoader",
  "UnsafeLoader",
  "_extract_legacy_loader",
  "_select_loader",
  "dump",
  "load",
  "load_all",
  "safe_load",
  "safe_load_all",
]
