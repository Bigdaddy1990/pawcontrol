"""Plugin to enforce type hints on specific functions."""

import re

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

_MODULE_REGEX: re.Pattern[str] = re.compile(r"^homeassistant\.components\.\w+(\.\w+)?$")


def _get_module_platform(module_name: str) -> str | None:
    """Return the platform for the module name."""  # noqa: E111
    if not (module_match := _MODULE_REGEX.match(module_name)):  # noqa: E111
        # Ensure `homeassistant.components.<component>`
        # Or `homeassistant.components.<component>.<platform>`
        return None

    platform = module_match.group(1)  # noqa: E111
    return platform.lstrip(".") if platform else "__init__"  # noqa: E111


class HassInheritanceChecker(BaseChecker):
    """Checker for invalid inheritance."""  # noqa: E111

    name = "hass_inheritance"  # noqa: E111
    priority = -1  # noqa: E111
    msgs = {  # noqa: E111
        "W7411": (
            "Invalid inheritance: %s",
            "hass-invalid-inheritance",
            "Used when a class has inheritance has issues",
        ),
    }
    options = ()  # noqa: E111

    _module_name: str  # noqa: E111
    _module_platform: str | None  # noqa: E111

    def visit_module(self, node: nodes.Module) -> None:  # noqa: E111
        """Populate matchers for a Module node."""
        self._module_name = node.name
        self._module_platform = _get_module_platform(node.name)

    def visit_classdef(self, node: nodes.ClassDef) -> None:  # noqa: E111
        """Apply relevant type hint checks on a ClassDef node."""
        if self._module_platform not in {"number", "sensor"}:
            return  # noqa: E111

        ancestors = [a.name for a in node.ancestors()]
        if (
            "RestoreEntity" in ancestors
            and "SensorEntity" in ancestors
            and "RestoreSensor" not in ancestors
        ):
            self.add_message(  # noqa: E111
                "hass-invalid-inheritance",
                node=node,
                args="SensorEntity and RestoreEntity should not be combined, please use RestoreSensor",  # noqa: E501
            )
        elif (
            "RestoreEntity" in ancestors
            and "NumberEntity" in ancestors
            and "RestoreNumber" not in ancestors
        ):
            self.add_message(  # noqa: E111
                "hass-invalid-inheritance",
                node=node,
                args="NumberEntity and RestoreEntity should not be combined, please use RestoreNumber",  # noqa: E501
            )


def register(linter: PyLinter) -> None:
    """Register the checker."""  # noqa: E111
    linter.register_checker(HassInheritanceChecker(linter))  # noqa: E111
