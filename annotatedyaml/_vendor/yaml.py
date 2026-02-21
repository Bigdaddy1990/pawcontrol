"""Vendored YAML adapter compatible with annotatedyaml regression tests."""

from collections.abc import Iterator
from typing import Any

try:
    import yaml as _pyyaml
except ModuleNotFoundError:  # pragma: no cover
    _pyyaml = None


if _pyyaml is not None:
    __version__ = getattr(_pyyaml, "__version__", "0")
    FullLoader = _pyyaml.FullLoader
    SafeLoader = _pyyaml.SafeLoader
    UnsafeLoader = getattr(_pyyaml, "UnsafeLoader", _pyyaml.FullLoader)
    Dumper = _pyyaml.Dumper
else:  # pragma: no cover - exercised when yaml is hidden
    __version__ = "0"

    class _PyYamlMissing:
        """Base class that fails fast when PyYAML-dependent classes are used."""

        _class_name = "PyYAML helper"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                f"PyYAML is not installed, cannot use {self._class_name}"
            )

    class FullLoader(_PyYamlMissing):
        _class_name = "FullLoader"

    class SafeLoader(FullLoader):
        _class_name = "SafeLoader"

    class UnsafeLoader(FullLoader):
        _class_name = "UnsafeLoader"

    class Dumper(_PyYamlMissing):
        _class_name = "Dumper"


def _extract_legacy_loader(func_name: str, kwargs: dict[str, object]) -> object | None:
    legacy_loader = kwargs.pop("Loader", None)
    if kwargs:
        key = next(iter(kwargs))
        raise TypeError(f"{func_name}() got unexpected keyword argument '{key}'")
    return legacy_loader


def _select_loader(
    func_name: str,
    *,
    loader_cls: object | None,
    legacy_loader: object | None,
    required: bool = False,
    default_loader: object | None = None,
) -> object:
    if loader_cls is not None and legacy_loader is not None:
        raise TypeError(f"{func_name}() received both 'Loader' and its replacement")
    if loader_cls is not None:
        return loader_cls
    if legacy_loader is not None:
        return legacy_loader
    if default_loader is not None:
        return default_loader
    if required:
        raise TypeError(
            f"{func_name}() missing 1 required positional argument: 'Loader'"
        )
    return SafeLoader


def _simple_parse(doc: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for raw_line in doc.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Invalid YAML line: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and not value.endswith("]"):
            raise ValueError("Unterminated flow sequence")
        if value.isdigit():
            result[key] = int(value)
        else:
            result[key] = value
    return result


def load(stream: str, loader_cls: object | None = None, **kwargs: object) -> object:
    legacy_loader = _extract_legacy_loader("load", kwargs)
    selected_loader = _select_loader(
        "load", loader_cls=loader_cls, legacy_loader=legacy_loader, required=True
    )
    if _pyyaml is None:
        _ = selected_loader
        return _simple_parse(stream)
    return _pyyaml.load(stream, Loader=selected_loader)


def load_all(
    stream: str, loader_cls: object | None = None, **kwargs: object
) -> Iterator[object]:
    legacy_loader = _extract_legacy_loader("load_all", kwargs)
    selected_loader = _select_loader(
        "load_all", loader_cls=loader_cls, legacy_loader=legacy_loader, required=True
    )
    if _pyyaml is None:
        docs = [part for part in stream.split("---") if part.strip()]
        for doc in docs:
            yield _simple_parse(doc)
        return
    yield from _pyyaml.load_all(stream, Loader=selected_loader)


def safe_load(
    stream: str, loader_cls: object | None = None, **kwargs: object
) -> object:
    legacy_loader = _extract_legacy_loader("safe_load", kwargs)
    selected_loader = _select_loader(
        "safe_load",
        loader_cls=loader_cls,
        legacy_loader=legacy_loader,
        default_loader=SafeLoader,
    )
    if not isinstance(selected_loader, type) or not issubclass(
        selected_loader, SafeLoader
    ):
        raise ValueError("safe_load() custom Loader must be a subclass of SafeLoader")
    if _pyyaml is None:
        return _simple_parse(stream)
    return _pyyaml.load(stream, Loader=selected_loader)


def safe_load_all(
    stream: str, loader_cls: object | None = None, **kwargs: object
) -> Iterator[object]:
    legacy_loader = _extract_legacy_loader("safe_load_all", kwargs)
    selected_loader = _select_loader(
        "safe_load_all",
        loader_cls=loader_cls,
        legacy_loader=legacy_loader,
        default_loader=SafeLoader,
    )
    if not isinstance(selected_loader, type) or not issubclass(
        selected_loader, SafeLoader
    ):
        raise ValueError(
            "safe_load_all() custom Loader must be a subclass of SafeLoader"
        )
    if _pyyaml is None:
        docs = [part for part in stream.split("---") if part.strip()]
        for doc in docs:
            yield _simple_parse(doc)
        return
    yield from _pyyaml.load_all(stream, Loader=selected_loader)


def dump(data: object, dumper_cls: object | None = None, **kwargs: object) -> str:
    legacy_dumper = kwargs.pop("Dumper", None)
    if kwargs:
        key = next(iter(kwargs))
        raise TypeError(f"dump() got unexpected keyword argument '{key}'")
    if dumper_cls is not None and legacy_dumper is not None:
        raise TypeError("dump() received both 'Dumper' and its replacement")
    selected_dumper = dumper_cls or legacy_dumper or globals()["Dumper"]
    if _pyyaml is None:
        if isinstance(data, dict):
            return "\n".join(f"{k}: {v}" for k, v in data.items()) + "\n"
        return f"{data}\n"
    return _pyyaml.dump(data, Dumper=selected_dumper)


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
