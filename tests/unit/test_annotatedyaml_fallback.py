"""Tests for the local ``annotatedyaml`` fallback loader."""

from __future__ import annotations

import importlib
import importlib.machinery
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
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
def _force_stub_loader() -> Iterator[None]:
    """Prevent the vendored package from loading so the stub executes."""

    original_find_spec = importlib.machinery.PathFinder.find_spec

    def _guard(
        fullname: str, path: list[str] | None = None, target: object | None = None
    ):
        if fullname == "annotatedyaml" and path is not None:
            return None
        return original_find_spec(fullname, path, target)

    with patch("importlib.machinery.PathFinder.find_spec", side_effect=_guard):
        yield


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


def test_fallback_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
    """Invalid YAML surfaces a ``ValueError`` so callers receive actionable errors."""

    with _force_stub_loader(), _isolated_import("annotatedyaml"):
        module = importlib.import_module("annotatedyaml")
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("bad: [unterminated\n", encoding="utf-8")

        with pytest.raises(ValueError):
            module.load_yaml(str(yaml_path))  # type: ignore[attr-defined]
