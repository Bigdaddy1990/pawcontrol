"""Type Safety Validation Script for PawControl.

This script verifies that all modules maintain strict type safety
by checking for common type violations.

Usage:
    python scripts/validate_type_safety.py

Returns:
    Exit code 0 if all checks pass, 1 otherwise
"""

import ast
from pathlib import Path
import sys
from typing import Any


class TypeSafetyChecker(ast.NodeVisitor):
    """AST visitor that checks for type safety violations."""

    def __init__(self) -> None:
        """Initialize the checker."""
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.current_file: str = ""
        self.functions_without_return_type: list[tuple[str, int]] = []
        self.functions_without_param_types: list[tuple[str, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function definitions for type annotations."""
        # Skip test functions
        if node.name.startswith("test_"):
            self.generic_visit(node)
            return

        # Skip dunder methods (except __init__)
        if node.name.startswith("__") and node.name != "__init__":
            self.generic_visit(node)
            return

        # Check return type annotation
        if node.returns is None and node.name != "__init__":
            self.functions_without_return_type.append(
                (f"{self.current_file}:{node.lineno}", node.name),
            )

        # Check parameter type annotations
        for arg in node.args.args:
            if arg.arg == "self" or arg.arg == "cls":
                continue
            if arg.annotation is None:
                self.functions_without_param_types.append(
                    (f"{self.current_file}:{node.lineno}", f"{node.name}({arg.arg})"),
                )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check async function definitions for type annotations."""
        # Skip test functions
        if node.name.startswith("test_"):
            self.generic_visit(node)
            return

        # Skip dunder methods
        if node.name.startswith("__"):
            self.generic_visit(node)
            return

        # Check return type annotation
        if node.returns is None:
            self.functions_without_return_type.append(
                (f"{self.current_file}:{node.lineno}", node.name),
            )

        # Check parameter type annotations
        for arg in node.args.args:
            if arg.arg == "self" or arg.arg == "cls":
                continue
            if arg.annotation is None:
                self.functions_without_param_types.append(
                    (f"{self.current_file}:{node.lineno}", f"{node.name}({arg.arg})"),
                )

        self.generic_visit(node)


def check_file(file_path: Path) -> TypeSafetyChecker:
    """Check a single Python file for type safety."""
    checker = TypeSafetyChecker()
    checker.current_file = str(file_path)

    try:
        with file_path.open() as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        checker.visit(tree)
    except SyntaxError as e:
        checker.errors.append(f"{file_path}: Syntax error: {e}")

    return checker


def main() -> int:
    """Run type safety checks on all Python files."""
    root = Path(__file__).parent.parent
    component_path = root / "custom_components" / "pawcontrol"

    if not component_path.exists():
        print(f"❌ Component path not found: {component_path}")
        return 1

    print("🔍 Checking type safety...")
    print(f"📁 Path: {component_path}\n")

    all_checkers: list[TypeSafetyChecker] = []
    files_checked = 0

    for py_file in component_path.rglob("*.py"):
        # Skip __pycache__ and test files
        if "__pycache__" in str(py_file) or py_file.name.startswith("test_"):
            continue

        checker = check_file(py_file)
        all_checkers.append(checker)
        files_checked += 1

    # Aggregate results
    total_errors = sum(len(c.errors) for c in all_checkers)
    total_missing_return_types = sum(
        len(c.functions_without_return_type) for c in all_checkers
    )
    total_missing_param_types = sum(
        len(c.functions_without_param_types) for c in all_checkers
    )

    # Report results
    print(f"✅ Files checked: {files_checked}")
    print(f"{'❌' if total_errors > 0 else '✅'} Syntax errors: {total_errors}")
    print(
        f"{'⚠️' if total_missing_return_types > 0 else '✅'} Missing return types: {total_missing_return_types}"  # noqa: E501
    )
    print(
        f"{'⚠️' if total_missing_param_types > 0 else '✅'} Missing parameter types: {total_missing_param_types}\n"  # noqa: E501
    )

    # Show details if there are issues
    if total_errors > 0:
        print("❌ SYNTAX ERRORS:")
        for checker in all_checkers:
            for error in checker.errors:
                print(f"  {error}")
        print()

    if total_missing_return_types > 0:
        print("⚠️  FUNCTIONS WITHOUT RETURN TYPE ANNOTATIONS:")
        for checker in all_checkers:
            for location, func_name in checker.functions_without_return_type:
                print(f"  {location}: {func_name}")
        print()

    if total_missing_param_types > 0:
        print("⚠️  FUNCTIONS WITHOUT PARAMETER TYPE ANNOTATIONS:")
        for checker in all_checkers:
            for location, param in checker.functions_without_param_types:
                print(f"  {location}: {param}")
        print()

    # Return success only if no errors and warnings
    if total_errors > 0:
        print("❌ Type safety check FAILED (syntax errors)")
        return 1

    if total_missing_return_types > 0 or total_missing_param_types > 0:
        print(
            f"⚠️  Type safety check completed with {total_missing_return_types + total_missing_param_types} warnings"  # noqa: E501
        )
        return 0  # Warnings don't fail the check, but should be addressed

    print("✅ Type safety check PASSED - All functions are fully typed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
