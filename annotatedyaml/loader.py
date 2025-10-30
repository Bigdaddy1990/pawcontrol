"""Fallback ``annotatedyaml`` loader for local development environments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised in environments missing PyYAML
    from yaml import (  # type: ignore[import-untyped]  # TODO: PyYAML lacks type stubs
        YAMLError,
        safe_load,
    )
except ModuleNotFoundError as err:  # pragma: no cover - defensive
    raise RuntimeError(
        "PyYAML is required to use the annotatedyaml fallback loader"
    ) from err


def load_yaml(path: str, secrets: Any | None = None) -> Any:
    """Load YAML content from ``path`` using ``PyYAML`` as a stub implementation."""

    del secrets  # ``annotatedyaml`` exposes this argument but the stub ignores it.

    yaml_path = Path(path)
    try:
        contents = yaml_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as err:  # pragma: no cover - defensive for unreadable files
        raise RuntimeError(f"Unable to read YAML file: {path}") from err

    if not contents.strip():
        return {}

    try:
        document = safe_load(contents)
    except YAMLError as err:
        raise ValueError(f"Invalid YAML in {path}") from err

    if document is None:
        return {}

    return document


__all__ = ["load_yaml"]
