"""Runtime patches for compatibility with third-party dependencies.

This project runs on Python 3.13 during testing, but some third-party
packages that ship with the test suite still expect private helpers from
`uuid` that were removed in Python 3.13.  The Home Assistant test helper
`pytest-homeassistant-custom-component` depends on `freezegun`, which
tries to import ``uuid._uuid_generate_time`` and ``uuid._load_system_functions``.
Without shims the import fails before our tests even start.  We provide a
minimal, well-documented compatibility layer so that those modules can be
imported safely on modern Python versions.  The helpers delegate to the
public ``uuid._generate_time_safe`` implementation available since Python
3.8, keeping behaviour consistent with CPython's previous private APIs.
"""

from __future__ import annotations

import builtins
import inspect
import sys
import types
import uuid

if not hasattr(uuid, "_uuid_generate_time"):

    def _uuid_generate_time() -> bytes:
        """Return a time-based UUID byte sequence.

        This mirrors the return type of the legacy private CPython helper
        that `freezegun` expects.  ``uuid._generate_time_safe`` returns a
        tuple of ``(bytes, clock_seq)`` so we only expose the first element
        to match the historical API.
        """

        generated = uuid._generate_time_safe()  # type: ignore[attr-defined]
        # `_generate_time_safe` returns ``(bytes, clock_seq)``; the legacy
        # helper only returned the raw bytes payload used to build UUID1
        # instances.
        return generated[0]

    uuid._uuid_generate_time = _uuid_generate_time  # type: ignore[attr-defined]

if not hasattr(uuid, "_load_system_functions"):

    def _load_system_functions() -> None:
        """Compatibility no-op for removed CPython internals.

        Older versions of ``freezegun`` call this helper during import to
        populate the private ``_uuid_generate_time`` attribute.  Our shim
        ensures that attribute is available above, so the function simply
        verifies it exists.
        """

        if not hasattr(uuid, "_uuid_generate_time"):
            uuid._uuid_generate_time = _uuid_generate_time  # type: ignore[attr-defined]

    uuid._load_system_functions = _load_system_functions  # type: ignore[attr-defined]

# ``freezegun`` also checks for ``uuid._UuidCreate`` on Windows.  That
# attribute still exists on Python 3.13 when running on Windows, but the
# tests execute on Linux where it is missing.  The import only needs the
# attribute to exist so we provide a stub matching the old behaviour.
if not hasattr(uuid, "_UuidCreate"):
    uuid._UuidCreate = types.SimpleNamespace  # type: ignore[attr-defined]


def _patch_pytest_async_fixture() -> None:
    """Monkeypatch ``pytest.fixture`` to support async fixtures without warnings."""

    try:
        import asyncio
        import functools
        import pytest  # type: ignore
    except Exception:  # pragma: no cover - pytest not available outside tests
        return

    original_fixture = getattr(pytest, "fixture", None)
    if original_fixture is None:
        return

    if getattr(original_fixture, "__pawcontrol_async_patch__", False):
        return

    def _wrap_coroutine_fixture(func):
        @functools.wraps(func)
        def sync_wrapper(*args: object, **kwargs: object):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(func(*args, **kwargs))

        return sync_wrapper

    def async_aware_fixture(*fixture_args: object, **fixture_kwargs: object):
        if (
            fixture_args
            and len(fixture_args) == 1
            and callable(fixture_args[0])
            and not fixture_kwargs
        ):
            func = fixture_args[0]
            if inspect.iscoroutinefunction(func):
                return original_fixture(_wrap_coroutine_fixture(func))  # type: ignore[misc]
            return original_fixture(func)  # type: ignore[misc]

        def decorator(func):
            if inspect.iscoroutinefunction(func):
                return original_fixture(*fixture_args, **fixture_kwargs)(
                    _wrap_coroutine_fixture(func)
                )  # type: ignore[misc]
            return original_fixture(*fixture_args, **fixture_kwargs)(func)  # type: ignore[misc]

        return decorator

    async_aware_fixture.__pawcontrol_async_patch__ = True  # type: ignore[attr-defined]
    async_aware_fixture.__wrapped_fixture__ = original_fixture  # type: ignore[attr-defined]
    pytest.fixture = async_aware_fixture  # type: ignore[assignment]


_original_import = builtins.__import__


def _import_hook(
    name: str,
    globals: dict[str, object] | None = None,
    locals: dict[str, object] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
):
    """Intercept imports to patch pytest as soon as it loads."""

    module = _original_import(name, globals, locals, fromlist, level)

    if name == "pytest" or (name.startswith("pytest.") and "pytest" in sys.modules):
        _patch_pytest_async_fixture()

    return module


if not getattr(builtins, "__pawcontrol_import_patch__", False):
    builtins.__import__ = _import_hook  # type: ignore[assignment]
    builtins.__pawcontrol_import_patch__ = True  # type: ignore[attr-defined]


def _ensure_homeassistant_stubs() -> None:
    """Install Home Assistant compatibility shims before imports occur."""

    try:
        from tests.helpers.homeassistant_test_stubs import (
            install_homeassistant_stubs,
        )
    except Exception:  # pragma: no cover - tests package unavailable
        return

    install_homeassistant_stubs()


_ensure_homeassistant_stubs()
