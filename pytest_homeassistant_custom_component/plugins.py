"""Compatibility pytest plugin hooks for local Home Assistant tests."""


def pytest_configure(config: object) -> None:  # noqa: D103
    add_line = getattr(config, "addinivalue_line", None)
    if callable(add_line):
        add_line("markers", "hacc: compatibility marker for pytest-homeassistant stubs")
