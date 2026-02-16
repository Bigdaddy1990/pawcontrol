"""Minimal vendored YAML parser for test fallbacks."""

from __future__ import annotations

import ast
from collections.abc import Generator
import contextlib
import json
from typing import Any


class FullLoader:
  """Placeholder loader type for compatibility."""  # noqa: E111


class SafeLoader(FullLoader):
  """Placeholder safe loader type."""  # noqa: E111


class UnsafeLoader(FullLoader):
  """Placeholder unsafe loader type."""  # noqa: E111


class Dumper:
  """Placeholder dumper type."""  # noqa: E111


def _strip_inline_comment(line: str) -> str:
  in_single = False  # noqa: E111
  in_double = False  # noqa: E111
  for index, char in enumerate(line):  # noqa: E111
    if char == "'" and not in_double:
      in_single = not in_single  # noqa: E111
    elif char == '"' and not in_single:
      in_double = not in_double  # noqa: E111
    elif char == "#" and not in_single and not in_double:
      return line[:index].rstrip()  # noqa: E111
  return line.rstrip()  # noqa: E111


def _parse_scalar(value: str) -> Any:
  text = value.strip()  # noqa: E111
  if text in {"", "~", "null", "Null", "NULL", "none", "None"}:  # noqa: E111
    return None
  lowered = text.lower()  # noqa: E111
  if lowered == "true":  # noqa: E111
    return True
  if lowered == "false":  # noqa: E111
    return False
  if (text.startswith('"') and text.endswith('"')) or (  # noqa: E111
    text.startswith("'") and text.endswith("'")
  ):
    return text[1:-1]
  with contextlib.suppress(ValueError):  # noqa: E111
    if "." in text:
      return float(text)  # noqa: E111
    return int(text)
  with contextlib.suppress(json.JSONDecodeError, ValueError, SyntaxError):  # noqa: E111
    return json.loads(text)
  with contextlib.suppress(ValueError, SyntaxError):  # noqa: E111
    return ast.literal_eval(text)
  return text  # noqa: E111


def _next_content_indent(lines: list[str], start: int) -> int | None:
  for index in range(start, len(lines)):  # noqa: E111
    line = lines[index]
    if not line.strip() or line.strip() == "---":
      continue  # noqa: E111
    return len(line) - len(line.lstrip(" "))
  return None  # noqa: E111


def _parse_block_scalar(
  lines: list[str],
  start: int,
  indent: int,
  style: str,
) -> tuple[str, int]:
  parts: list[str] = []  # noqa: E111
  index = start  # noqa: E111
  while index < len(lines):  # noqa: E111
    line = lines[index]
    if not line.strip():
      parts.append("")  # noqa: E111
      index += 1  # noqa: E111
      continue  # noqa: E111
    current_indent = len(line) - len(line.lstrip(" "))
    if current_indent < indent:
      break  # noqa: E111
    parts.append(line[indent:])
    index += 1
  if style == ">":  # noqa: E111
    return " ".join(part.strip() for part in parts).strip(), index
  return "\n".join(parts).rstrip(), index  # noqa: E111


def _parse_block(
  lines: list[str],
  start: int,
  indent: int,
) -> tuple[Any, int]:
  container: Any | None = None  # noqa: E111
  index = start  # noqa: E111
  while index < len(lines):  # noqa: E111
    line = lines[index]
    if not line.strip() or line.strip() == "---":
      index += 1  # noqa: E111
      continue  # noqa: E111
    current_indent = len(line) - len(line.lstrip(" "))
    if current_indent < indent:
      break  # noqa: E111
    if current_indent > indent:
      raise ValueError("Invalid YAML indentation")  # noqa: E111
    stripped = line.strip()
    if stripped.startswith("-"):
      if container is None:  # noqa: E111
        container = []
      if not isinstance(container, list):  # noqa: E111
        raise ValueError("Invalid YAML content")
      item_text = stripped[1:].lstrip()  # noqa: E111
      if not item_text:  # noqa: E111
        next_indent = _next_content_indent(lines, index + 1)
        if next_indent is None or next_indent <= indent:
          container.append(None)  # noqa: E111
          index += 1  # noqa: E111
        else:
          value, index = _parse_block(lines, index + 1, indent + 2)  # noqa: E111
          container.append(value)  # noqa: E111
        continue
      if item_text in {"|", ">"}:  # noqa: E111
        value, index = _parse_block_scalar(lines, index + 1, indent + 2, item_text)
        container.append(value)
        continue
      if ":" in item_text:  # noqa: E111
        key, rest = item_text.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        if not key:
          raise ValueError("Invalid YAML content")  # noqa: E111
        if rest in {"|", ">"}:
          value, index = _parse_block_scalar(lines, index + 1, indent + 2, rest)  # noqa: E111
          container.append({key: value})  # noqa: E111
        elif rest:
          container.append({key: _parse_scalar(rest)})  # noqa: E111
          index += 1  # noqa: E111
        else:
          next_indent = _next_content_indent(lines, index + 1)  # noqa: E111
          if next_indent is None or next_indent <= indent:  # noqa: E111
            container.append({key: None})
            index += 1
          else:  # noqa: E111
            value, index = _parse_block(lines, index + 1, indent + 2)
            container.append({key: value})
        continue
      container.append(_parse_scalar(item_text))  # noqa: E111
      index += 1  # noqa: E111
      continue  # noqa: E111

    if container is None:
      container = {}  # noqa: E111
    if not isinstance(container, dict):
      raise ValueError("Invalid YAML content")  # noqa: E111
    if ":" not in stripped:
      raise ValueError("Invalid YAML content")  # noqa: E111
    key, rest = stripped.split(":", 1)
    key = key.strip()
    rest = rest.strip()
    if not key:
      raise ValueError("Invalid YAML content")  # noqa: E111
    if rest in {"|", ">"}:
      value, index = _parse_block_scalar(lines, index + 1, indent + 2, rest)  # noqa: E111
      container[key] = value  # noqa: E111
    elif rest:
      container[key] = _parse_scalar(rest)  # noqa: E111
      index += 1  # noqa: E111
    else:
      next_indent = _next_content_indent(lines, index + 1)  # noqa: E111
      if next_indent is None or next_indent <= indent:  # noqa: E111
        container[key] = None
        index += 1
      else:  # noqa: E111
        value, index = _parse_block(lines, index + 1, indent + 2)
        container[key] = value
  if container is None:  # noqa: E111
    return {}, index
  return container, index  # noqa: E111


def _parse_mapping(content: str) -> Any:
  lines: list[str] = []  # noqa: E111
  for raw_line in content.splitlines():  # noqa: E111
    stripped = _strip_inline_comment(raw_line)
    if stripped:
      lines.append(stripped)  # noqa: E111
    else:
      lines.append("")  # noqa: E111
  parsed, _ = _parse_block(lines, 0, 0)  # noqa: E111
  return parsed  # noqa: E111


def _split_documents(content: str) -> list[str]:
  if "---" not in content:  # noqa: E111
    return [content]
  docs = []  # noqa: E111
  current: list[str] = []  # noqa: E111
  for line in content.splitlines():  # noqa: E111
    if line.strip() == "---":
      if current:  # noqa: E111
        docs.append("\n".join(current))
        current = []
      continue  # noqa: E111
    current.append(line)
  if current:  # noqa: E111
    docs.append("\n".join(current))
  return docs  # noqa: E111


def _extract_legacy_loader(func_name: str, kwargs: dict[str, Any]) -> type | None:
  if "Loader" not in kwargs:  # noqa: E111
    return None
  if len(kwargs) > 1:  # noqa: E111
    unexpected = next(key for key in kwargs if key != "Loader")
    raise TypeError(f"{func_name}() got unexpected keyword argument '{unexpected}'")
  return kwargs.pop("Loader")  # noqa: E111


def _select_loader(
  func_name: str,
  *,
  loader_cls: type | None,
  legacy_loader: type | None,
  default_loader: type | None = None,
  required: bool = False,
) -> type | None:
  if loader_cls is not None and legacy_loader is not None:  # noqa: E111
    raise TypeError(f"{func_name}() received both 'Loader' and its replacement")
  if loader_cls is None and legacy_loader is None:  # noqa: E111
    if required and default_loader is None:
      raise TypeError(f"{func_name}() missing 1 required positional argument: 'Loader'")  # noqa: E111
    return default_loader
  return loader_cls or legacy_loader  # noqa: E111


def load(stream: str, loader_cls: type | None = None, **kwargs: Any) -> Any:
  legacy_loader = _extract_legacy_loader("load", kwargs)  # noqa: E111
  loader = _select_loader(  # noqa: E111
    "load",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    required=True,
  )
  _ = loader  # noqa: E111
  return _parse_mapping(stream)  # noqa: E111


def load_all(
  stream: str, loader_cls: type | None = None, **kwargs: Any
) -> Generator[Any]:
  legacy_loader = _extract_legacy_loader("load_all", kwargs)  # noqa: E111
  loader = _select_loader(  # noqa: E111
    "load_all",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    required=True,
  )
  _ = loader  # noqa: E111
  for doc in _split_documents(stream):  # noqa: E111
    yield _parse_mapping(doc)


def safe_load(stream: str, loader_cls: type | None = None, **kwargs: Any) -> Any:
  legacy_loader = _extract_legacy_loader("safe_load", kwargs)  # noqa: E111
  loader = _select_loader(  # noqa: E111
    "safe_load",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    default_loader=SafeLoader,
  )
  if loader is not None and not issubclass(loader, SafeLoader):  # noqa: E111
    raise ValueError("safe_load() custom Loader must be a subclass")
  return _parse_mapping(stream)  # noqa: E111


def safe_load_all(
  stream: str, loader_cls: type | None = None, **kwargs: Any
) -> Generator[Any]:
  legacy_loader = _extract_legacy_loader("safe_load_all", kwargs)  # noqa: E111
  loader = _select_loader(  # noqa: E111
    "safe_load_all",
    loader_cls=loader_cls,
    legacy_loader=legacy_loader,
    default_loader=SafeLoader,
  )
  if loader is not None and not issubclass(loader, SafeLoader):  # noqa: E111
    raise ValueError("safe_load_all() custom Loader must be a subclass")
  for doc in _split_documents(stream):  # noqa: E111
    yield _parse_mapping(doc)


def dump(data: dict[str, Any], *_args: Any, **_kwargs: Any) -> str:
  return "\n".join(f"{key}: {value}" for key, value in data.items())  # noqa: E111


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
