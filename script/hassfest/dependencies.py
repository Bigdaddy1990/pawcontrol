"""Minimal dependency scanner used by hassfest tests."""

from __future__ import annotations

import ast


class ImportCollector(ast.NodeVisitor):
    """Collect Home Assistant component import references."""

    def __init__(self, config) -> None:
        super().__init__()
        self._config = config
        self.unfiltered_referenced: set[str] = set()
        self._add_reference = self.unfiltered_referenced.add

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # type: ignore[override]
        module = node.module or ""
        if module == "homeassistant.components":
            for alias in node.names:
                self._add_reference(alias.name.split(".")[0])
        elif module.startswith("homeassistant.components."):
            component = module.split(".", 2)[2]
            self._add_reference(component.split(".")[0])
        super().visit_ImportFrom(node)

    def visit_Import(self, node: ast.Import) -> None:  # type: ignore[override]
        for alias in node.names:
            name = alias.name
            if name.startswith("homeassistant.components."):
                component = name.split(".", 2)[2]
                self._add_reference(component.split(".")[0])
        super().visit_Import(node)


__all__ = ["ImportCollector"]
