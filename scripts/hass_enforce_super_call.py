"""Plugin for checking super calls."""

from __future__ import annotations

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.interfaces import INFERENCE
from pylint.lint import PyLinter

METHODS = {
  "async_added_to_hass",
}


class HassEnforceSuperCallChecker(BaseChecker):
  """Checker for super calls."""  # noqa: E111

  name = "hass_enforce_super_call"  # noqa: E111
  priority = -1  # noqa: E111
  msgs = {  # noqa: E111
    "W7441": (
      "Missing call to: super().%s",
      "hass-missing-super-call",
      "Used when method should call its parent implementation.",
    ),
  }
  options = ()  # noqa: E111

  def visit_functiondef(self, node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> None:  # noqa: E111
    """Check for super calls in method body."""
    if node.name not in METHODS:
      return  # noqa: E111

    assert node.parent
    parent = node.parent.frame()
    if not isinstance(parent, nodes.ClassDef):
      return  # noqa: E111

    # Check function body for super call
    for child_node in node.body:
      while isinstance(child_node, (nodes.Expr, nodes.Await, nodes.Return)):  # noqa: E111
        child_node = child_node.value
      match child_node:  # noqa: E111
        case nodes.Call(
          func=nodes.Attribute(
            expr=nodes.Call(func=nodes.Name(name="super")),
            attrname=node.name,
          ),
        ):
          return  # noqa: E111

    # Check for non-empty base implementation
    found_base_implementation = False
    for base in parent.ancestors():
      for method in base.mymethods():  # noqa: E111
        if method.name != node.name:
          continue  # noqa: E111
        if method.body and not (
          len(method.body) == 1 and isinstance(method.body[0], nodes.Pass)
        ):
          found_base_implementation = True  # noqa: E111
        break

      if found_base_implementation:  # noqa: E111
        self.add_message(
          "hass-missing-super-call",
          node=node,
          args=(node.name,),
          confidence=INFERENCE,
        )
        break

  visit_asyncfunctiondef = visit_functiondef  # noqa: E111


def register(linter: PyLinter) -> None:
  """Register the checker."""  # noqa: E111
  linter.register_checker(HassEnforceSuperCallChecker(linter))  # noqa: E111
