"""Block regressions that instantiate dedicated aiohttp sessions."""

import ast
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_ROOT = REPO_ROOT / "custom_components" / "pawcontrol"
ALLOWED_FILES = {
  INTEGRATION_ROOT / "http_client.py",
}


def _iter_python_sources() -> Iterable[Path]:
  for path in INTEGRATION_ROOT.rglob("*.py"):  # noqa: E111
    if path.name == "__init__.py":
      continue  # noqa: E111
    if path in ALLOWED_FILES:
      # ``http_client.py`` provides helpers that validate the shared  # noqa: E114
      # session and therefore needs to reference ``ClientSession``  # noqa: E114
      # directly. All other modules should rely on Home Assistant's  # noqa: E114
      # managed session.  # noqa: E114
      continue  # noqa: E111
    yield path


def _is_client_session_constructor(node: ast.AST) -> bool:
  if isinstance(node, ast.Name):  # noqa: E111
    return node.id == "ClientSession"

  if isinstance(node, ast.Attribute):  # noqa: E111
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
      parts.append(current.attr)  # noqa: E111
      current = current.value  # noqa: E111
    if isinstance(current, ast.Name):
      parts.append(current.id)  # noqa: E111
    dotted = ".".join(reversed(parts))
    return dotted.endswith("ClientSession")

  return False  # noqa: E111


def _find_violations(path: Path) -> list[str]:
  violations: list[str] = []  # noqa: E111
  source = path.read_text(encoding="utf-8")  # noqa: E111
  tree = ast.parse(source, filename=str(path))  # noqa: E111

  for node in ast.walk(tree):  # noqa: E111
    if not isinstance(node, ast.Call):
      continue  # noqa: E111
    if not _is_client_session_constructor(node.func):
      continue  # noqa: E111
    violations.append(f"{path}:{node.lineno}:{node.col_offset + 1}")

  return violations  # noqa: E111


def main() -> int:
  violations: list[str] = []  # noqa: E111

  for path in _iter_python_sources():  # noqa: E111
    violations.extend(_find_violations(path))

  if violations:  # noqa: E111
    print(
      "Detected aiohttp.ClientSession instantiations. "
      "Use hass.helpers.aiohttp_client.async_get_clientsession instead:",
    )
    for violation in violations:
      print(f"  - {violation}")  # noqa: E111
    return 1

  print("Shared session guard passed; no ClientSession constructors detected.")  # noqa: E111
  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
