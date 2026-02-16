"""Plugin for logger invocations."""

from __future__ import annotations

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

LOGGER_NAMES = ("LOGGER", "_LOGGER")
LOG_LEVEL_ALLOWED_LOWER_START = ("debug",)


class HassLoggerFormatChecker(BaseChecker):
  """Checker for logger invocations."""  # noqa: E111

  name = "hass_logger"  # noqa: E111
  priority = -1  # noqa: E111
  msgs = {  # noqa: E111
    "W7401": (
      "User visible logger messages must not end with a period",
      "hass-logger-period",
      "Periods are not permitted at the end of logger messages",
    ),
    "W7402": (
      "User visible logger messages must start with a capital letter or downgrade to debug",  # noqa: E501
      "hass-logger-capital",
      "All logger messages must start with a capital letter",
    ),
  }
  options = ()  # noqa: E111

  def visit_call(self, node: nodes.Call) -> None:  # noqa: E111
    """Check for improper log messages."""
    if not isinstance(node.func, nodes.Attribute) or not isinstance(
      node.func.expr, nodes.Name
    ):
      return  # noqa: E111

    if node.func.expr.name not in LOGGER_NAMES:
      return  # noqa: E111

    if not node.args:
      return  # noqa: E111

    first_arg = node.args[0]

    if not isinstance(first_arg, nodes.Const) or not first_arg.value:
      return  # noqa: E111

    log_message = first_arg.value

    if len(log_message) < 1:
      return  # noqa: E111

    if log_message[-1] == ".":
      self.add_message("hass-logger-period", node=node)  # noqa: E111

    if (
      isinstance(node.func.attrname, str)
      and node.func.attrname not in LOG_LEVEL_ALLOWED_LOWER_START
      and log_message[0].upper() != log_message[0]
    ):
      self.add_message("hass-logger-capital", node=node)  # noqa: E111


def register(linter: PyLinter) -> None:
  """Register the checker."""  # noqa: E111
  linter.register_checker(HassLoggerFormatChecker(linter))  # noqa: E111
