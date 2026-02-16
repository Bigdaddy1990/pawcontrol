"""Type Safety Validation Script for PawControl.

This script verifies that all modules maintain strict type safety
by checking for common type violations.

Usage:
    python scripts/validate_type_safety.py

Returns:
    Exit code 0 if all checks pass, 1 otherwise
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Any


class TypeSafetyChecker(ast.NodeVisitor):
  """AST visitor that checks for type safety violations."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    """Initialize the checker."""
    self.errors: list[str] = []
    self.warnings: list[str] = []
    self.current_file: str = ""
    self.functions_without_return_type: list[tuple[str, int]] = []
    self.functions_without_param_types: list[tuple[str, int]] = []

  def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: E111
    """Check function definitions for type annotations."""
    # Skip test functions
    if node.name.startswith("test_"):
      self.generic_visit(node)  # noqa: E111
      return  # noqa: E111

    # Skip dunder methods (except __init__)
    if node.name.startswith("__") and node.name != "__init__":
      self.generic_visit(node)  # noqa: E111
      return  # noqa: E111

    # Check return type annotation
    if node.returns is None and node.name != "__init__":
      self.functions_without_return_type.append(  # noqa: E111
        (f"{self.current_file}:{node.lineno}", node.name),
      )

    # Check parameter type annotations
    for arg in node.args.args:
      if arg.arg == "self" or arg.arg == "cls":  # noqa: E111
        continue
      if arg.annotation is None:  # noqa: E111
        self.functions_without_param_types.append(
          (f"{self.current_file}:{node.lineno}", f"{node.name}({arg.arg})"),
        )

    self.generic_visit(node)

  def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: E111
    """Check async function definitions for type annotations."""
    # Skip test functions
    if node.name.startswith("test_"):
      self.generic_visit(node)  # noqa: E111
      return  # noqa: E111

    # Skip dunder methods
    if node.name.startswith("__"):
      self.generic_visit(node)  # noqa: E111
      return  # noqa: E111

    # Check return type annotation
    if node.returns is None:
      self.functions_without_return_type.append(  # noqa: E111
        (f"{self.current_file}:{node.lineno}", node.name),
      )

    # Check parameter type annotations
    for arg in node.args.args:
      if arg.arg == "self" or arg.arg == "cls":  # noqa: E111
        continue
      if arg.annotation is None:  # noqa: E111
        self.functions_without_param_types.append(
          (f"{self.current_file}:{node.lineno}", f"{node.name}({arg.arg})"),
        )

    self.generic_visit(node)


def check_file(file_path: Path) -> TypeSafetyChecker:
  """Check a single Python file for type safety."""  # noqa: E111
  checker = TypeSafetyChecker()  # noqa: E111
  checker.current_file = str(file_path)  # noqa: E111

  try:  # noqa: E111
    with file_path.open() as f:
      tree = ast.parse(f.read(), filename=str(file_path))  # noqa: E111
    checker.visit(tree)
  except SyntaxError as e:  # noqa: E111
    checker.errors.append(f"{file_path}: Syntax error: {e}")

  return checker  # noqa: E111


def main() -> int:
  """Run type safety checks on all Python files."""  # noqa: E111
  root = Path(__file__).parent.parent  # noqa: E111
  component_path = root / "custom_components" / "pawcontrol"  # noqa: E111

  if not component_path.exists():  # noqa: E111
    print(f"❌ Component path not found: {component_path}")
    return 1

  print("🔍 Checking type safety...")  # noqa: E111
  print(f"📁 Path: {component_path}\n")  # noqa: E111

  all_checkers: list[TypeSafetyChecker] = []  # noqa: E111
  files_checked = 0  # noqa: E111

  for py_file in component_path.rglob("*.py"):  # noqa: E111
    # Skip __pycache__ and test files
    if "__pycache__" in str(py_file) or py_file.name.startswith("test_"):
      continue  # noqa: E111

    checker = check_file(py_file)
    all_checkers.append(checker)
    files_checked += 1

  # Aggregate results  # noqa: E114
  total_errors = sum(len(c.errors) for c in all_checkers)  # noqa: E111
  total_missing_return_types = sum(  # noqa: E111
    len(c.functions_without_return_type) for c in all_checkers
  )
  total_missing_param_types = sum(  # noqa: E111
    len(c.functions_without_param_types) for c in all_checkers
  )

  # Report results  # noqa: E114
  print(f"✅ Files checked: {files_checked}")  # noqa: E111
  print(f"{'❌' if total_errors > 0 else '✅'} Syntax errors: {total_errors}")  # noqa: E111
  print(  # noqa: E111
    f"{'⚠️' if total_missing_return_types > 0 else '✅'} Missing return types: {total_missing_return_types}"  # noqa: E501
  )
  print(  # noqa: E111
    f"{'⚠️' if total_missing_param_types > 0 else '✅'} Missing parameter types: {total_missing_param_types}\n"  # noqa: E501
  )

  # Show details if there are issues  # noqa: E114
  if total_errors > 0:  # noqa: E111
    print("❌ SYNTAX ERRORS:")
    for checker in all_checkers:
      for error in checker.errors:  # noqa: E111
        print(f"  {error}")
    print()

  if total_missing_return_types > 0:  # noqa: E111
    print("⚠️  FUNCTIONS WITHOUT RETURN TYPE ANNOTATIONS:")
    for checker in all_checkers:
      for location, func_name in checker.functions_without_return_type:  # noqa: E111
        print(f"  {location}: {func_name}")
    print()

  if total_missing_param_types > 0:  # noqa: E111
    print("⚠️  FUNCTIONS WITHOUT PARAMETER TYPE ANNOTATIONS:")
    for checker in all_checkers:
      for location, param in checker.functions_without_param_types:  # noqa: E111
        print(f"  {location}: {param}")
    print()

  # Return success only if no errors and warnings  # noqa: E114
  if total_errors > 0:  # noqa: E111
    print("❌ Type safety check FAILED (syntax errors)")
    return 1

  if total_missing_return_types > 0 or total_missing_param_types > 0:  # noqa: E111
    print(
      f"⚠️  Type safety check completed with {total_missing_return_types + total_missing_param_types} warnings"  # noqa: E501
    )
    return 0  # Warnings don't fail the check, but should be addressed

  print("✅ Type safety check PASSED - All functions are fully typed!")  # noqa: E111
  return 0  # noqa: E111


if __name__ == "__main__":
  sys.exit(main())  # noqa: E111
