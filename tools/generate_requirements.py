"""Generate requirements_test.txt from pyproject optional test dependencies."""

from __future__ import annotations

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
OUTPUT = ROOT / "requirements_test.txt"

EXTRA_DEPS = [
    "homeassistant>=2025.8.0",
    "pytest-homeassistant-custom-component  # follows daily HA version",
]


def main() -> None:
    data = tomllib.loads(PYPROJECT.read_text())
    test_deps = data.get("project", {}).get("optional-dependencies", {}).get("test", [])
    deps = sorted(set(test_deps + EXTRA_DEPS))
    lines = ["# Auto-generated test requirements. Do not edit manually.", *deps, ""]
    OUTPUT.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
