"""Tiny YAML loader shim compatible with the local regression tests."""

from __future__ import annotations

from pathlib import Path

try:
    from yaml import safe_load
except ModuleNotFoundError:  # pragma: no cover - exercised in tests
    from ._vendor.yaml import safe_load  # type: ignore[no-redef]


def load_yaml(path: str) -> object:
    """Load YAML from ``path`` and convert parser errors to ``ValueError``."""
    content = Path(path).read_text(encoding="utf-8")
    try:
        data = safe_load(content)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    return {} if data is None else data
