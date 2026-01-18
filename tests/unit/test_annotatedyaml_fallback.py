"""Tests for the local ``annotatedyaml`` fallback loader."""

from __future__ import annotations

import builtins
import importlib
import importlib.machinery
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


@contextmanager
def _isolated_import(module_name: str) -> Iterator[None]:
  """Temporarily replace ``module_name`` with a fresh import."""

  existing = {
    key: value
    for key, value in sys.modules.items()
    if key == module_name or key.startswith(f"{module_name}.")
  }

  for key in existing:
    del sys.modules[key]

  try:
    yield
  finally:
    for key in list(sys.modules):
      if key == module_name or key.startswith(f"{module_name}."):
        del sys.modules[key]
    sys.modules.update(existing)


@contextmanager
def _force_stub_loader(
  *, blocked_modules: tuple[str, ...] = ("annotatedyaml",)
) -> Iterator[None]:
  """Prevent specified modules from resolving so the stub executes."""

  original_find_spec = importlib.machinery.PathFinder.find_spec

  def _guard(
    fullname: str, path: list[str] | None = None, target: object | None = None
  ):
    for module in blocked_modules:
      if fullname == module and path is not None:
        return None
    return original_find_spec(fullname, path, target)

  with patch("importlib.machinery.PathFinder.find_spec", side_effect=_guard):
    yield


@contextmanager
def _hide_modules(*module_names: str) -> Iterator[None]:
  """Temporarily remove modules from ``sys.modules`` and block re-imports."""

  removed: dict[str, ModuleType] = {}
  for module in module_names:
    for key in list(sys.modules):
      if key == module or key.startswith(f"{module}."):
        removed[key] = sys.modules.pop(key)

  original_import = builtins.__import__

  def _guard(
    name: str,
    globals: dict[str, object] | None = None,
    locals: dict[str, object] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
  ) -> ModuleType:
    for module in module_names:
      if name == module or name.startswith(f"{module}."):
        raise ModuleNotFoundError(name)
    return original_import(name, globals, locals, fromlist, level)

  try:
    builtins.__import__ = _guard  # type: ignore[assignment]
    yield
  finally:
    builtins.__import__ = original_import  # type: ignore[assignment]
    sys.modules.update(removed)


def test_fallback_loader_exposes_stub_module(tmp_path: Path) -> None:
  """The repository fallback exposes ``load_yaml`` from the stub loader."""

  with _force_stub_loader(), _isolated_import("annotatedyaml"):
    module = importlib.import_module("annotatedyaml")

    assert hasattr(module, "load_yaml"), "Stub should expose ``load_yaml``"

    stub_loader = importlib.import_module("annotatedyaml.loader")
    assert module.load_yaml is stub_loader.load_yaml  # type: ignore[attr-defined]

    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("key: value\n", encoding="utf-8")
    assert module.load_yaml(str(yaml_path)) == {"key": "value"}  # type: ignore[attr-defined]


def test_fallback_loader_uses_vendored_yaml(tmp_path: Path) -> None:
  """When system PyYAML is missing the vendored copy provides ``safe_load``."""

  if importlib.util.find_spec("annotatedyaml._vendor.yaml") is None:
    pytest.skip("annotatedyaml does not vendor PyYAML in this environment")

  with (
    _hide_modules("yaml"),
    _force_stub_loader(blocked_modules=("annotatedyaml", "yaml")),
    _isolated_import("annotatedyaml"),
  ):
    module = importlib.import_module("annotatedyaml")
    stub_loader = importlib.import_module("annotatedyaml.loader")

    safe_load = stub_loader.safe_load  # type: ignore[attr-defined]
    assert safe_load.__module__.startswith("annotatedyaml._vendor.yaml")

    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("key: vendored\n", encoding="utf-8")

    assert module.load_yaml(str(yaml_path)) == {"key": "vendored"}  # type: ignore[attr-defined]


def test_fallback_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
  """Invalid YAML surfaces a ``ValueError`` so callers receive actionable errors."""

  with _force_stub_loader(), _isolated_import("annotatedyaml"):
    module = importlib.import_module("annotatedyaml")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("bad: [unterminated\n", encoding="utf-8")

    with pytest.raises(ValueError):
      module.load_yaml(str(yaml_path))  # type: ignore[attr-defined]
