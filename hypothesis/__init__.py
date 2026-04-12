"""Tiny hypothesis compatibility layer for import-time usage in tests."""

from collections.abc import Callable
from typing import Any


class HealthCheck:
    function_scoped_fixture = "function_scoped_fixture"
    differing_executors = "differing_executors"
    too_slow = "too_slow"
    filter_too_much = "filter_too_much"


class Verbosity:
    quiet = 0
    normal = 1
    verbose = 2
    debug = 3


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
            return func

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
    explain = "explain"


class _CoreCompat:
    global_force_seed: Any = None
    pytest_shows_exceptiongroups = False
    running_under_pytest = False


core = _CoreCompat()


class _Strategies:
    def __getattr__(self, _name: str) -> Callable[..., _Strategy]:
        return lambda *args, **kwargs: _Strategy()

    def composite(self, function: Callable[..., Any]) -> Callable[..., _Strategy]:
        def _wrapper(*args: Any, **kwargs: Any) -> _Strategy:
            return _Strategy()

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
