"""Tiny YAML loader shim compatible with the local regression tests."""

from pathlib import Path

try:
    import yaml as _pyyaml
    from yaml import safe_load
except ModuleNotFoundError:  # pragma: no cover - exercised in tests
    _pyyaml = None
    from ._vendor.yaml import safe_load  # type: ignore[no-redef]


def load_yaml(path: str) -> object:
    """Load YAML from ``path`` and convert parser errors to ``ValueError``."""
    content = Path(path).read_text(encoding="utf-8")
    try:
        data = safe_load(content)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    except TypeError as exc:
        raise ValueError(str(exc)) from exc
    except _pyyaml.YAMLError as exc:  # type: ignore[union-attr]
        raise ValueError(str(exc)) from exc
    return {} if data is None else data
