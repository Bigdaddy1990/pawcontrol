"""Lightweight voluptuous compatibility shim for dependency-light test runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

UNDEFINED = object()
ALLOW_EXTRA = object()


class Invalid(Exception):
    """Validation error compatible with voluptuous.Invalid."""


class _ErrorModule:
    Invalid = Invalid


error = _ErrorModule()


class Marker:
    """Marker wrapper used by Schema definitions."""

    def __init__(self, schema: Any, default: Any = UNDEFINED) -> None:
        self.schema = schema
        if default is UNDEFINED:
            self.default = lambda: UNDEFINED
        elif callable(default):
            self.default = default
        else:
            self.default = lambda default=default: default

    def __hash__(self) -> int:
        return hash((self.schema, id(self.default)))


class Optional(Marker):
    """Optional marker."""


class Required(Marker):
    """Required marker."""


def Coerce(target_type: type[Any]) -> Callable[[Any], Any]:
    def _coerce(value: Any) -> Any:
        return target_type(value)

    return _coerce


def In(options: Mapping[Any, Any] | list[Any] | tuple[Any, ...] | set[Any]) -> Callable[[Any], Any]:
    def _validate(value: Any) -> Any:
        if value in options:
            return value
        raise Invalid(f"value {value!r} not in allowed options")

    return _validate


def Any(*validators: Any) -> Callable[[Any], Any]:
    def _validate(value: Any) -> Any:
        for validator in validators:
            try:
                if callable(validator):
                    return validator(value)
                if value == validator:
                    return value
            except Exception:
                continue
        return value

    return _validate


def All(*validators: Any) -> Callable[[Any], Any]:
    def _validate(value: Any) -> Any:
        current = value
        for validator in validators:
            if callable(validator):
                current = validator(current)
        return current

    return _validate


def Range(*, min: float | int | None = None, max: float | int | None = None) -> Callable[[Any], Any]:
    def _validate(value: Any) -> Any:
        if min is not None and value < min:
            raise Invalid(f"value {value!r} is below minimum {min}")
        if max is not None and value > max:
            raise Invalid(f"value {value!r} is above maximum {max}")
        return value

    return _validate


class Schema:
    def __init__(self, schema: Any, extra: Any | None = None) -> None:
        self.schema = schema
        self.extra = extra

    def __call__(self, value: Any) -> Any:
        return value

    def extend(self, schema: Mapping[Any, Any]) -> Schema:
        if isinstance(self.schema, Mapping):
            merged = dict(self.schema)
            merged.update(schema)
            return Schema(merged, extra=self.extra)
        return Schema(schema, extra=self.extra)


__all__ = [
    "ALLOW_EXTRA",
    "All",
    "Any",
    "Coerce",
    "In",
    "Invalid",
    "Marker",
    "Optional",
    "Range",
    "Required",
    "Schema",
    "UNDEFINED",
    "error",
]
