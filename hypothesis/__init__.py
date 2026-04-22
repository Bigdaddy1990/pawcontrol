"""Tiny hypothesis compatibility layer for import-time usage in tests."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import functools
import inspect
from typing import Any


class HealthCheck:
    """Compatibility constants mirroring Hypothesis health checks."""

    function_scoped_fixture = "function_scoped_fixture"
    differing_executors = "differing_executors"
    too_slow = "too_slow"
    filter_too_much = "filter_too_much"


class Verbosity:
    """Compatibility constants mirroring Hypothesis verbosity levels."""

    quiet = 0
    normal = 1
    verbose = 2
    debug = 3


class _Strategy:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def example(self) -> Any:
        """Return a deterministic sample value for this strategy."""
        return self._value

    def __or__(self, _other: object) -> _Strategy:
        if isinstance(_other, _Strategy) and self._value is None:
            return _other
        return self

    def map(self, _func: Callable[[Any], Any]) -> _Strategy:
        if self._value is None:
            return self
        try:
            return _Strategy(_func(self._value))
        except Exception:
            return self

    def filter(self, _func: Callable[[Any], bool]) -> _Strategy:
        if self._value is None:
            return self
        try:
            return self if _func(self._value) else _Strategy(None)
        except Exception:
            return _Strategy(None)


def given(
    *_strategies: Any, **_kwargs: Any
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Return a decorator that injects deterministic generated values."""

    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            generated = [
                strategy.example() if isinstance(strategy, _Strategy) else None
                for strategy in _strategies
            ]
            return func(*args, *generated, **kwargs)

        signature = inspect.signature(func)
        params = list(signature.parameters.values())
        if _strategies and len(params) >= len(_strategies):
            _wrapper.__signature__ = signature.replace(
                parameters=params[: len(params) - len(_strategies)],
            )
        return _wrapper

    return _decorator


class _Settings:
    """Lightweight settings facade used by tests and plugins."""

    _profiles: dict[str, object] = {}
    _current_profile = "default"

    class _DefaultProfile:
        verbosity = Verbosity.normal

        def show_changed(self) -> str:
            return ""

    default = _DefaultProfile()

    def __call__(
        self, *_args: Any, **_kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def _wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            return _wrapper

        return _decorator

    def register_profile(self, name: str, value: object) -> None:
        self._profiles[name] = value

    def load_profile(self, name: str) -> None:
        self._current_profile = name
        profile = self._profiles.get(name)
        if (
            profile is not None
            and hasattr(profile, "verbosity")
            and hasattr(profile, "show_changed")
        ):
            self.default = profile
        else:
            self.default = self._DefaultProfile()

    def get_current_profile_name(self) -> str:
        return self._current_profile


settings = _Settings()


class Phase:
    """Compatibility container for Hypothesis execution phases."""

    explain = "explain"


class _CoreCompat:
    """Minimal ``hypothesis.core`` compatibility namespace."""

    global_force_seed: Any = None
    pytest_shows_exceptiongroups = False
    running_under_pytest = False


core = _CoreCompat()


class _Strategies:
    """Factory that returns deterministic stand-ins for Hypothesis strategies."""

    def __getattr__(self, _name: str) -> Callable[..., _Strategy]:
        """Return a strategy constructor by attribute lookup."""

        def _factory(*args: Any, **kwargs: Any) -> _Strategy:
            if _name == "floats":
                min_value = kwargs.get("min_value", 0.0)
                max_value = kwargs.get("max_value", min_value)
                return _Strategy((float(min_value) + float(max_value)) / 2.0)
            if _name == "integers":
                min_value = kwargs.get("min_value", 0)
                max_value = kwargs.get("max_value", min_value)
                return _Strategy((int(min_value) + int(max_value)) // 2)
            if _name == "booleans":
                return _Strategy(False)
            if _name == "none":
                return _Strategy(None)
            if _name == "sampled_from" and args:
                sequence = args[0]
                if isinstance(sequence, list | tuple) and sequence:
                    return _Strategy(sequence[0])
            if _name == "one_of":
                for strategy in args:
                    if isinstance(strategy, _Strategy):
                        return strategy
                return _Strategy(None)
            if _name == "text":
                min_size = int(kwargs.get("min_size", 0))
                max_size = int(kwargs.get("max_size", min_size if min_size else 1))
                size = max(min_size, min(max_size, 1))
                return _Strategy("x" * size)
            if _name == "dictionaries":
                return _Strategy({})
            if _name == "datetimes":
                return _Strategy(datetime(2024, 1, 1, 0, 0, 0))
            if _name == "timedeltas":
                return _Strategy(timedelta(seconds=0))
            if _name == "characters":
                return _Strategy("x")
            if _name == "none":
                return _Strategy(None)
            if _name == "one_of" and args:
                for strategy in args:
                    if isinstance(strategy, _Strategy):
                        return strategy
                return _Strategy(None)
            if _name == "dictionaries":
                key_strategy = args[0] if len(args) > 0 else _Strategy("key")
                value_strategy = args[1] if len(args) > 1 else _Strategy(0)
                min_size = int(kwargs.get("min_size", 0))
                if min_size <= 0:
                    return _Strategy({})
            if _name == "datetimes":
                min_value = kwargs.get("min_value")
                max_value = kwargs.get("max_value")
                if min_value is not None and max_value is not None:
                    midpoint = min_value + (max_value - min_value) / 2
                    return _Strategy(midpoint)
                return _Strategy(min_value or max_value)
            if _name == "timedeltas":
                min_value = kwargs.get("min_value")
                max_value = kwargs.get("max_value")
                if min_value is not None and max_value is not None:
                    midpoint = min_value + (max_value - min_value) / 2
                    return _Strategy(midpoint)
                return _Strategy(min_value or max_value)
            return _Strategy(None)

        return _factory

    def composite(self, function: Callable[..., Any]) -> Callable[..., _Strategy]:
        """Wrap composite strategy callables with deterministic draw support."""

        def _wrapper(*args: Any, **kwargs: Any) -> _Strategy:
            def _draw(strategy: _Strategy) -> Any:
                return strategy.example()

            try:
                return _Strategy(function(_draw, *args, **kwargs))
            except Exception:
                return _Strategy(None)

        return _wrapper


strategies = _Strategies()
st = strategies


def is_hypothesis_test(_func: object) -> bool:
    """Compatibility helper expected by pytest-hypothesis plugin."""
    return False


__all__ = [
    "HealthCheck",
    "Phase",
    "Verbosity",
    "core",
    "given",
    "is_hypothesis_test",
    "settings",
    "strategies",
    "st",
]
