"""Tiny hypothesis compatibility layer for import-time usage in tests."""

from collections.abc import Callable
from typing import Any


class HealthCheck:
    function_scoped_fixture = "function_scoped_fixture"
    too_slow = "too_slow"
    filter_too_much = "filter_too_much"


class _Strategy:
    def __or__(self, _other: object) -> _Strategy:
        return self

    def map(self, _func: Callable[[Any], Any]) -> _Strategy:
        return self

    def filter(self, _func: Callable[[Any], bool]) -> _Strategy:
        return self


def given(
    *_strategies: Any, **_kwargs: Any
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    return _decorator


class _Settings:
    _profiles: dict[str, object] = {}

    def __call__(
        self, *_args: Any, **_kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return _decorator

    def register_profile(self, name: str, value: object) -> None:
        self._profiles[name] = value

    def load_profile(self, _name: str) -> None:
        return None


settings = _Settings()


class _Strategies:
    def __getattr__(self, _name: str) -> Callable[..., _Strategy]:
        return lambda *args, **kwargs: _Strategy()

    def composite(self, function: Callable[..., Any]) -> Callable[..., _Strategy]:
        def _wrapper(*args: Any, **kwargs: Any) -> _Strategy:
            return _Strategy()

        return _wrapper


strategies = _Strategies()
st = strategies

__all__ = ["HealthCheck", "given", "settings", "strategies", "st"]
