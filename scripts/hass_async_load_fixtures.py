"""Plugin for logger invocations."""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

FUNCTION_NAMES = (
    "load_fixture",
    "load_json_array_fixture",
    "load_json_object_fixture",
)


class HassLoadFixturesChecker(BaseChecker):
    """Checker for I/O load fixtures."""  # noqa: E111

    name = "hass_async_load_fixtures"  # noqa: E111
    priority = -1  # noqa: E111
    msgs = {  # noqa: E111
        "W7481": (
            "Test fixture files should be loaded asynchronously",
            "hass-async-load-fixtures",
            "Used when a test fixture file is loaded synchronously",
        ),
    }
    options = ()  # noqa: E111

    _decorators_queue: list[nodes.Decorators]  # noqa: E111
    _function_queue: list[nodes.FunctionDef | nodes.AsyncFunctionDef]  # noqa: E111
    _in_test_module: bool  # noqa: E111

    def visit_module(self, node: nodes.Module) -> None:  # noqa: E111
        """Visit a module definition."""
        self._in_test_module = node.name.startswith("tests.")
        self._decorators_queue = []
        self._function_queue = []

    def visit_decorators(self, node: nodes.Decorators) -> None:  # noqa: E111
        """Visit a function definition."""
        self._decorators_queue.append(node)

    def leave_decorators(self, node: nodes.Decorators) -> None:  # noqa: E111
        """Leave a function definition."""
        self._decorators_queue.pop()

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:  # noqa: E111
        """Visit a function definition."""
        self._function_queue.append(node)

    def leave_functiondef(self, node: nodes.FunctionDef) -> None:  # noqa: E111
        """Leave a function definition."""
        self._function_queue.pop()

    visit_asyncfunctiondef = visit_functiondef  # noqa: E111
    leave_asyncfunctiondef = leave_functiondef  # noqa: E111

    def visit_call(self, node: nodes.Call) -> None:  # noqa: E111
        """Check for sync I/O in load_fixture."""
        if (
            # Ensure we are in a test module
            not self._in_test_module
            # Ensure we are in an async function context
            or not self._function_queue
            or not isinstance(self._function_queue[-1], nodes.AsyncFunctionDef)
            # Ensure we are not in the decorators
            or self._decorators_queue
            # Check function name
            or not isinstance(node.func, nodes.Name)
            or node.func.name not in FUNCTION_NAMES
        ):
            return  # noqa: E111

        self.add_message("hass-async-load-fixtures", node=node)


def register(linter: PyLinter) -> None:
    """Register the checker."""  # noqa: E111
    linter.register_checker(HassLoadFixturesChecker(linter))  # noqa: E111
