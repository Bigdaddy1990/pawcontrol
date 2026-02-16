"""Fallback YAML loader used in the test environment."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_yaml_spec = importlib.util.find_spec("yaml")
if _yaml_spec is not None:
  yaml = importlib.import_module("yaml")  # noqa: E111
else:
  from annotatedyaml._vendor import yaml  # type: ignore[assignment]  # noqa: E111


safe_load = yaml.safe_load


def load_yaml(path: str) -> dict[str, Any]:
  """Load a YAML file and return the parsed mapping."""  # noqa: E111

  payload = Path(path).read_text(encoding="utf-8")  # noqa: E111
  try:  # noqa: E111
    return safe_load(payload)
  except Exception as err:  # noqa: E111
    raise ValueError("Invalid YAML content") from err


__all__ = ["load_yaml", "safe_load"]
