"""Minimal vendored YAML parser for test fallbacks."""

from __future__ import annotations

import ast
import contextlib
import json
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


def _strip_inline_comment(line: str) -> str:
  in_single = False
  in_double = False
  for index, char in enumerate(line):
    if char == "'" and not in_double:
      in_single = not in_single
    elif char == '"' and not in_single:
      in_double = not in_double
    elif char == "#" and not in_single and not in_double:
      return line[:index].rstrip()
  return line.rstrip()


def _parse_scalar(value: str) -> Any:
  text = value.strip()
  if text in {"", "~", "null", "Null", "NULL", "none", "None"}:
    return None
  lowered = text.lower()
  if lowered == "true":
    return True
  if lowered == "false":
    return False
  if (text.startswith('"') and text.endswith('"')) or (
    text.startswith("'") and text.endswith("'")
  ):
    return text[1:-1]
  with contextlib.suppress(ValueError):
    if "." in text:
      return float(text)
    return int(text)
  if text.startswith("[") or text.startswith("{"):
    try:
      return json.loads(text)
    except (json.JSONDecodeError, ValueError, SyntaxError):
      try:
        return ast.literal_eval(text)
      except (ValueError, SyntaxError) as err:
        raise ValueError("Invalid YAML content") from err
  return text


def _next_content_indent(lines: list[str], start: int) -> int | None:
  for index in range(start, len(lines)):
    line = lines[index]
    if not line.strip() or line.strip() == "---":
      continue
    return len(line) - len(line.lstrip(" "))
  return None


def _parse_block_scalar(
  lines: list[str],
  start: int,
  indent: int,
  style: str,
) -> tuple[str, int]:
  parts: list[str] = []
  index = start
  while index < len(lines):
    line = lines[index]
    if not line.strip():
      parts.append("")
      index += 1
      continue
    current_indent = len(line) - len(line.lstrip(" "))
    if current_indent < indent:
      break
    parts.append(line[indent:])
    index += 1
  if style == ">":
    return " ".join(part.strip() for part in parts).strip(), index
  return "\n".join(parts).rstrip(), index


def _parse_block(
  lines: list[str],
  start: int,
  indent: int,
) -> tuple[Any, int]:
  container: Any | None = None
  index = start
  while index < len(lines):
    line = lines[index]
    if not line.strip() or line.strip() == "---":
      index += 1
      continue
    current_indent = len(line) - len(line.lstrip(" "))
    if current_indent < indent:
      break
    if current_indent > indent:
      raise ValueError("Invalid YAML indentation")
    stripped = line.strip()
    if stripped.startswith("-"):
      if container is None:
        container = []
      if not isinstance(container, list):
        raise ValueError("Invalid YAML content")
      item_text = stripped[1:].lstrip()
      if not item_text:
        next_indent = _next_content_indent(lines, index + 1)
        if next_indent is None or next_indent <= indent:
          container.append(None)
          index += 1
        else:
          value, index = _parse_block(lines, index + 1, indent + 2)
          container.append(value)
        continue
      if item_text in {"|", ">"}:
        value, index = _parse_block_scalar(lines, index + 1, indent + 2, item_text)
        container.append(value)
        continue
      if ":" in item_text:
        key, rest = item_text.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        if not key:
          raise ValueError("Invalid YAML content")
        if rest in {"|", ">"}:
          value, index = _parse_block_scalar(lines, index + 1, indent + 2, rest)
          container.append({key: value})
        elif rest:
          container.append({key: _parse_scalar(rest)})
          index += 1
        else:
          next_indent = _next_content_indent(lines, index + 1)
          if next_indent is None or next_indent <= indent:
            container.append({key: None})
            index += 1
          else:
            value, index = _parse_block(lines, index + 1, indent + 2)
            container.append({key: value})
        continue
      container.append(_parse_scalar(item_text))
      index += 1
      continue

    if container is None:
      container = {}
    if not isinstance(container, dict):
      raise ValueError("Invalid YAML content")
    if ":" not in stripped:
      raise ValueError("Invalid YAML content")
    key, rest = stripped.split(":", 1)
    key = key.strip()
    rest = rest.strip()
    if not key:
      raise ValueError("Invalid YAML content")
    if rest in {"|", ">"}:
      value, index = _parse_block_scalar(lines, index + 1, indent + 2, rest)
      container[key] = value
    elif rest:
      container[key] = _parse_scalar(rest)
      index += 1
    else:
      next_indent = _next_content_indent(lines, index + 1)
      if next_indent is None or next_indent <= indent:
        container[key] = None
        index += 1
      else:
        value, index = _parse_block(lines, index + 1, indent + 2)
        container[key] = value
  if container is None:
    return {}, index
  return container, index


def _parse_mapping(content: str) -> Any:
  lines: list[str] = []
  for raw_line in content.splitlines():
    stripped = _strip_inline_comment(raw_line)
    if stripped:
      lines.append(stripped)
    else:
      lines.append("")
  parsed, _ = _parse_block(lines, 0, 0)
  return parsed


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


def load(stream: str, loader_cls: type | None = None, **kwargs: Any) -> Any:
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
) -> Generator[Any]:
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


def safe_load(stream: str, loader_cls: type | None = None, **kwargs: Any) -> Any:
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
) -> Generator[Any]:
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
