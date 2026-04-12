"""Lightweight voluptuous compatibility shim for dependency-light test runs."""

from collections.abc import Callable, Mapping
from typing import Any as AnyType

UNDEFINED = object()
ALLOW_EXTRA = object()


class Invalid(Exception):
    """Validation error compatible with voluptuous.Invalid."""


class _ErrorModule:
    Invalid = Invalid


error = _ErrorModule()


class Marker:
    """Marker wrapper used by Schema definitions."""

    def __init__(self, schema: AnyType, default: AnyType = UNDEFINED) -> None:
        """Store wrapped schema metadata and resolve default provider."""
        self.schema = schema
        if default is UNDEFINED:
            self.default = lambda: UNDEFINED
        elif callable(default):
            self.default = default
        else:
            self.default = lambda default=default: default

    def __hash__(self) -> int:
        """Return a stable hash for marker identity checks."""
        return hash((self.schema, id(self.default)))


class Optional(Marker):
    """Optional marker."""


class Required(Marker):
    """Required marker."""


def Coerce(target_type: type[AnyType]) -> Callable[[AnyType], AnyType]:
    """Return a validator that coerces incoming values to ``target_type``."""

    def _coerce(value: AnyType) -> AnyType:
        return target_type(value)

    return _coerce


def In(
    options: Mapping[AnyType, AnyType]
    | list[AnyType]
    | tuple[AnyType, ...]
    | set[AnyType],
) -> Callable[[AnyType], AnyType]:
    """Return a validator that accepts only configured options."""

    def _validate(value: AnyType) -> AnyType:
        if value in options:
            return value
        raise Invalid(f"value {value!r} not in allowed options")

    return _validate


def Any(*validators: AnyType) -> Callable[[AnyType], AnyType]:
    """Return a validator that accepts first matching validator/value."""

    def _validate(value: AnyType) -> AnyType:
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


def All(*validators: AnyType) -> Callable[[AnyType], AnyType]:
    """Return a validator that runs validators in sequence."""

    def _validate(value: AnyType) -> AnyType:
        current = value
        for validator in validators:
            if callable(validator):
                current = validator(current)
        return current

    return _validate


def Range(
    *, min: float | int | None = None, max: float | int | None = None
) -> Callable[[AnyType], AnyType]:
    """Return a validator that enforces optional min/max boundaries."""

    def _validate(value: AnyType) -> AnyType:
        if min is not None and value < min:
            raise Invalid(f"value {value!r} is below minimum {min}")
        if max is not None and value > max:
            raise Invalid(f"value {value!r} is above maximum {max}")
        return value

    return _validate


class Schema:
    """Minimal schema wrapper used by tests."""

    def __init__(self, schema: AnyType, extra: AnyType | None = None) -> None:
        """Store schema configuration for later validation calls."""
        self.schema = schema
        self.extra = extra

    def __call__(self, value: AnyType) -> AnyType:
        """Return values unchanged in the lightweight compatibility shim."""
        return value

    def extend(self, schema: Mapping[AnyType, AnyType]) -> Schema:
        """Return a new schema containing the merged mapping definition."""
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
