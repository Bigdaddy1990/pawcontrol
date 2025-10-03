"""Ensure PawControl HTTP helpers reuse Home Assistant's shared session."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_ROOT = REPO_ROOT / "custom_components" / "pawcontrol"
CONFIG_PATH = REPO_ROOT / "scripts" / "shared_session_guard_roots.toml"
ALLOWED_FILES: frozenset[Path] = frozenset({INTEGRATION_ROOT / "http_client.py"})
TARGET_MODULES: frozenset[str] = frozenset(
    {"aiohttp", "aiohttp.client", "aiohttp.client_reqrep"}
)
ERROR_TEMPLATE = (
    "{path}: Detected direct ClientSession instantiation. Use "
    "ensure_shared_client_session() to enforce shared-session reuse."
)


def _iter_python_files(root: Path) -> Iterable[Path]:
    """Yield Python files within *root* recursively."""

    for file_path in root.rglob("*.py"):
        if file_path.is_file():
            yield file_path


def _discover_package_roots(base: Path) -> set[Path]:
    """Return integration packages that should be scanned automatically."""

    roots: set[Path] = {base}
    for init_file in base.rglob("__init__.py"):
        parent = init_file.parent
        if parent.is_dir():
            roots.add(parent.resolve())

    return roots


def _resolve_configured_roots() -> set[Path]:
    """Return directories that should be scanned for direct session usage."""

    roots: set[Path] = _discover_package_roots(INTEGRATION_ROOT)
    if not CONFIG_PATH.exists():
        return roots

    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    configured = config.get("roots", [])
    for entry in configured:
        if not isinstance(entry, str) or not entry.strip():
            continue

        pattern = entry.strip()
        # Support simple glob patterns (e.g., "services/*") so future helper
        # packages are picked up automatically without modifying this script.
        if any(char in pattern for char in "*?[]"):
            for match in REPO_ROOT.glob(pattern):
                if match.is_dir():
                    roots.add(match.resolve())
            continue

        candidate = (REPO_ROOT / pattern).resolve()
        if candidate.is_dir():
            roots.add(candidate)

    return roots


SCAN_ROOTS: tuple[Path, ...] = tuple(sorted(_resolve_configured_roots()))


def _collect_client_session_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return alias names for ClientSession and aiohttp modules."""

    session_aliases: set[str] = {"ClientSession"}
    module_aliases: set[str] = {"aiohttp", "client_session"}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in TARGET_MODULES:
            for alias in node.names:
                if alias.name == "ClientSession":
                    session_aliases.add(alias.asname or alias.name)
                else:
                    module_aliases.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in TARGET_MODULES:
                    continue
                module_aliases.add((alias.asname or alias.name).split(".")[0])

    return session_aliases, module_aliases


def _attribute_base_name(node: ast.Attribute) -> str | None:
    """Return the left-most identifier for an attribute chain."""

    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parent = current.value
        if isinstance(parent, ast.Name):
            return parent.id
        current = parent
    if isinstance(current, ast.Name):
        return current.id
    return None


def _attribute_full_name(node: ast.Attribute) -> str | None:
    """Return the dotted attribute name for ``node`` if resolvable."""

    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _detect_client_session_calls(tree: ast.AST) -> list[ast.Call]:
    """Return all call nodes that instantiate an aiohttp ClientSession."""

    offenders: list[ast.Call] = []
    session_aliases, module_aliases = _collect_client_session_aliases(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        # Match direct names including aliased imports (e.g. ``ClientSession``
        # or ``AioClientSession`` from ``as`` imports).
        if isinstance(func, ast.Name) and func.id in session_aliases:
            offenders.append(node)
            continue

        if isinstance(func, ast.Attribute):
            base_name = _attribute_base_name(func)
            full_name = _attribute_full_name(func)

            if full_name in {
                "aiohttp.ClientSession",
                "aiohttp.client.ClientSession",
                "aiohttp.client_reqrep.ClientSession",
            }:
                offenders.append(node)
                continue

            if base_name in module_aliases and func.attr == "ClientSession":
                offenders.append(node)

    return offenders


def main() -> int:
    """Validate that no module bypasses the shared session guard."""

    failures: list[str] = []

    for root in SCAN_ROOTS:
        for file_path in _iter_python_files(root):
            if file_path in ALLOWED_FILES:
                continue

            tree = ast.parse(file_path.read_text(encoding="utf-8"))
            offenders = _detect_client_session_calls(tree)
            if offenders:
                failures.append(
                    ERROR_TEMPLATE.format(path=file_path.relative_to(REPO_ROOT))
                )

    if failures:
        print("\n".join(sorted(failures)))
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    sys.exit(main())
