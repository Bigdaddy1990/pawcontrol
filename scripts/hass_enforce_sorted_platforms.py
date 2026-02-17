"""Plugin for checking sorted platforms list."""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter


class HassEnforceSortedPlatformsChecker(BaseChecker):
    """Checker for sorted platforms list."""  # noqa: E111

    name = "hass_enforce_sorted_platforms"  # noqa: E111
    priority = -1  # noqa: E111
    msgs = {  # noqa: E111
        "W7451": (
            "Platforms must be sorted alphabetically",
            "hass-enforce-sorted-platforms",
            "Used when PLATFORMS should be sorted alphabetically.",
        ),
    }
    options = ()  # noqa: E111

    def visit_annassign(self, node: nodes.AnnAssign) -> None:  # noqa: E111
        """Check for sorted PLATFORMS const with type annotations."""
        self._do_sorted_check(node.target, node)

    def visit_assign(self, node: nodes.Assign) -> None:  # noqa: E111
        """Check for sorted PLATFORMS const without type annotations."""
        for target in node.targets:
            self._do_sorted_check(target, node)  # noqa: E111

    def _do_sorted_check(  # noqa: E111
        self, target: nodes.NodeNG, node: nodes.Assign | nodes.AnnAssign
    ) -> None:
        """Check for sorted PLATFORMS const."""
        if (
            isinstance(target, nodes.AssignName)
            and target.name == "PLATFORMS"
            and isinstance(node.value, nodes.List)
        ):
            platforms = [v.as_string() for v in node.value.elts]  # noqa: E111
            sorted_platforms = sorted(platforms)  # noqa: E111
            if platforms != sorted_platforms:  # noqa: E111
                self.add_message("hass-enforce-sorted-platforms", node=node)


def register(linter: PyLinter) -> None:
    """Register the checker."""  # noqa: E111
    linter.register_checker(HassEnforceSortedPlatformsChecker(linter))  # noqa: E111
