"""Dependency analysis helpers for hassfest tests."""

from __future__ import annotations

import ast
from typing import Any


class ImportCollector(ast.NodeVisitor):
    """Collect references to Home Assistant integrations from import statements."""

    def __init__(self, module: Any) -> None:  # pragma: no cover - signature parity
        super().__init__()
        self.module = module
        self.unfiltered_referenced: set[str] = set()
        self._add_reference = self.unfiltered_referenced.add

    def _record_component(self, module_name: str) -> None:
        """Record the integration name extracted from an import path."""

        prefix = "homeassistant.components."
        if not module_name.startswith(prefix):
            return
        component_path = module_name[len(prefix) :]
        if not component_path:
            return
        integration = component_path.split(".", 1)[0]
        if integration:
            self._add_reference(integration)

    def visit_Import(
        self, node: ast.Import
    ) -> None:  # pragma: no cover - exercised via tests
        for alias in node.names:
            self._record_component(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # pragma: no cover
        if node.module:
            self._record_component(node.module)
        self.generic_visit(node)


__all__ = ["ImportCollector"]
