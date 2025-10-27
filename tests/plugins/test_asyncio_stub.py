from __future__ import annotations

import textwrap

import pytest

pytest_plugins = ("pytester",)


def test_session_loop_debug_hook(pytester: pytest.Pytester) -> None:
    """Ensure the asyncio stub cooperates with debug hooks."""

    pytester.makeconftest(
        textwrap.dedent(
            """\
import asyncio

import pytest

pytest_plugins = ("tests.plugins.asyncio_stub",)

_SESSION_DEBUG_STATE: dict[str, asyncio.AbstractEventLoop | None] = {
    "loop": None,
}


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    del session
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    _SESSION_DEBUG_STATE["loop"] = loop


@pytest.fixture()
def captured_session_loop() -> asyncio.AbstractEventLoop:
    loop = _SESSION_DEBUG_STATE["loop"]
    assert loop is not None
    return loop
            """
        )
    )

    pytester.makepyfile(
        test_app="""\
import asyncio


def test_loop_uses_session_debug_state(captured_session_loop):
    loop = asyncio.get_event_loop()
    assert loop is captured_session_loop
    assert loop.get_debug()
        """
    )

    result = pytester.runpytest("-q", "-p", "no:sugar")
    result.assert_outcomes(passed=1)


def test_enable_event_loop_debug_via_pytest_addhooks(
    pytester: pytest.Pytester,
) -> None:
    """Ensure ``pytest_addhooks`` exposes the debug helper without runtime errors."""

    pytester.makepyfile(
        test_enable="""\
import asyncio

import pytest

pytest_plugins = ("tests.plugins.asyncio_stub",)


def test_enable_event_loop_debug(pytestconfig: pytest.Config) -> None:
    pytestconfig.hook.pytest_addhooks.call_historic(
        kwargs={"pluginmanager": pytestconfig.pluginmanager}
    )
    from tests.plugins import asyncio_stub

    loop = asyncio_stub.enable_event_loop_debug()
    assert loop.get_debug()
        """,
    )

    result = pytester.runpytest("-q", "-p", "no:sugar")
    result.assert_outcomes(passed=1)
