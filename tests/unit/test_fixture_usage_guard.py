"""Ensure Pytest fixtures are not called directly inside the test suite."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final, TypeAlias

type DynamicPath = tuple[str, ...]
type DynamicFixture = str | tuple[tuple[DynamicPath, str], ...]

FORBIDDEN_FIXTURE_CALLS: Final[dict[str, str]] = {
  "aiohttp_server": "Use the ``aiohttp_client`` helpers instead of calling the fixture.",
  "hass_companion_client": (
    "Request the companion HTTP client fixture via a parameter instead of"
    " invoking it manually.",
  ),
  "hass_companion_ws_client": (
    "Inject the companion websocket client fixture via a parameter rather than"
    " calling it directly.",
  ),
  "hass_mobile_app_client": (
    "Request the mobile app client fixture via a parameter instead of invoking"
    " it directly.",
  ),
  "hass_mobile_app_ws_client": (
    "Inject the mobile websocket client fixture through a parameter rather than"
    " calling it manually.",
  ),
  "hass_client_admin": (
    "Inject the admin HTTP client fixture via a parameter instead of invoking"
    " it directly."
  ),
  "hass_client": (
    "Inject the HTTP client fixture via a parameter instead of invoking it manually."
  ),
  "hass_client_no_auth": (
    "Request the unauthenticated HTTP client fixture via a parameter instead of"
    " invoking it directly."
  ),
  "hass_supervisor_admin_ws_client": (
    "Inject the supervisor admin websocket helper as a fixture argument instead"
    " of calling it directly.",
  ),
  "hass_supervisor_client": (
    "Inject the supervisor HTTP client fixture via a test parameter instead of"
    " invoking it manually.",
  ),
  "hass_supervisor_ws_client": (
    "Inject the supervisor websocket client fixture through a parameter rather"
    " than calling it directly.",
  ),
  "hass_ws_client": (
    "Request the websocket fixture via a test argument instead of calling it directly."
  ),
  "hass_admin_ws_client": (
    "Request the admin websocket client via a fixture argument instead of"
    " invoking it directly."
  ),
  "hass_owner_ws_client": (
    "Request the owner websocket client via a fixture argument instead of"
    " invoking it directly."
  ),
  "hass_voice_assistant_client": (
    "Inject the voice assistant HTTP client fixture via a parameter rather"
    " than calling it manually.",
  ),
  "hass_voice_assistant_ws_client": (
    "Inject the voice assistant websocket client fixture via a fixture"
    " argument instead of invoking it directly.",
  ),
}

FORBIDDEN_FIXTURE_PREFIXES: Final[dict[str, str]] = {
  "hass_companion_": (
    "Request companion fixtures via a pytest parameter instead of invoking "
    "them manually."
  ),
  "hass_voice_assistant_": (
    "Inject voice assistant fixtures via a pytest parameter rather than "
    "calling them directly."
  ),
}

SKIP_ARGUMENT_WRAPPERS: Final[set[str]] = {
  "partial",
  "partialmethod",
  "getattr",
  "MethodType",
  "wraps",
  "update_wrapper",
  "property",
  "cached_property",
  "classmethod",
  "staticmethod",
  "contextmanager",
  "asynccontextmanager",
  "entry_points",
  "SimpleNamespace",
  "ModuleSpec",
  "module_from_spec",
  "open_binary",
  "open_file",
  "open_text",
  "read_text",
  "open",
  "get_data",
  "get_loader",
  "find_loader",
  "find_spec",
  "read_binary",
  "load_module",
  "get_code",
  "find_module",
  "joinpath",
  "with_suffix",
  "with_name",
  "with_stem",
  "with_segments",
  "relative_to",
  "resolve",
  "exec_module",
  "invalidate_caches",
  "files",
}


class _FixtureUsageVisitor(ast.NodeVisitor):
  """Track forbidden fixture usage within a module AST."""

  def __init__(self, *, path: Path) -> None:
    self._path = path
    self.offenders: list[str] = []
    self._alias_map: dict[str, str] = {
      fixture_name: fixture_name for fixture_name in FORBIDDEN_FIXTURE_CALLS
    }
    self._wrapper_aliases: dict[str, str] = {}
    self._class_stack: list[str] = []
    self._dynamic_class_accessors: dict[str, str] = {}
    self._dynamic_attribute_aliases: dict[str, str] = {}
    self._dynamic_attribute_paths: dict[str, dict[DynamicPath, str]] = {}
    self._dynamic_function_returns: dict[str, tuple[tuple[DynamicPath, str], ...]] = {}

  def _match_fixture(self, candidate: str) -> tuple[str | None, str | None]:
    if candidate in FORBIDDEN_FIXTURE_CALLS:
      return candidate, FORBIDDEN_FIXTURE_CALLS[candidate]
    for prefix, message in FORBIDDEN_FIXTURE_PREFIXES.items():
      if candidate.startswith(prefix):
        return candidate, message
    return None, None

  def _resolve_fixture_reference(self, candidate: str) -> tuple[str | None, str | None]:
    alias_target = self._alias_map.get(candidate, candidate)
    return self._match_fixture(alias_target)

  def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
    if node.module == "functools":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {
          "partial",
          "partialmethod",
          "wraps",
          "update_wrapper",
          "cached_property",
        }:
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "types":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {"MethodType", "SimpleNamespace", "ModuleType"}:
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "pkgutil":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {
          "resolve_name",
          "get_importer",
          "get_data",
          "get_loader",
          "find_loader",
          "find_spec",
        }:
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "zipimport":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name == "zipimporter":
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "runpy":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {"run_module", "run_path"}:
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "importlib":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name == "invalidate_caches":
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "importlib.metadata":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {"entry_points", "EntryPoint", "EntryPoints"}:
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "importlib.util":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name == "module_from_spec":
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "importlib.resources":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {
          "files",
          "as_file",
          "read_text",
          "contents",
          "open_binary",
          "open_file",
          "open_text",
          "read_binary",
        }:
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "importlib.machinery":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name == "ModuleSpec":
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "contextlib":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {
          "ExitStack",
          "AsyncExitStack",
          "contextmanager",
          "asynccontextmanager",
          "nullcontext",
          "closing",
          "aclosing",
        }:
          self._wrapper_aliases[alias.asname] = alias.name
    if node.module == "dataclasses":
      for alias in node.names:
        if alias.asname is None:
          continue
        if alias.name in {"field", "make_dataclass"}:
          self._wrapper_aliases[alias.asname] = alias.name
    self.generic_visit(node)

  def visit_Import(self, node: ast.Import) -> None:
    for alias in node.names:
      if alias.asname is None:
        continue
      if alias.name == "functools":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "types":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "pkgutil":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "zipimport":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "runpy":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "importlib":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "importlib.metadata":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "importlib.resources":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "importlib.util":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "importlib.machinery":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "contextlib":
        self._wrapper_aliases[alias.asname] = alias.name
      if alias.name == "dataclasses":
        self._wrapper_aliases[alias.asname] = alias.name
    self.generic_visit(node)

  def visit_ClassDef(self, node: ast.ClassDef) -> None:
    self._class_stack.append(node.name)
    self.generic_visit(node)
    self._class_stack.pop()

  def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
    self.generic_visit(node)
    self._record_descriptor_return(node)
    self._record_function_return(node)

  def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
    self.generic_visit(node)
    self._record_descriptor_return(node)
    self._record_function_return(node)

  def visit_Assign(self, node: ast.Assign) -> None:
    self.visit(node.value)
    fixture_name = self._resolve_name(node.value)
    if fixture_name is not None:
      for target in node.targets:
        self._record_alias(target, fixture_name)
        self._record_dynamic_alias(target, fixture_name)
    dynamic_fixture = self._resolve_dynamic_instance(node.value)
    if dynamic_fixture is not None:
      for target in node.targets:
        self._record_dynamic_alias(target, dynamic_fixture)
    for target in node.targets:
      self.visit(target)

  def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
    if node.value is not None:
      self.visit(node.value)
      fixture_name = self._resolve_name(node.value)
      if fixture_name is not None:
        self._record_alias(node.target, fixture_name)
        self._record_dynamic_alias(node.target, fixture_name)
      dynamic_fixture = self._resolve_dynamic_instance(node.value)
      if dynamic_fixture is not None:
        self._record_dynamic_alias(node.target, dynamic_fixture)
    self.visit(node.target)

  def visit_With(self, node: ast.With) -> None:
    for item in node.items:
      self.visit(item.context_expr)
      if item.optional_vars is None:
        continue
      wrapper_name = self._resolve_wrapper_name(item.context_expr)
      base_wrapper = None
      if wrapper_name is not None:
        base_wrapper = wrapper_name.rsplit(".", 1)[-1]
      fixture_name = self._resolve_name(item.context_expr)
      if fixture_name is not None and base_wrapper not in {
        "nullcontext",
        "closing",
      }:
        self._record_alias(item.optional_vars, fixture_name)
        self._record_dynamic_alias(item.optional_vars, fixture_name)
      dynamic_fixture = self._resolve_dynamic_instance(item.context_expr)
      if dynamic_fixture is not None and not (
        base_wrapper in {"nullcontext", "closing"} and isinstance(dynamic_fixture, str)
      ):
        self._record_dynamic_alias(item.optional_vars, dynamic_fixture)
      self.visit(item.optional_vars)
    for statement in node.body:
      self.visit(statement)

  def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
    for item in node.items:
      self.visit(item.context_expr)
      if item.optional_vars is None:
        continue
      wrapper_name = self._resolve_wrapper_name(item.context_expr)
      base_wrapper = None
      if wrapper_name is not None:
        base_wrapper = wrapper_name.rsplit(".", 1)[-1]
      fixture_name = self._resolve_name(item.context_expr)
      if fixture_name is not None and base_wrapper not in {
        "nullcontext",
        "closing",
      }:
        self._record_alias(item.optional_vars, fixture_name)
        self._record_dynamic_alias(item.optional_vars, fixture_name)
      dynamic_fixture = self._resolve_dynamic_instance(item.context_expr)
      if dynamic_fixture is not None and not (
        base_wrapper in {"nullcontext", "closing"} and isinstance(dynamic_fixture, str)
      ):
        self._record_dynamic_alias(item.optional_vars, dynamic_fixture)
      self.visit(item.optional_vars)
    for statement in node.body:
      self.visit(statement)

  def visit_Call(self, node: ast.Call) -> None:
    fixture_candidate = self._resolve_callable(node.func)
    if isinstance(fixture_candidate, str):
      fixture_name, message = self._resolve_fixture_reference(fixture_candidate)
      if fixture_name and message:
        wrapper_name = self._resolve_wrapper_name(node.func)
        if wrapper_name is None or wrapper_name.rsplit(".", 1)[-1] in {"getattr"}:
          self._flag(node, fixture_name, message)

    self._record_setattr_alias(node)
    self._record_mapping_update(node)

    for argument in node.args:
      self._check_argument(argument, node)
    for keyword in node.keywords:
      if keyword.value is not None:
        self._check_argument(keyword.value, node)

    super().generic_visit(node)

  def _check_argument(self, node: ast.AST, call: ast.Call) -> None:
    wrapper_name = self._resolve_wrapper_name(call.func)
    if wrapper_name is not None and self._should_skip_argument_check(wrapper_name):
      return
    fixture_candidate = self._resolve_name(node)
    if isinstance(fixture_candidate, str):
      fixture_name, message = self._resolve_fixture_reference(fixture_candidate)
      if fixture_name and message:
        self._flag(call, fixture_name, message)

  def _should_skip_argument_check(self, wrapper_name: str) -> bool:
    base_name = wrapper_name.rsplit(".", 1)[-1]
    return base_name in SKIP_ARGUMENT_WRAPPERS

  def _resolve_callable(self, node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
      return self._resolve_name(node)
    if isinstance(node, ast.Attribute):
      return self._resolve_name(node)
    if isinstance(node, ast.Subscript):
      return self._resolve_name(node)
    if isinstance(node, ast.Call):
      return self._resolve_wrapped_fixture(node)
    if isinstance(node, ast.Lambda):
      return self._resolve_name(node.body)
    return None

  def _record_setattr_alias(self, node: ast.Call) -> None:
    callee_name = self._resolve_wrapper_name(node.func)
    if callee_name is None:
      if isinstance(node.func, ast.Name):
        callee_name = node.func.id
      elif isinstance(node.func, ast.Attribute):
        callee_name = node.func.attr
      else:
        return

    if not callee_name.endswith("setattr"):
      return

    attribute_node: ast.AST | None = None
    value_node: ast.AST | None = None

    if len(node.args) >= 3:
      attribute_node = node.args[1]
      value_node = node.args[2]
    else:
      for keyword in node.keywords:
        if keyword.arg == "name":
          attribute_node = keyword.value
        if keyword.arg == "value":
          value_node = keyword.value

    if attribute_node is None or value_node is None:
      return

    if not isinstance(attribute_node, ast.Constant) or not isinstance(
      attribute_node.value, str
    ):
      return

    fixture_name = self._resolve_name(value_node)
    if fixture_name is None:
      return

    self._alias_map[attribute_node.value] = fixture_name

  def _record_mapping_update(self, node: ast.Call) -> None:
    if not isinstance(node.func, ast.Attribute):
      return
    method = node.func.attr
    if method not in {"update", "setdefault"}:
      return

    bases = self._collect_target_bases(node.func.value)
    if not bases:
      return

    if method == "update":
      paths: list[tuple[DynamicPath, str]] = []
      for argument in node.args:
        paths.extend(self._mapping_paths(argument))
      for keyword in node.keywords:
        if keyword.arg is None or keyword.value is None:
          continue
        paths.extend(self._mapping_paths(keyword.value, prefix=(keyword.arg,)))

      if not paths:
        return

      for base in bases:
        path_map = self._dynamic_attribute_paths.setdefault(base, {})
        for path, alias in paths:
          path_map[path] = alias
          self._register_dynamic_path(base, path, alias)
      return

    key_node: ast.AST | None = None
    value_node: ast.AST | None = None

    if node.args:
      key_node = node.args[0]
      if len(node.args) >= 2:
        value_node = node.args[1]

    for keyword in node.keywords:
      if keyword.arg in {None, "key", "name"} and keyword.value is not None:
        key_node = keyword.value
      if keyword.arg in {"default", "value"} and keyword.value is not None:
        value_node = keyword.value

    if (
      key_node is None
      or not isinstance(key_node, ast.Constant)
      or not isinstance(key_node.value, str)
      or value_node is None
    ):
      return

    fixture_name = self._resolve_name(value_node)
    dynamic_fixture: DynamicFixture | None = None
    if fixture_name is None:
      dynamic_fixture = self._resolve_dynamic_instance(value_node)
      if isinstance(dynamic_fixture, str):
        fixture_name = dynamic_fixture
        dynamic_fixture = None
    if fixture_name is None and dynamic_fixture is None:
      return

    for base in bases:
      if dynamic_fixture is not None:
        path_map = self._dynamic_attribute_paths.setdefault(base, {})
        for path, alias in dynamic_fixture:
          combined_path = (key_node.value, *path)
          path_map[combined_path] = alias
          self._register_dynamic_path(base, combined_path, alias)
        continue
      self._register_dynamic_path(base, (key_node.value,), fixture_name)

  def _resolve_name(self, node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
      fixture_name = self._alias_map.get(node.id)
      if fixture_name is not None:
        return fixture_name
      dynamic_alias = self._dynamic_attribute_aliases.get(node.id)
      if dynamic_alias is not None:
        return dynamic_alias
      dynamic_fixture = self._dynamic_class_accessors.get(node.id)
      if dynamic_fixture is not None:
        return dynamic_fixture
      alias_target = self._alias_map.get(node.id)
      if alias_target is not None:
        return self._dynamic_class_accessors.get(alias_target)
      matched_fixture, _ = self._match_fixture(node.id)
      if matched_fixture is not None:
        return matched_fixture
      return None
    if isinstance(node, ast.Attribute):
      dotted = self._extract_dotted_name(node)
      if dotted is not None:
        fixture_name = self._alias_map.get(dotted)
        if fixture_name is not None:
          return fixture_name
      fixture_name = self._alias_map.get(node.attr)
      if fixture_name is not None:
        return fixture_name
      if node.attr == "parent":
        resolved_parent = self._resolve_parent_chain(node.value, 1)
        if resolved_parent is not None:
          if isinstance(resolved_parent, tuple):
            self._record_dynamic_alias(node, resolved_parent)
          else:
            self._record_alias(node, resolved_parent)
          return resolved_parent
      if node.attr == "parents":
        dynamic_parents = self._resolve_dynamic_instance(node.value)
        if dynamic_parents is not None:
          if isinstance(dynamic_parents, tuple):
            trimmed_paths: list[tuple[DynamicPath, str]] = []
            direct_alias: str | None = None
            for path, alias in dynamic_parents:
              if path and path[0] == "parents":
                new_path = path[1:]
              else:
                new_path = path
              if not new_path:
                direct_alias = alias
                continue
              trimmed_paths.append((new_path, alias))
            if trimmed_paths:
              dynamic_parents = tuple(trimmed_paths)
              self._record_dynamic_alias(node, dynamic_parents)
              return dynamic_parents
            if direct_alias is not None:
              self._record_alias(node, direct_alias)
              return direct_alias
          else:
            self._record_dynamic_alias(node, dynamic_parents)
            return dynamic_parents
        base_parents = self._resolve_name(node.value)
        if isinstance(base_parents, str):
          self._record_alias(node, base_parents)
        if base_parents is not None:
          return base_parents
      base_fixture = self._resolve_name(node.value)
      if isinstance(base_fixture, tuple):
        next_paths: list[tuple[DynamicPath, str]] = []
        for path, alias in base_fixture:
          if not path:
            continue
          if path[0] != node.attr:
            continue
          if len(path) == 1:
            return alias
          next_paths.append((path[1:], alias))
        if next_paths:
          return tuple(next_paths)
      if base_fixture is not None:
        return base_fixture
      dynamic_fixture = self._resolve_dynamic_base(node.value)
      if dynamic_fixture is not None:
        return dynamic_fixture
    if isinstance(node, ast.Subscript):
      if isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
        index = self._extract_subscript_index(node.slice)
        if index is not None and index >= 0:
          parent_fixture = self._resolve_parent_chain(node.value.value, 1)
          if parent_fixture is not None:
            if isinstance(parent_fixture, tuple):
              self._record_dynamic_alias(node, parent_fixture)
            elif isinstance(parent_fixture, str):
              self._record_alias(node, parent_fixture)
            return parent_fixture
        return None
      target = self._resolve_name(node.value)
      if target is not None:
        return target
      dynamic_fixture = self._resolve_dynamic_instance(node.value)
      if dynamic_fixture is not None:
        key = self._extract_subscript_key(node.slice)
        if isinstance(dynamic_fixture, tuple):
          if key is not None:
            for path, alias in dynamic_fixture:
              if not path:
                continue
              if path[0] == key:
                if len(path) == 1:
                  return alias
                remaining_path = path[1:]
                bases = self._collect_target_bases(node.value)
                for base in bases:
                  path_map = self._dynamic_attribute_paths.setdefault(base, {})
                  path_map[remaining_path] = alias
                  self._register_dynamic_path(base, remaining_path, alias)
                return alias
          else:
            index = self._extract_subscript_index(node.slice)
            if index is not None and index >= 0:
              trimmed_paths: list[tuple[DynamicPath, str]] = []
              direct_alias: str | None = None
              for path, alias in dynamic_fixture:
                if not path:
                  continue
                if path[0] != "__getitem__":
                  continue
                if len(path) == 1:
                  direct_alias = alias
                  continue
                trimmed_paths.append((path[1:], alias))
              if trimmed_paths:
                return tuple(trimmed_paths)
              if direct_alias is not None:
                return direct_alias
        if isinstance(dynamic_fixture, str):
          return dynamic_fixture
      constructor_name = self._resolve_constructor_name(node.value)
      if constructor_name is not None:
        dynamic_fixture = self._dynamic_class_accessors.get(constructor_name)
        if dynamic_fixture is not None:
          return dynamic_fixture
        alias_target = self._alias_map.get(constructor_name)
        if alias_target is not None:
          dynamic_fixture = self._dynamic_class_accessors.get(alias_target)
          if dynamic_fixture is not None:
            return dynamic_fixture
      slice_node = node.slice
      if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
        alias_target = self._alias_map.get(slice_node.value)
        if alias_target is not None:
          return alias_target
        matched_fixture, _ = self._match_fixture(slice_node.value)
        if matched_fixture is not None:
          return matched_fixture
      if isinstance(slice_node, ast.Index):  # pragma: no cover - py311 compat
        index_value = slice_node.value
        if isinstance(index_value, ast.Constant) and isinstance(index_value.value, str):
          alias_target = self._alias_map.get(index_value.value)
          if alias_target is not None:
            return alias_target
          matched_fixture, _ = self._match_fixture(index_value.value)
          if matched_fixture is not None:
            return matched_fixture
    if isinstance(node, ast.Call):
      wrapper_target = self._resolve_wrapped_fixture(node)
      if wrapper_target is not None:
        return wrapper_target
    if isinstance(node, ast.Lambda):
      return self._resolve_name(node.body)
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
      for element in node.elts:
        fixture_name = self._resolve_name(element)
        if fixture_name is not None:
          return fixture_name
      return None
    if isinstance(node, ast.Dict):
      for value in node.values:
        if value is None:
          continue
        fixture_name = self._resolve_name(value)
        if fixture_name is not None:
          return fixture_name
      return None
    return None

  def _extract_dotted_name(self, node: ast.Attribute) -> str | None:
    parts: list[str] = [node.attr]
    value = node.value
    while isinstance(value, ast.Attribute):
      parts.append(value.attr)
      value = value.value
    if isinstance(value, ast.Name):
      parts.append(value.id)
      parts.reverse()
      return ".".join(parts)
    return None

  def _extract_subscript_key(self, node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
      return node.value
    if isinstance(node, ast.Index):  # pragma: no cover - py311 compat
      return self._extract_subscript_key(node.value)
    return None

  def _extract_subscript_index(self, node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
      return node.value
    if isinstance(node, ast.Index):  # pragma: no cover - py311 compat
      return self._extract_subscript_index(node.value)
    return None

  def _resolve_parent_chain(self, node: ast.AST, steps: int) -> DynamicFixture | None:
    def _trim_path(path: DynamicPath) -> tuple[DynamicPath, bool]:
      remaining = list(path)
      consumed = 0
      index = 0
      while consumed < steps and index < len(remaining):
        segment = remaining[index]
        if segment == "parent":
          del remaining[index]
          consumed += 1
          continue
        if (
          segment == "parents"
          and index + 1 < len(remaining)
          and remaining[index + 1] == "__getitem__"
        ):
          del remaining[index : index + 2]
          consumed += 1
          continue
        index += 1
      if consumed != steps:
        return path, False
      return tuple(remaining), True

    if steps <= 0:
      return self._resolve_dynamic_instance(node) or self._resolve_name(node)

    dynamic_parent = self._resolve_dynamic_instance(node)
    if dynamic_parent is not None:
      if isinstance(dynamic_parent, tuple):
        trimmed_paths: list[tuple[DynamicPath, str]] = []
        direct_alias: str | None = None
        for path, alias in dynamic_parent:
          trimmed_path, matched = _trim_path(path)
          if not matched:
            continue
          if not trimmed_path:
            direct_alias = alias
            continue
          trimmed_paths.append((trimmed_path, alias))
        if trimmed_paths:
          return tuple(trimmed_paths)
        if direct_alias is not None:
          return direct_alias
      else:
        return dynamic_parent

    base_parent = self._resolve_name(node)
    if isinstance(base_parent, tuple):
      trimmed_paths = []
      direct_alias: str | None = None
      for path, alias in base_parent:
        trimmed_path, matched = _trim_path(path)
        if not matched:
          continue
        if not trimmed_path:
          direct_alias = alias
          continue
        trimmed_paths.append((trimmed_path, alias))
      if trimmed_paths:
        return tuple(trimmed_paths)
      if direct_alias is not None:
        return direct_alias
    if isinstance(base_parent, str):
      return base_parent
    return None

  def _resolve_wrapped_fixture(self, node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Call):
      inner_target = self._resolve_wrapped_fixture(node.func)
      if inner_target is not None:
        return inner_target

    callee_name = self._resolve_wrapper_name(node.func)
    if callee_name is None:
      callee_name = self._resolve_constructor_name(node.func)
      if callee_name is None:
        return None

    if callee_name.endswith("partial") or callee_name.endswith("partialmethod"):
      if node.args:
        return self._resolve_name(node.args[0])
      for keyword in node.keywords:
        if keyword.arg in {"func", None} and keyword.value is not None:
          return self._resolve_name(keyword.value)
      return None

    if callee_name.endswith("getattr"):
      attribute = None if len(node.args) < 2 else node.args[1]
      if attribute is None:
        for keyword in node.keywords:
          if keyword.arg in {"name", "attr"} and keyword.value is not None:
            attribute = keyword.value
            break
      if attribute is None:
        return None
      if isinstance(attribute, ast.Constant) and isinstance(attribute.value, str):
        return self._alias_map.get(attribute.value)
      return None

    if callee_name.endswith("MethodType"):
      if not node.args:
        return None
      return self._resolve_name(node.args[0])

    if callee_name.endswith("wraps"):
      if not node.args:
        return None
      return self._resolve_name(node.args[0])

    if callee_name.endswith("update_wrapper"):
      if len(node.args) > 1:
        return self._resolve_name(node.args[1])
      for keyword in node.keywords:
        if keyword.arg == "wrapped" and keyword.value is not None:
          return self._resolve_name(keyword.value)
      return None

    if callee_name.endswith("cached_property") or callee_name.endswith("property"):
      if node.args:
        return self._resolve_name(node.args[0])
      for keyword in node.keywords:
        if keyword.arg in {"fget", None} and keyword.value is not None:
          return self._resolve_name(keyword.value)
      return None

    if callee_name.endswith("classmethod") or callee_name.endswith("staticmethod"):
      if node.args:
        return self._resolve_name(node.args[0])
      for keyword in node.keywords:
        if keyword.arg in {"function", "func"} and keyword.value is not None:
          return self._resolve_name(keyword.value)
      return None

    if (
      callee_name.endswith("nullcontext")
      or callee_name.endswith("closing")
      or callee_name.endswith("aclosing")
    ):
      if node.args:
        return self._resolve_name(node.args[0])
      for keyword in node.keywords:
        if keyword.value is not None:
          fixture_name = self._resolve_name(keyword.value)
          if fixture_name is not None:
            return fixture_name
      return None

    if callee_name.endswith("enter_context") or callee_name.endswith(
      "enter_async_context"
    ):
      for argument in node.args:
        fixture_name = self._resolve_name(argument)
        if fixture_name is not None:
          return fixture_name
      for keyword in node.keywords:
        if keyword.value is None:
          continue
        fixture_name = self._resolve_name(keyword.value)
        if fixture_name is not None:
          return fixture_name
      return None

    if (
      callee_name.endswith("push")
      or callee_name.endswith("push_async_callback")
      or callee_name.endswith("push_async_exit")
    ):
      for argument in node.args:
        fixture_name = self._resolve_name(argument)
        if fixture_name is not None:
          return fixture_name
      for keyword in node.keywords:
        if keyword.value is None:
          continue
        fixture_name = self._resolve_name(keyword.value)
        if fixture_name is not None:
          return fixture_name
      return None

    if callee_name.endswith("callback"):
      if node.args:
        return self._resolve_name(node.args[0])
      for keyword in node.keywords:
        if keyword.value is not None:
          fixture_name = self._resolve_name(keyword.value)
          if fixture_name is not None:
            return fixture_name
      return None

    if callee_name.endswith("select") or callee_name.endswith("get"):
      for keyword in node.keywords:
        if (
          keyword.arg in {"name", "key"}
          and isinstance(keyword.value, ast.Constant)
          and isinstance(keyword.value.value, str)
        ):
          fixture_name = self._alias_map.get(keyword.value.value)
          if fixture_name is not None:
            return fixture_name
          matched_fixture, _ = self._match_fixture(keyword.value.value)
          if matched_fixture is not None:
            return matched_fixture
      if node.args:
        candidate = node.args[0]
        if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
          fixture_name = self._alias_map.get(candidate.value)
          if fixture_name is not None:
            return fixture_name
          matched_fixture, _ = self._match_fixture(candidate.value)
          if matched_fixture is not None:
            return matched_fixture
      return None

    if callee_name.endswith("files"):
      dynamic_fixture = self._resolve_dynamic_constructor(node)
      if dynamic_fixture is not None:
        return dynamic_fixture
      return None

    if callee_name.endswith("find_loader"):
      dynamic_fixture = self._resolve_dynamic_constructor(node)
      if dynamic_fixture is not None:
        return dynamic_fixture
      return None

    if callee_name.endswith("find_spec"):
      dynamic_fixture = self._resolve_dynamic_constructor(node)
      if dynamic_fixture is not None:
        return dynamic_fixture
      return None

    if callee_name.endswith(("load", "load_module", "get_code")):
      if not isinstance(node.func, ast.Attribute):
        return None
      base_fixture = self._resolve_name(node.func.value)
      if base_fixture is not None:
        return base_fixture
      return None

    if callee_name.endswith("joinpath"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("with_suffix") or callee_name.endswith("with_name"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("with_segments"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("with_stem"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("relative_to"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("resolve"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("read_text"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("open_text"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("open"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("invalidate_caches"):
      fixture = self._resolve_name(node.func)
      if fixture is not None:
        return fixture
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("exec_module"):
      dynamic_fixture = self._resolve_dynamic_constructor(node)
      if dynamic_fixture is not None:
        return dynamic_fixture
      module_node: ast.AST | None = None
      if node.args:
        module_node = node.args[0]
      if module_node is None:
        for keyword in node.keywords:
          if keyword.arg in {None, "module"} and keyword.value is not None:
            module_node = keyword.value
            break
      if module_node is not None:
        dynamic_fixture = self._resolve_dynamic_instance(module_node)
        if dynamic_fixture is not None:
          return dynamic_fixture
        fixture_name = self._resolve_name(module_node)
        if fixture_name is not None:
          return fixture_name
      fixture_name = self._resolve_name(node.func)
      if fixture_name is not None:
        return fixture_name
      if isinstance(node.func, ast.Attribute):
        dynamic_fixture = self._resolve_dynamic_instance(node.func.value)
        if dynamic_fixture is not None:
          return dynamic_fixture
      return None

    if callee_name.endswith("field"):
      if node.args:
        fixture_name = self._resolve_name(node.args[0])
        if fixture_name is not None:
          return fixture_name
      for keyword in node.keywords:
        if keyword.value is None:
          continue
        if keyword.arg in {"default", "default_factory"}:
          fixture_name = self._resolve_name(keyword.value)
          if fixture_name is not None:
            return fixture_name
      return None

    if callee_name.endswith("make_dataclass"):
      for argument in node.args[1:]:
        fixture_name = self._resolve_name(argument)
        if fixture_name is not None:
          return fixture_name
      for keyword in node.keywords:
        if keyword.value is None:
          continue
        fixture_name = self._resolve_name(keyword.value)
        if fixture_name is not None:
          return fixture_name
      return None
    if callee_name.endswith("resolve_name"):
      target_node: ast.AST | None = None
      if node.args:
        target_node = node.args[0]
      else:
        for keyword in node.keywords:
          if keyword.arg in {None, "fullname", "name"} and keyword.value is not None:
            target_node = keyword.value
            break
      if isinstance(target_node, ast.Constant) and isinstance(target_node.value, str):
        lookup = target_node.value.split(":")[-1].split(".")[-1]
        alias_target = self._alias_map.get(lookup)
        if alias_target is not None:
          return alias_target
        matched_fixture, _ = self._match_fixture(lookup)
        if matched_fixture is not None:
          return matched_fixture
      return None

    return None

  def _resolve_wrapper_name(self, node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
      return self._resolve_wrapper_name(node.func)
    if isinstance(node, ast.Name):
      name = node.id
      if name in {
        "partial",
        "partialmethod",
        "getattr",
        "MethodType",
        "ModuleType",
        "wraps",
        "update_wrapper",
        "property",
        "cached_property",
        "classmethod",
        "staticmethod",
        "contextmanager",
        "asynccontextmanager",
        "nullcontext",
        "closing",
        "aclosing",
        "select",
        "get",
        "entry_points",
        "resolve_name",
        "get_importer",
        "get_loader",
        "find_loader",
        "find_spec",
        "files",
        "field",
        "make_dataclass",
        "SimpleNamespace",
        "ModuleSpec",
        "module_from_spec",
        "zipimporter",
        "contents",
        "open_binary",
        "open_file",
        "open_text",
        "read_text",
        "open",
        "get_data",
        "read_binary",
        "load_module",
        "get_code",
        "find_module",
        "joinpath",
        "with_suffix",
        "with_name",
        "with_stem",
        "relative_to",
        "exec_module",
        "run_module",
        "run_path",
      }:
        return name
      alias_target = self._wrapper_aliases.get(name)
      if alias_target in {
        "partial",
        "partialmethod",
        "getattr",
        "MethodType",
        "ModuleType",
        "wraps",
        "update_wrapper",
        "cached_property",
        "contextmanager",
        "asynccontextmanager",
        "nullcontext",
        "closing",
        "aclosing",
        "entry_points",
        "resolve_name",
        "get_importer",
        "get_loader",
        "find_loader",
        "find_spec",
        "files",
        "get_data",
        "field",
        "make_dataclass",
        "SimpleNamespace",
        "ModuleSpec",
        "module_from_spec",
        "zipimporter",
        "contents",
        "open_binary",
        "open_file",
        "open_text",
        "read_text",
        "open",
        "load_module",
        "get_code",
        "read_binary",
        "find_module",
        "joinpath",
        "with_suffix",
        "with_name",
        "with_stem",
        "relative_to",
        "exec_module",
        "invalidate_caches",
        "run_module",
        "run_path",
      }:
        return alias_target
      return None
    if isinstance(node, ast.Attribute):
      if node.attr in {
        "partial",
        "partialmethod",
        "getattr",
        "wraps",
        "update_wrapper",
        "property",
        "cached_property",
        "classmethod",
        "staticmethod",
        "nullcontext",
        "closing",
        "aclosing",
        "ModuleType",
        "resolve_name",
        "enter_context",
        "enter_async_context",
        "push",
        "push_async_callback",
        "push_async_exit",
        "callback",
        "select",
        "get",
        "load",
        "load_module",
        "get_source",
        "open_binary",
        "open_file",
        "open_text",
        "get_data",
        "get_loader",
        "find_loader",
        "find_spec",
        "files",
        "field",
        "get_code",
        "read_binary",
        "find_module",
        "joinpath",
        "read_text",
        "open",
        "with_suffix",
        "with_name",
        "with_stem",
        "relative_to",
        "invalidate_caches",
        "exec_module",
        "run_module",
        "run_path",
      }:
        return node.attr
      dotted = self._extract_dotted_name(node)
      if dotted is None:
        return None
      if dotted.endswith("partial") or dotted.endswith("partialmethod"):
        return dotted
      if dotted.endswith("getattr"):
        return dotted
      if dotted.endswith("property") or dotted.endswith("cached_property"):
        return dotted
      if dotted.endswith("classmethod") or dotted.endswith("staticmethod"):
        return dotted
      if (
        dotted.endswith("nullcontext")
        or dotted.endswith("closing")
        or dotted.endswith("aclosing")
      ):
        return dotted
      if dotted.endswith("select") or dotted.endswith("get"):
        return dotted
      if dotted.endswith("entry_points"):
        return dotted
      if dotted.endswith("contents"):
        return dotted
      if dotted.endswith("files"):
        return dotted
      if dotted.endswith("open_binary"):
        return dotted
      if dotted.endswith("open_file"):
        return dotted
      if dotted.endswith("open_text"):
        return dotted
      if dotted.endswith("read_text"):
        return dotted
      if dotted.endswith("get_data"):
        return dotted
      if dotted.endswith("get_loader"):
        return dotted
      if dotted.endswith("find_loader"):
        return dotted
      if dotted.endswith("find_spec"):
        return dotted
      if dotted.endswith("read_binary"):
        return dotted
      if dotted.endswith("field"):
        return dotted
      if dotted.endswith("make_dataclass"):
        return dotted
      if dotted.endswith("joinpath"):
        return dotted
      if dotted.endswith("with_suffix"):
        return dotted
      if dotted.endswith("with_name"):
        return dotted
      if dotted.endswith("with_stem"):
        return dotted
      if dotted.endswith("with_segments"):
        return dotted
      if dotted.endswith("relative_to"):
        return dotted
      if dotted.endswith("resolve"):
        return dotted
      if dotted.endswith("open"):
        return dotted
      if dotted.endswith("SimpleNamespace"):
        return dotted
      if dotted.endswith("ModuleSpec"):
        return dotted
      if dotted.endswith("module_from_spec"):
        return dotted
      if dotted.endswith("ModuleType"):
        return dotted
      if dotted.endswith("resolve_name"):
        return dotted
      if dotted.endswith("get_importer"):
        return dotted
      if dotted.endswith("zipimporter"):
        return dotted
      if dotted.endswith("get_source"):
        return dotted
      if dotted.endswith("get_code"):
        return dotted
      if dotted.endswith("load_module"):
        return dotted
      if dotted.endswith("find_module"):
        return dotted
      if dotted.endswith("invalidate_caches"):
        return dotted
      if dotted.endswith("exec_module"):
        return dotted
      if dotted.endswith("find_spec"):
        return dotted
      if dotted.endswith("run_module"):
        return dotted
      if dotted.endswith("run_path"):
        return dotted
      base_name = self._resolve_attribute_base(node)
      if base_name is not None:
        alias_target = self._wrapper_aliases.get(base_name)
        if alias_target == "functools" and node.attr == "partial":
          return "functools.partial"
        if alias_target == "functools" and node.attr == "partialmethod":
          return "functools.partialmethod"
        if alias_target == "types" and node.attr == "MethodType":
          return "types.MethodType"
        if alias_target == "functools" and node.attr == "wraps":
          return "functools.wraps"
        if alias_target == "functools" and node.attr == "update_wrapper":
          return "functools.update_wrapper"
        if alias_target == "functools" and node.attr == "cached_property":
          return "functools.cached_property"
        if alias_target == "types" and node.attr == "ModuleType":
          return "types.ModuleType"
        if alias_target == "importlib" and node.attr == "resources":
          return "importlib.resources"
        if alias_target == "importlib" and node.attr == "invalidate_caches":
          return "importlib.invalidate_caches"
        if alias_target == "importlib.resources" and node.attr in {
          "files",
          "as_file",
          "read_text",
          "contents",
          "open_binary",
          "open_file",
          "open_text",
          "read_binary",
        }:
          return f"importlib.resources.{node.attr}"
        if alias_target == "importlib.metadata" and node.attr == "entry_points":
          return "importlib.metadata.entry_points"
        if alias_target == "importlib" and node.attr == "import_module":
          return "importlib.import_module"
        if alias_target == "contextlib" and node.attr == "contextmanager":
          return "contextlib.contextmanager"
        if alias_target == "contextlib" and node.attr == "asynccontextmanager":
          return "contextlib.asynccontextmanager"
        if alias_target == "contextlib" and node.attr == "nullcontext":
          return "contextlib.nullcontext"
        if alias_target == "contextlib" and node.attr == "closing":
          return "contextlib.closing"
        if alias_target == "contextlib" and node.attr == "aclosing":
          return "contextlib.aclosing"
        if alias_target == "dataclasses" and node.attr == "field":
          return "dataclasses.field"
        if alias_target == "dataclasses" and node.attr == "make_dataclass":
          return "dataclasses.make_dataclass"
        if alias_target == "types" and node.attr == "SimpleNamespace":
          return "types.SimpleNamespace"
        if alias_target == "pkgutil" and node.attr == "resolve_name":
          return "pkgutil.resolve_name"
        if alias_target == "pkgutil" and node.attr == "get_importer":
          return "pkgutil.get_importer"
        if alias_target == "pkgutil" and node.attr == "get_loader":
          return "pkgutil.get_loader"
        if alias_target == "pkgutil" and node.attr == "find_loader":
          return "pkgutil.find_loader"
        if alias_target == "pkgutil" and node.attr == "find_spec":
          return "pkgutil.find_spec"
        if alias_target == "pkgutil" and node.attr == "get_data":
          return "pkgutil.get_data"
        if alias_target == "runpy" and node.attr == "run_module":
          return "runpy.run_module"
        if alias_target == "runpy" and node.attr == "run_path":
          return "runpy.run_path"
        if alias_target == "zipimport" and node.attr == "zipimporter":
          return "zipimport.zipimporter"
        if alias_target == "zipimporter" and node.attr == "load_module":
          return "zipimporter.load_module"
        if alias_target == "zipimport.zipimporter" and node.attr == "load_module":
          return "zipimport.zipimporter.load_module"
        if alias_target == "zipimporter" and node.attr == "get_code":
          return "zipimporter.get_code"
        if alias_target == "zipimporter" and node.attr == "find_module":
          return "zipimporter.find_module"
        if alias_target == "zipimporter" and node.attr == "find_loader":
          return "zipimporter.find_loader"
        if alias_target == "zipimporter" and node.attr == "find_spec":
          return "zipimporter.find_spec"
        if alias_target == "zipimporter" and node.attr == "invalidate_caches":
          return "zipimporter.invalidate_caches"
        if alias_target == "zipimport.zipimporter" and node.attr == "get_code":
          return "zipimport.zipimporter.get_code"
        if alias_target == "zipimport.zipimporter" and node.attr == "find_module":
          return "zipimport.zipimporter.find_module"
        if alias_target == "zipimport.zipimporter" and node.attr == "find_loader":
          return "zipimport.zipimporter.find_loader"
        if alias_target == "zipimport.zipimporter" and node.attr == "find_spec":
          return "zipimport.zipimporter.find_spec"
        if alias_target == "zipimport.zipimporter" and node.attr == "invalidate_caches":
          return "zipimport.zipimporter.invalidate_caches"
        if alias_target == "importlib.machinery" and node.attr == "ModuleSpec":
          return "importlib.machinery.ModuleSpec"
        if alias_target == "importlib.util" and node.attr == "module_from_spec":
          return "importlib.util.module_from_spec"
      if dotted.endswith("wraps"):
        return dotted
      if dotted.endswith("update_wrapper"):
        return dotted
      if dotted.endswith("enter_context"):
        return dotted
      if dotted.endswith("enter_async_context"):
        return dotted
      if dotted.endswith("push"):
        return dotted
      if dotted.endswith("push_async_callback"):
        return dotted
      if dotted.endswith("push_async_exit"):
        return dotted
      if dotted.endswith("callback"):
        return dotted
      if dotted.endswith("import_module"):
        return dotted
      if dotted.endswith("files"):
        return dotted
      if dotted.endswith("entry_points"):
        return dotted
      if dotted.endswith("contents"):
        return dotted
      if dotted.endswith("open_binary"):
        return dotted
      if dotted.endswith("open_file"):
        return dotted
      if dotted.endswith("open_text"):
        return dotted
      if dotted.endswith("read_text"):
        return dotted
      if dotted.endswith("get_data"):
        return dotted
      if dotted.endswith("get_loader"):
        return dotted
      if dotted.endswith("read_binary"):
        return dotted
      if dotted.endswith("get_importer"):
        return dotted
      if dotted.endswith("zipimporter"):
        return dotted
      if dotted.endswith("get_source"):
        return dotted
      if dotted.endswith("get_code"):
        return dotted
      if dotted.endswith("load_module"):
        return dotted
      if dotted.endswith("find_module"):
        return dotted
      if dotted.endswith("find_spec"):
        return dotted
      if dotted.endswith("field"):
        return dotted
      if dotted.endswith("make_dataclass"):
        return dotted
      if dotted.endswith("SimpleNamespace"):
        return dotted
      if dotted.endswith("ModuleSpec"):
        return dotted
      if dotted.endswith("module_from_spec"):
        return dotted
      if dotted.endswith("ModuleType"):
        return dotted
      if dotted.endswith("resolve_name"):
        return dotted
      if dotted.endswith("run_module"):
        return dotted
      if dotted.endswith("run_path"):
        return dotted
    return None

  def _has_contextmanager_decorator(
    self, node: ast.FunctionDef | ast.AsyncFunctionDef
  ) -> bool:
    for decorator in node.decorator_list:
      decorator_name = self._resolve_wrapper_name(decorator)
      if decorator_name is None:
        continue
      base_name = decorator_name.rsplit(".", 1)[-1]
      if base_name in {"contextmanager", "asynccontextmanager"}:
        return True
    return False

  def _resolve_attribute_base(self, node: ast.Attribute) -> str | None:
    value = node.value
    while isinstance(value, ast.Attribute):
      value = value.value
    if isinstance(value, ast.Name):
      return value.id
    return None

  def _record_alias(self, node: ast.AST, fixture_name: str) -> None:
    if isinstance(node, ast.Name):
      self._alias_map[node.id] = fixture_name
    elif isinstance(node, ast.Attribute):
      dotted = self._extract_dotted_name(node)
      if dotted is not None:
        self._alias_map[dotted] = fixture_name
      self._alias_map[node.attr] = fixture_name
    elif isinstance(node, ast.Tuple | ast.List):
      for element in node.elts:
        self._record_alias(element, fixture_name)

  def _record_descriptor_return(
    self, node: ast.FunctionDef | ast.AsyncFunctionDef
  ) -> None:
    if not node.decorator_list:
      return
    for decorator in node.decorator_list:
      decorator_name = self._resolve_wrapper_name(decorator)
      if decorator_name not in {
        "property",
        "cached_property",
        "functools.cached_property",
        "classmethod",
        "staticmethod",
      }:
        continue
      fixture_name = self._find_descriptor_fixture(node)
      if fixture_name is not None:
        self._alias_map[node.name] = fixture_name
        if self._class_stack and node.name == "__class_getitem__":
          self._dynamic_class_accessors[self._class_stack[-1]] = fixture_name
        break

  def _record_function_return(
    self, node: ast.FunctionDef | ast.AsyncFunctionDef
  ) -> None:
    include_expressions = self._has_contextmanager_decorator(node)
    fixture_name = self._descriptor_fixture_from_block(
      node.body, include_expressions=include_expressions
    )
    if fixture_name is not None:
      self._alias_map[node.name] = fixture_name
      if self._class_stack and node.name in {
        "__getattr__",
        "__getattribute__",
        "__class_getitem__",
      }:
        self._dynamic_class_accessors[self._class_stack[-1]] = fixture_name
      return
    dynamic_fixture = self._dynamic_fixture_from_block(node.body)
    if dynamic_fixture is None:
      return
    if isinstance(dynamic_fixture, tuple):
      self._register_dynamic_function_return(node, dynamic_fixture)
      if self._class_stack and node.name in {
        "__getattr__",
        "__getattribute__",
        "__class_getitem__",
      }:
        self._dynamic_class_accessors[self._class_stack[-1]] = next(
          (alias for path, alias in dynamic_fixture if not path),
          dynamic_fixture[0][1],
        )
      return
    if self._class_stack and node.name in {
      "__getattr__",
      "__getattribute__",
      "__class_getitem__",
    }:
      self._dynamic_class_accessors[self._class_stack[-1]] = dynamic_fixture
      return
    if self._class_stack and node.name == "create_module":
      self._dynamic_class_accessors[self._class_stack[-1]] = dynamic_fixture
    self._register_dynamic_function_return(node, (((), dynamic_fixture),))

  def _register_dynamic_function_return(
    self,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    mapping: tuple[tuple[DynamicPath, str], ...],
  ) -> None:
    key = self._qualify_function_name(node.name)
    merged: dict[DynamicPath, str] = {}
    existing = self._dynamic_function_returns.get(key)
    if existing is not None:
      merged.update({path: alias for path, alias in existing})
    merged.update({path: alias for path, alias in mapping})
    self._dynamic_function_returns[key] = tuple(merged.items())

  def _qualify_function_name(self, name: str) -> str:
    if self._class_stack:
      return ".".join((*self._class_stack, name))
    return name

  def _find_descriptor_fixture(
    self, node: ast.FunctionDef | ast.AsyncFunctionDef
  ) -> str | None:
    return self._descriptor_fixture_from_block(node.body)

  def _descriptor_fixture_from_block(
    self,
    block: list[ast.stmt],
    *,
    local_aliases: dict[str, str] | None = None,
    include_expressions: bool = True,
  ) -> str | None:
    aliases = {} if local_aliases is None else local_aliases
    for statement in block:
      fixture_name = self._descriptor_fixture_from_statement(
        statement, aliases, include_expressions=include_expressions
      )
      if fixture_name is not None:
        return fixture_name
    return None

  def _descriptor_fixture_from_statement(
    self,
    statement: ast.stmt,
    local_aliases: dict[str, str],
    *,
    include_expressions: bool,
  ) -> str | None:
    if isinstance(statement, ast.Return):
      if statement.value is None:
        return None
      return self._resolve_descriptor_name(statement.value, local_aliases)
    if isinstance(statement, ast.Expr):
      if isinstance(statement.value, ast.Yield | ast.YieldFrom):
        return self._resolve_descriptor_name(statement.value, local_aliases)
      if not include_expressions:
        return None
      return self._resolve_descriptor_name(statement.value, local_aliases)
    if isinstance(statement, ast.If):
      fixture_name = self._descriptor_fixture_from_block(
        statement.body,
        local_aliases=local_aliases.copy(),
        include_expressions=include_expressions,
      )
      if fixture_name is not None:
        return fixture_name
      return self._descriptor_fixture_from_block(
        statement.orelse,
        local_aliases=local_aliases.copy(),
        include_expressions=include_expressions,
      )
    if isinstance(statement, ast.With | ast.AsyncWith):
      return self._descriptor_fixture_from_block(
        statement.body,
        local_aliases=local_aliases,
        include_expressions=include_expressions,
      )
    if isinstance(statement, ast.Try):
      fixture_name = self._descriptor_fixture_from_block(
        statement.body,
        local_aliases=local_aliases.copy(),
        include_expressions=include_expressions,
      )
      if fixture_name is not None:
        return fixture_name
      for handler in statement.handlers:
        handler_fixture = self._descriptor_fixture_from_block(
          handler.body,
          local_aliases=local_aliases.copy(),
          include_expressions=include_expressions,
        )
        if handler_fixture is not None:
          return handler_fixture
      fixture_name = self._descriptor_fixture_from_block(
        statement.orelse,
        local_aliases=local_aliases.copy(),
        include_expressions=include_expressions,
      )
      if fixture_name is not None:
        return fixture_name
      return self._descriptor_fixture_from_block(
        statement.finalbody,
        local_aliases=local_aliases.copy(),
        include_expressions=include_expressions,
      )
    if isinstance(statement, ast.For | ast.AsyncFor | ast.While):
      fixture_name = self._descriptor_fixture_from_block(
        statement.body,
        local_aliases=local_aliases.copy(),
        include_expressions=include_expressions,
      )
      if fixture_name is not None:
        return fixture_name
      return self._descriptor_fixture_from_block(
        statement.orelse,
        local_aliases=local_aliases.copy(),
        include_expressions=include_expressions,
      )
    if isinstance(statement, ast.Assign):
      fixture_name = self._resolve_descriptor_name(statement.value, local_aliases)
      if fixture_name is not None:
        for target in statement.targets:
          if isinstance(target, ast.Name):
            local_aliases[target.id] = fixture_name
      return None
    if isinstance(statement, ast.AnnAssign):
      if statement.value is not None:
        fixture_name = self._resolve_descriptor_name(statement.value, local_aliases)
        if fixture_name is not None and isinstance(statement.target, ast.Name):
          local_aliases[statement.target.id] = fixture_name
      return None
    return None

  def _resolve_descriptor_name(
    self, node: ast.AST, local_aliases: dict[str, str]
  ) -> str | None:
    if isinstance(node, ast.Name) and node.id in local_aliases:
      return local_aliases[node.id]
    fixture_name = self._resolve_name(node)
    if fixture_name is not None:
      return fixture_name
    if isinstance(node, ast.Yield | ast.YieldFrom):
      if node.value is None:
        return None
      return self._resolve_descriptor_name(node.value, local_aliases)
    if isinstance(node, ast.Name):
      return local_aliases.get(node.id)
    return None

  def _record_dynamic_alias(self, node: ast.AST, fixture: DynamicFixture) -> None:
    if isinstance(node, ast.Tuple | ast.List):
      for element in node.elts:
        self._record_dynamic_alias(element, fixture)
      return
    if isinstance(fixture, tuple):
      bases = self._collect_target_bases(node)
      if not bases:
        return
      for base in bases:
        path_map = self._dynamic_attribute_paths.setdefault(base, {})
        for path, alias in fixture:
          path_map[path] = alias
          self._register_dynamic_path(base, path, alias)
      return
    if isinstance(node, ast.Name):
      self._dynamic_attribute_aliases[node.id] = fixture
    elif isinstance(node, ast.Attribute):
      dotted = self._extract_dotted_name(node)
      if dotted is not None:
        self._dynamic_attribute_aliases[dotted] = fixture
      self._dynamic_attribute_aliases[node.attr] = fixture
    elif isinstance(node, ast.Subscript):
      key_node = node.slice
      if isinstance(key_node, ast.Index):  # pragma: no cover - py311 compat
        key_node = key_node.value
      if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
        return
      bases = self._collect_target_bases(node)
      if not bases:
        return
      path = (key_node.value,)
      for base in bases:
        path_map = self._dynamic_attribute_paths.setdefault(base, {})
        path_map[path] = fixture
        self._register_dynamic_path(base, path, fixture)

  def _collect_target_bases(self, node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
      return [node.id]
    if isinstance(node, ast.Attribute):
      bases: list[str] = []
      dotted = self._extract_dotted_name(node)
      if dotted is not None:
        bases.append(dotted)
      bases.extend(self._collect_target_bases(node.value))
      return list(dict.fromkeys(bases))
    if isinstance(node, ast.Subscript):
      return self._collect_target_bases(node.value)
    return []

  def _register_dynamic_path(self, base: str, path: DynamicPath, alias: str) -> None:
    dotted = ".".join((base, *path)) if path else base
    self._alias_map[dotted] = alias
    self._dynamic_attribute_aliases[dotted] = alias
    if len(path) > 1:
      intermediate_base = ".".join((base, path[0]))
      nested_path = path[1:]
      nested_map = self._dynamic_attribute_paths.setdefault(intermediate_base, {})
      nested_map[nested_path] = alias
      self._register_dynamic_path(intermediate_base, nested_path, alias)

  def _resolve_dynamic_base(self, node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
      fixture_name = self._dynamic_attribute_aliases.get(node.id)
      if fixture_name is not None:
        return fixture_name
      fixture_name = self._dynamic_class_accessors.get(node.id)
      if fixture_name is not None:
        return fixture_name
      alias_target = self._alias_map.get(node.id)
      if alias_target is not None:
        return self._dynamic_class_accessors.get(alias_target)
      return None
    if isinstance(node, ast.Attribute):
      dotted = self._extract_dotted_name(node)
      if dotted is not None:
        fixture_name = self._dynamic_attribute_aliases.get(dotted)
        if fixture_name is not None:
          return fixture_name
      fixture_name = self._dynamic_class_accessors.get(node.attr)
      if fixture_name is not None:
        return fixture_name
      dynamic_base = self._resolve_dynamic_base(node.value)
      if dynamic_base is not None:
        return dynamic_base
      constructor_name = self._resolve_constructor_name(node)
      if constructor_name is not None:
        fixture_name = self._dynamic_class_accessors.get(constructor_name)
        if fixture_name is not None:
          return fixture_name
      return None
    if isinstance(node, ast.Call):
      return self._resolve_dynamic_constructor(node)
    return None

  def _resolve_dynamic_instance(self, node: ast.AST) -> DynamicFixture | None:
    if isinstance(node, ast.Call):
      fixture_name = self._resolve_dynamic_constructor(node)
      if fixture_name is not None:
        return fixture_name
    if isinstance(node, ast.Name):
      path_map = self._dynamic_attribute_paths.get(node.id)
      if path_map:
        return tuple(path_map.items())
      fixture_name = self._dynamic_attribute_aliases.get(node.id)
      if fixture_name is not None:
        return fixture_name
      fixture_name = self._dynamic_class_accessors.get(node.id)
      if fixture_name is not None:
        return fixture_name
      function_mapping = self._dynamic_function_returns.get(node.id)
      if function_mapping is not None:
        return function_mapping
      alias_target = self._alias_map.get(node.id)
      if alias_target is not None:
        mapping = self._dynamic_function_returns.get(alias_target)
        if mapping is not None:
          return mapping
        return self._dynamic_class_accessors.get(alias_target)
      return None
    if isinstance(node, ast.Attribute):
      dotted = self._extract_dotted_name(node)
      if dotted is not None:
        path_map = self._dynamic_attribute_paths.get(dotted)
        if path_map:
          return tuple(path_map.items())
        fixture_name = self._dynamic_attribute_aliases.get(dotted)
        if fixture_name is not None:
          return fixture_name
        mapping = self._dynamic_function_returns.get(dotted)
        if mapping is not None:
          return mapping
      fixture_name = self._dynamic_class_accessors.get(node.attr)
      if fixture_name is not None:
        return fixture_name
      mapping = self._dynamic_function_returns.get(node.attr)
      if mapping is not None:
        return mapping
      dynamic_fixture = self._resolve_dynamic_instance(node.value)
      if dynamic_fixture is not None:
        return dynamic_fixture
      constructor_name = self._resolve_constructor_name(node)
      if constructor_name is not None:
        fixture_name = self._dynamic_class_accessors.get(constructor_name)
        if fixture_name is not None:
          return fixture_name
        mapping = self._dynamic_function_returns.get(constructor_name)
        if mapping is not None:
          return mapping
      return None
    return None

  def _resolve_dynamic_constructor(self, node: ast.Call) -> DynamicFixture | None:
    constructor_name = self._resolve_constructor_name(node.func)
    if constructor_name is None:
      return None
    path_map = self._dynamic_attribute_paths.get(constructor_name)
    if path_map:
      return tuple(path_map.items())
    fixture_name = self._dynamic_attribute_aliases.get(constructor_name)
    if fixture_name is not None:
      return fixture_name
    mapping = self._dynamic_function_returns.get(constructor_name)
    if mapping is not None:
      return mapping
    fixture_name = self._dynamic_class_accessors.get(constructor_name)
    if fixture_name is not None:
      return fixture_name
    alias_target = self._alias_map.get(constructor_name)
    if alias_target is not None:
      path_map = self._dynamic_attribute_paths.get(alias_target)
      if path_map:
        return tuple(path_map.items())
      fixture_name = self._dynamic_attribute_aliases.get(alias_target)
      if fixture_name is not None:
        return fixture_name
      mapping = self._dynamic_function_returns.get(alias_target)
      if mapping is not None:
        return mapping
      return self._dynamic_class_accessors.get(alias_target)
    if constructor_name.endswith("SimpleNamespace"):
      paths: list[tuple[DynamicPath, str]] = []
      for keyword in node.keywords:
        if keyword.arg is None or keyword.value is None:
          continue
        paths.extend(self._namespace_paths_from_value(keyword.value, (keyword.arg,)))
      for argument in node.args:
        if not isinstance(argument, ast.Dict):
          continue
        for key, value in zip(argument.keys, argument.values, strict=False):
          if (
            key is None
            or not isinstance(key, ast.Constant)
            or not isinstance(key.value, str)
          ):
            continue
          paths.extend(self._namespace_paths_from_value(value, (key.value,)))
      if paths:
        return tuple(paths)
      return None
    if constructor_name.endswith("ModuleSpec"):
      loader_node: ast.AST | None = None
      if len(node.args) >= 2:
        loader_node = node.args[1]
      for keyword in node.keywords:
        if keyword.arg == "loader" and keyword.value is not None:
          loader_node = keyword.value
      if loader_node is None:
        return None
      loader_paths = self._namespace_paths_from_value(loader_node, ("loader",))
      if loader_paths:
        return tuple(loader_paths)
      return None
    if constructor_name.endswith("run_module") or constructor_name.endswith("run_path"):
      init_globals_node: ast.AST | None = None
      arg_index = 1 if constructor_name.endswith("run_module") else 2
      if len(node.args) > arg_index:
        init_globals_node = node.args[arg_index]
      for keyword in node.keywords:
        if keyword.arg == "init_globals" and keyword.value is not None:
          init_globals_node = keyword.value
          break
      path_map: dict[DynamicPath, str] = {}
      if init_globals_node is not None:
        for path, alias in self._mapping_paths(init_globals_node):
          path_map.setdefault(path, alias)
      for fixture_name in FORBIDDEN_FIXTURE_CALLS:
        path_map.setdefault((fixture_name,), fixture_name)
      if path_map:
        return tuple(path_map.items())
      return None
    if constructor_name.endswith("create_module"):
      path_map: dict[DynamicPath, str] = {}
      for argument in node.args:
        for path, alias in self._mapping_paths(argument):
          path_map.setdefault(path, alias)
      for keyword in node.keywords:
        if keyword.value is None:
          continue
        prefix: DynamicPath = () if keyword.arg is None else (keyword.arg,)
        for path, alias in self._mapping_paths(keyword.value, prefix=prefix):
          path_map.setdefault(path, alias)
      if path_map:
        return tuple(path_map.items())
      return None
    if constructor_name.endswith("module_from_spec"):
      spec_node: ast.AST | None = None
      if node.args:
        spec_node = node.args[0]
      else:
        for keyword in node.keywords:
          if keyword.arg == "spec" and keyword.value is not None:
            spec_node = keyword.value
            break
      if spec_node is None:
        return None
      spec_fixture = self._resolve_dynamic_instance(spec_node)
      if isinstance(spec_fixture, tuple):
        module_paths: list[tuple[DynamicPath, str]] = []
        for path, alias in spec_fixture:
          if not path:
            module_paths.append(((), alias))
            continue
          if path[0] != "loader":
            continue
          if len(path) == 1:
            module_paths.append(((), alias))
            continue
          if path[1] == "create_module":
            remainder = path[2:]
            if remainder:
              module_paths.append((remainder, alias))
            else:
              module_paths.append(((), alias))
        if module_paths:
          return tuple(module_paths)
        return None
      if isinstance(spec_fixture, str):
        return spec_fixture
      fixture_name = self._resolve_name(spec_node)
      if fixture_name is not None:
        return fixture_name
      return None
    if constructor_name.endswith("getattr"):
      attribute_node: ast.AST | None = None
      if node.args and len(node.args) >= 2:
        attribute_node = node.args[1]
      if attribute_node is None:
        for keyword in node.keywords:
          if keyword.arg in {"name", "attr"}:
            attribute_node = keyword.value
            break
      if isinstance(attribute_node, ast.Constant) and isinstance(
        attribute_node.value, str
      ):
        fixture_name = self._dynamic_class_accessors.get(attribute_node.value)
        if fixture_name is not None:
          return fixture_name
        alias_target = self._alias_map.get(attribute_node.value)
        if alias_target is not None:
          return self._dynamic_class_accessors.get(alias_target)
    class_name = constructor_name.rsplit(".", 1)[-1]
    method_paths: list[tuple[DynamicPath, str]] = []
    for qualname, mapping in self._dynamic_function_returns.items():
      if qualname.startswith(f"{constructor_name}.") or qualname.startswith(
        f"{class_name}."
      ):
        method = qualname.rsplit(".", 1)[-1]
        for path, alias in mapping:
          method_paths.append(((method, *path), alias))
    if method_paths:
      return tuple(method_paths)
    return None

  def _namespace_paths_from_value(
    self, value: ast.AST, prefix: DynamicPath
  ) -> list[tuple[DynamicPath, str]]:
    fixture_name = self._resolve_name(value)
    if fixture_name is not None:
      return [(prefix, fixture_name)]
    dynamic_fixture = self._resolve_dynamic_instance(value)
    if dynamic_fixture is None:
      return []
    if isinstance(dynamic_fixture, tuple):
      return [(prefix + sub_path, alias) for sub_path, alias in dynamic_fixture]
    return [(prefix, dynamic_fixture)]

  def _mapping_paths(
    self, node: ast.AST, *, prefix: DynamicPath = ()
  ) -> list[tuple[DynamicPath, str]]:
    if isinstance(node, ast.Dict):
      paths: list[tuple[DynamicPath, str]] = []
      for key, value in zip(node.keys, node.values, strict=False):
        if (
          key is None
          or not isinstance(key, ast.Constant)
          or not isinstance(key.value, str)
        ):
          continue
        paths.extend(self._namespace_paths_from_value(value, (*prefix, key.value)))
      return paths
    return self._namespace_paths_from_value(node, prefix)

  def _resolve_constructor_name(self, node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
      return self._resolve_constructor_name(node.func)
    if isinstance(node, ast.Subscript):
      base_constructor = self._resolve_constructor_name(node.value)
      if base_constructor is not None:
        return f"{base_constructor}.__getitem__"
      return None
    if isinstance(node, ast.Name):
      alias_target = self._wrapper_aliases.get(node.id)
      if alias_target is not None:
        return alias_target
      return node.id
    if isinstance(node, ast.Attribute):
      dotted = self._extract_dotted_name(node)
      if dotted is not None:
        parts = dotted.split(".")
        if parts:
          alias_target = self._wrapper_aliases.get(parts[0])
          if alias_target is not None:
            remainder = ".".join(parts[1:])
            if remainder:
              return f"{alias_target}.{remainder}"
            return alias_target
        return dotted
      base_constructor = self._resolve_constructor_name(node.value)
      if base_constructor is not None:
        return f"{base_constructor}.{node.attr}"
      return self._resolve_constructor_name(node.value)
    return None

  def _dynamic_fixture_from_block(self, block: list[ast.stmt]) -> DynamicFixture | None:
    for statement in block:
      fixture_name = self._dynamic_fixture_from_statement(statement)
      if fixture_name is not None:
        return fixture_name
    return None

  def _dynamic_fixture_from_statement(
    self, statement: ast.stmt
  ) -> DynamicFixture | None:
    if isinstance(statement, ast.Return):
      if statement.value is None:
        return None
      if isinstance(statement.value, ast.Call):
        return self._resolve_dynamic_constructor(statement.value)
      fixture_name = self._resolve_dynamic_instance(statement.value)
      if fixture_name is not None:
        return fixture_name
      return self._resolve_name(statement.value)
    if isinstance(statement, ast.Expr):
      expr_value = statement.value
      if isinstance(expr_value, ast.Call):
        return self._resolve_dynamic_constructor(expr_value)
      if isinstance(expr_value, ast.Yield | ast.YieldFrom):
        if expr_value.value is None:
          return None
        if isinstance(expr_value.value, ast.Call):
          return self._resolve_dynamic_constructor(expr_value.value)
        return self._resolve_name(expr_value.value)
    if isinstance(statement, ast.If):
      fixture_name = self._dynamic_fixture_from_block(statement.body)
      if fixture_name is not None:
        return fixture_name
      return self._dynamic_fixture_from_block(statement.orelse)
    if isinstance(statement, ast.Try):
      fixture_name = self._dynamic_fixture_from_block(statement.body)
      if fixture_name is not None:
        return fixture_name
      for handler in statement.handlers:
        handler_fixture = self._dynamic_fixture_from_block(handler.body)
        if handler_fixture is not None:
          return handler_fixture
      fixture_name = self._dynamic_fixture_from_block(statement.orelse)
      if fixture_name is not None:
        return fixture_name
      return self._dynamic_fixture_from_block(statement.finalbody)
    return None

  def _flag(self, node: ast.AST, fixture_name: str, message: str) -> None:
    entry = f"{self._path}:{node.lineno} - {fixture_name}: {message}"
    if entry in self.offenders:
      return
    self.offenders.append(entry)


def _scan_source(source: str) -> list[str]:
  tree = ast.parse(source, filename="inline.py")
  visitor = _FixtureUsageVisitor(path=Path("inline.py"))
  visitor.visit(tree)
  return visitor.offenders


def test_detects_partial_wrapped_fixture() -> None:
  """Flag helpers created via functools.partial wrappers."""

  offenders = _scan_source(
    "from functools import partial\nclient = partial(hass_client, hass)\nclient()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_client" in offender for offender in offenders)


def test_detects_partialmethod_wrapped_fixture() -> None:
  """Flag helpers created via functools.partialmethod wrappers."""

  offenders = _scan_source(
    "from functools import partialmethod\n"
    "class Helper:\n"
    "    client = partialmethod(hass_client, hass)\n"
    "Helper().client()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_client" in offender for offender in offenders)


def test_detects_getattr_fixture_wrapper() -> None:
  """Flag getattr-based wrappers that forward to forbidden fixtures."""

  offenders = _scan_source(
    "helper = getattr(pytestconfig, 'hass_ws_client')\nhelper()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_ws_client" in offender for offender in offenders)


def test_detects_methodtype_wrapped_fixture() -> None:
  """Flag types.MethodType wrappers that forward fixture calls."""

  offenders = _scan_source(
    "from types import MethodType\n"
    "class Helper:\n"
    "    pass\n"
    "helper = Helper()\n"
    "helper.client = MethodType(hass_client, helper)\n"
    "helper.client()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_client" in offender for offender in offenders)


def test_detects_admin_websocket_fixture_invocation() -> None:
  """Detect direct invocations of the admin websocket fixture."""

  offenders = _scan_source("hass_admin_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_admin_ws_client" in offenders[0]


def test_detects_lambda_wrapped_fixture() -> None:
  """Flag lambda wrappers that forward fixture invocations."""

  offenders = _scan_source(
    "client = lambda *args, **kwargs: hass_client(*args, **kwargs)\nclient()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_supervisor_http_fixture_invocation() -> None:
  """Detect direct invocations of the supervisor HTTP client fixture."""

  offenders = _scan_source("hass_supervisor_client()\n")

  assert len(offenders) == 1
  assert "hass_supervisor_client" in offenders[0]


def test_detects_supervisor_websocket_fixture_invocation() -> None:
  """Detect direct invocations of the supervisor websocket fixture."""

  offenders = _scan_source("hass_supervisor_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_supervisor_ws_client" in offenders[0]


def test_detects_supervisor_admin_websocket_fixture_invocation() -> None:
  """Detect direct invocations of the supervisor admin websocket fixture."""

  offenders = _scan_source("hass_supervisor_admin_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_supervisor_admin_ws_client" in offenders[0]


def test_detects_aiohttp_server_fixture_invocation() -> None:
  """Detect direct invocations of the aiohttp test server fixture."""

  offenders = _scan_source("aiohttp_server()\n")

  assert len(offenders) == 1
  assert "aiohttp_server" in offenders[0]


def test_detects_unauthenticated_http_fixture_invocation() -> None:
  """Detect direct invocations of the unauthenticated HTTP fixture."""

  offenders = _scan_source("hass_client_no_auth()\n")

  assert len(offenders) == 1
  assert "hass_client_no_auth" in offenders[0]


def test_detects_admin_http_fixture_invocation() -> None:
  """Detect direct invocations of the admin HTTP fixture."""

  offenders = _scan_source("hass_client_admin()\n")

  assert len(offenders) == 1
  assert "hass_client_admin" in offenders[0]


def test_detects_mobile_app_http_fixture_invocation() -> None:
  """Detect direct invocations of the mobile app HTTP fixture."""

  offenders = _scan_source("hass_mobile_app_client()\n")

  assert len(offenders) == 1
  assert "hass_mobile_app_client" in offenders[0]


def test_detects_mobile_app_websocket_fixture_invocation() -> None:
  """Detect direct invocations of the mobile app websocket fixture."""

  offenders = _scan_source("hass_mobile_app_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_mobile_app_ws_client" in offenders[0]


def test_detects_companion_http_fixture_invocation() -> None:
  """Detect direct invocations of the companion HTTP client fixture."""

  offenders = _scan_source("hass_companion_client()\n")

  assert len(offenders) == 1
  assert "hass_companion_client" in offenders[0]


def test_detects_companion_websocket_fixture_invocation() -> None:
  """Detect direct invocations of the companion websocket client fixture."""

  offenders = _scan_source("hass_companion_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_companion_ws_client" in offenders[0]


def test_detects_companion_prefix_fixture_invocation() -> None:
  """Detect new companion fixtures registered via prefix matching."""

  offenders = _scan_source("hass_companion_voice_client()\n")

  assert len(offenders) == 1
  assert "hass_companion_voice_client" in offenders[0]


def test_detects_update_wrapper_alias() -> None:
  """Flag fixtures wrapped via functools.update_wrapper."""

  offenders = _scan_source(
    "from functools import update_wrapper\n"
    "def helper(*args, **kwargs):\n"
    "    return args, kwargs\n"
    "client = update_wrapper(helper, hass_client)\n"
    "client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_wraps_decorator_alias() -> None:
  """Flag fixtures wrapped via functools.wraps decorator factories."""

  offenders = _scan_source(
    "from functools import wraps\n"
    "client = wraps(hass_client)(lambda *args, **kwargs: None)\n"
    "client(None)\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_property_descriptor_wrapper() -> None:
  """Flag property descriptors returning forbidden fixtures."""

  offenders = _scan_source(
    "class Helper:\n"
    "    client = property(lambda self: hass_ws_client)\n"
    "Helper().client()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_ws_client" in offender for offender in offenders)


def test_detects_property_descriptor_local_alias() -> None:
  """Flag descriptor returns that alias fixtures before yielding them."""

  offenders = _scan_source(
    "class Helper:\n"
    "    @property\n"
    "    def client(self):\n"
    "        fixture = hass_client\n"
    "        return fixture\n"
    "Helper().client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_cached_property_decorator_wrapper() -> None:
  """Flag cached_property descriptors returning forbidden fixtures."""

  offenders = _scan_source(
    "from functools import cached_property\n"
    "class Helper:\n"
    "    @cached_property\n"
    "    def client(self):\n"
    "        return hass_client\n"
    "Helper().client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_cached_property_nested_alias() -> None:
  """Flag cached_property descriptors that alias fixtures via temporaries."""

  offenders = _scan_source(
    "from functools import cached_property\n"
    "class Helper:\n"
    "    @cached_property\n"
    "    def client(self):\n"
    "        helper = hass_client\n"
    "        return helper\n"
    "Helper().client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_entry_point_fixture_loader() -> None:
  """Detect fixtures resolved dynamically via importlib entry points."""

  offenders = _scan_source(
    "from importlib.metadata import entry_points\n"
    "client = entry_points(group='ha.test').get('hass_owner_ws_client').load()\n"
    "client()\n"
  )

  assert len(offenders) == 1
  assert "hass_owner_ws_client" in offenders[0]


def test_detects_entry_point_select_loader() -> None:
  """Detect fixtures pulled from entry point selections by name."""

  offenders = _scan_source(
    "from importlib.metadata import entry_points\n"
    "client = entry_points(group='ha.test').select(name='hass_client_admin').load()\n"
    "client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client_admin" in offenders[0]


def test_detects_entry_point_subscript_loader() -> None:
  """Detect fixtures retrieved via subscription off entry point mappings."""

  offenders = _scan_source(
    "from importlib.metadata import entry_points\n"
    "entry_points(group='ha.test')['hass_client']()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_pkgutil_resolve_name_fixture() -> None:
  """Detect fixtures loaded dynamically via pkgutil.resolve_name."""

  offenders = _scan_source(
    "from pkgutil import resolve_name\n"
    "client = resolve_name('tests.helpers:hass_voice_assistant_client')\n"
    "client()\n"
  )

  assert len(offenders) == 1
  assert "hass_voice_assistant_client" in offenders[0]


def test_detects_simple_namespace_fixture_alias() -> None:
  """Detect fixtures stored on SimpleNamespace helpers."""

  offenders = _scan_source(
    "from types import SimpleNamespace\n"
    "helper = SimpleNamespace(client=hass_client)\n"
    "helper.client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_nested_simple_namespace_fixture_alias() -> None:
  """Detect fixtures exposed through nested SimpleNamespace containers."""

  offenders = _scan_source(
    "from types import SimpleNamespace\n"
    "spec = SimpleNamespace(loader=SimpleNamespace(create_module=hass_ws_client))\n"
    "spec.loader.create_module()\n"
  )

  assert len(offenders) == 1
  assert "hass_ws_client" in offenders[0]


def test_detects_simple_namespace_exec_module_loader() -> None:
  """Detect fixtures returned from SimpleNamespace exec_module loaders."""

  offenders = _scan_source(
    "from types import SimpleNamespace\n"
    "def _exec_module(module):\n"
    "    return SimpleNamespace(client=hass_owner_ws_client)\n"
    "spec = SimpleNamespace(loader=SimpleNamespace(exec_module=_exec_module))\n"
    "module = spec.loader.exec_module(SimpleNamespace())\n"
    "module.client()\n"
  )

  assert any("hass_owner_ws_client" in offender for offender in offenders)


def test_detects_module_spec_loader_fixture_alias() -> None:
  """Detect fixtures wired through ModuleSpec loader helpers."""

  offenders = _scan_source(
    "from importlib.machinery import ModuleSpec\n"
    "from types import SimpleNamespace\n"
    "spec = ModuleSpec('helper', SimpleNamespace(create_module=hass_client_admin))\n"
    "spec.loader.create_module()\n"
  )

  assert len(offenders) == 1
  assert "hass_client_admin" in offenders[0]


def test_detects_module_spec_loader_exec_module_alias() -> None:
  """Detect fixtures exposed through ModuleSpec exec_module helpers."""

  offenders = _scan_source(
    "from importlib.machinery import ModuleSpec\n"
    "from types import SimpleNamespace\n"
    "def _exec_module(module):\n"
    "    return SimpleNamespace(client=hass_companion_ws_client)\n"
    "spec = ModuleSpec('helper', SimpleNamespace(exec_module=_exec_module))\n"
    "module = spec.loader.exec_module(SimpleNamespace())\n"
    "module.client()\n"
  )

  assert any("hass_companion_ws_client" in offender for offender in offenders)


def test_detects_module_from_spec_attribute_fixture_alias() -> None:
  """Detect fixtures returned from module_from_spec loader factories."""

  offenders = _scan_source(
    "from importlib.util import module_from_spec\n"
    "from types import SimpleNamespace\n"
    "spec = SimpleNamespace(\n"
    "    loader=SimpleNamespace(\n"
    "        create_module=SimpleNamespace(client=hass_owner_ws_client)\n"
    "    )\n"
    ")\n"
    "module = module_from_spec(spec)\n"
    "module.client()\n"
  )

  assert len(offenders) == 1
  assert "hass_owner_ws_client" in offenders[0]


def test_detects_module_from_spec_exec_module_loader() -> None:
  """Detect fixtures returned via module_from_spec followed by exec_module."""

  offenders = _scan_source(
    "from importlib.util import module_from_spec\n"
    "from types import SimpleNamespace\n"
    "def _create_module(spec):\n"
    "    return SimpleNamespace()\n"
    "def _exec_module(module):\n"
    "    return SimpleNamespace(client=hass_supervisor_ws_client)\n"
    "spec = SimpleNamespace(\n"
    "    loader=SimpleNamespace(create_module=_create_module, exec_module=_exec_module)\n"
    ")\n"
    "module = module_from_spec(spec)\n"
    "module = spec.loader.exec_module(module)\n"
    "module.client()\n"
  )

  assert any("hass_supervisor_ws_client" in offender for offender in offenders)


def test_detects_module_type_update_fixture_alias() -> None:
  """Detect fixtures exposed through ModuleType dictionaries."""

  offenders = _scan_source(
    "from types import ModuleType\n"
    "module = ModuleType('helpers')\n"
    "module.__dict__.update(client=hass_supervisor_client)\n"
    "module.client()\n"
  )

  assert any(
    offender.startswith("inline.py:4") and "hass_supervisor_client" in offender
    for offender in offenders
  )


def test_detects_module_type_update_from_mapping() -> None:
  """Detect fixtures injected into ModuleType via external mappings."""

  offenders = _scan_source(
    "payload = {}\n"
    "payload['client'] = hass_client\n"
    "from types import ModuleType\n"
    "module = ModuleType('helpers')\n"
    "module.__dict__.update(payload)\n"
    "module.client()\n"
  )

  assert any(
    offender.startswith("inline.py:6") and "hass_client" in offender
    for offender in offenders
  )


def test_detects_module_type_setdefault_fixture_alias() -> None:
  """Detect fixtures exposed via ModuleType.setdefault aliases."""

  offenders = _scan_source(
    "from types import ModuleType\n"
    "module = ModuleType('helpers')\n"
    "module.__dict__.setdefault('client', hass_voice_assistant_client)\n"
    "module.client()\n"
  )

  assert any(
    offender.startswith("inline.py:4") and "hass_voice_assistant_client" in offender
    for offender in offenders
  )


def test_detects_exec_module_setdefault_fixture_alias() -> None:
  """Detect fixtures registered via exec_module callbacks using setdefault."""

  offenders = _scan_source(
    "from importlib.util import module_from_spec\n"
    "from types import SimpleNamespace\n"
    "def _create_module(spec):\n"
    "    return SimpleNamespace()\n"
    "def _exec_module(module):\n"
    "    module.__dict__.setdefault('client', hass_owner_ws_client)\n"
    "spec = SimpleNamespace(\n"
    "    loader=SimpleNamespace(create_module=_create_module, exec_module=_exec_module)\n"
    ")\n"
    "module = module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
    "module.client()\n"
  )

  assert any("hass_owner_ws_client" in offender for offender in offenders)


def test_detects_pkgutil_iter_modules_spec_loader() -> None:
  """Detect fixtures returned through pkgutil iter_modules loaders."""

  offenders = _scan_source(
    "from pkgutil import iter_modules\n"
    "from types import SimpleNamespace\n"
    "for finder, name, _ in iter_modules():\n"
    "    spec = finder.find_spec(name)\n"
    "    module = spec.loader.create_module(SimpleNamespace(client=hass_client))\n"
    "    module.client()\n"
  )

  assert any("hass_client" in offender for offender in offenders)


def test_detects_pkgutil_get_data_loader() -> None:
  """Detect fixtures returned through pkgutil.get_data loaders."""

  offenders = _scan_source(
    "import pkgutil\n"
    "from types import SimpleNamespace\n"
    "def _get_data(package: str, resource: str):\n"
    "    return SimpleNamespace(client=hass_owner_ws_client)\n"
    "pkgutil.get_data = _get_data\n"
    "module = pkgutil.get_data('tests.helpers', 'client.py')\n"
    "module.client()\n"
  )

  assert any("hass_owner_ws_client" in offender for offender in offenders)


def test_detects_pkgutil_get_loader_loader_chain() -> None:
  """Detect fixtures returned through pkgutil.get_loader loaders."""

  offenders = _scan_source(
    "import pkgutil\n"
    "from types import SimpleNamespace\n"
    "def load_module(name: str):\n"
    "    return SimpleNamespace(client=hass_voice_assistant_ws_client)\n"
    "def get_loader(name: str):\n"
    "    return SimpleNamespace(load_module=load_module)\n"
    "pkgutil.get_loader = get_loader\n"
    "module = pkgutil.get_loader('tests.helpers').load_module('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_voice_assistant_ws_client" in offender for offender in offenders)


def test_detects_pkgutil_find_loader_loader_chain() -> None:
  """Detect fixtures returned through pkgutil.find_loader loaders."""

  offenders = _scan_source(
    "import pkgutil\n"
    "from types import SimpleNamespace\n"
    "def load_module(name: str):\n"
    "    return SimpleNamespace(client=hass_owner_ws_client)\n"
    "def find_loader(name: str):\n"
    "    return SimpleNamespace(load_module=load_module)\n"
    "pkgutil.find_loader = find_loader\n"
    "module = pkgutil.find_loader('tests.helpers').load_module('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_owner_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_as_file_loader_chain() -> None:
  """Detect fixtures loaded via importlib.resources.as_file context managers."""

  offenders = _scan_source(
    "from importlib.resources import files, as_file\n"
    "from importlib.util import module_from_spec\n"
    "from types import SimpleNamespace\n"
    "with as_file(files('tests.helpers') / 'helper.py'):\n"
    "    spec = SimpleNamespace(\n"
    "        loader=SimpleNamespace(\n"
    "            create_module=SimpleNamespace(client=hass_ws_client)\n"
    "        )\n"
    "    )\n"
    "module = module_from_spec(spec)\n"
    "module.client()\n"
  )

  assert len(offenders) == 1
  assert "hass_ws_client" in offenders[0]


def test_detects_importlib_resources_open_binary_loader() -> None:
  """Detect fixtures returned via importlib.resources.open_binary wrappers."""

  offenders = _scan_source(
    "from importlib.resources import open_binary\n"
    "from types import SimpleNamespace\n"
    "def _open_binary(package: str, resource: str):\n"
    "    return SimpleNamespace(client=hass_client)\n"
    "open_binary = _open_binary\n"
    "module = open_binary('tests.helpers', 'client.bin')\n"
    "module.client()\n"
  )

  assert any("hass_client" in offender for offender in offenders)


def test_detects_importlib_resources_open_file_loader() -> None:
  """Detect fixtures yielded via importlib.resources.open_file wrappers."""

  offenders = _scan_source(
    "from importlib.resources import open_file\n"
    "from contextlib import contextmanager\n"
    "from types import SimpleNamespace\n"
    "@contextmanager\n"
    "def _open_file(package: str, resource: str):\n"
    "    yield SimpleNamespace(client=hass_voice_assistant_client)\n"
    "open_file = _open_file\n"
    "with open_file('tests.helpers', 'client.bin') as module:\n"
    "    module.client()\n"
  )

  assert any("hass_voice_assistant_client" in offender for offender in offenders)


def test_detects_importlib_resources_joinpath_open_loader() -> None:
  """Detect fixtures returned via importlib.resources.files joinpath open wrappers."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_supervisor_ws_client)\n"
    "resource = SimpleNamespace(open=_open)\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return resource\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client.py').open().client()\n"
  )

  assert any("hass_supervisor_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_joinpath_read_text_loader() -> None:
  """Detect fixtures returned via importlib.resources.files joinpath read_text wrappers."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _read_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_companion_client)\n"
    "resource = SimpleNamespace(read_text=_read_text)\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return resource\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client.py').read_text().client()\n"
  )

  assert any("hass_companion_client" in offender for offender in offenders)


def test_detects_importlib_resources_read_binary_loader() -> None:
  """Detect fixtures returned via importlib.resources.read_binary wrappers."""

  offenders = _scan_source(
    "from importlib.resources import read_binary\n"
    "def _read_binary(package: str, resource: str):\n"
    "    return hass_supervisor_client\n"
    "read_binary = _read_binary\n"
    "module = read_binary('tests.helpers', 'client.bin')\n"
    "module()\n"
  )

  assert any("hass_supervisor_client" in offender for offender in offenders)


def test_detects_importlib_resources_open_text_loader() -> None:
  """Detect fixtures returned via importlib.resources.open_text wrappers."""

  offenders = _scan_source(
    "from importlib.resources import open_text\n"
    "from types import SimpleNamespace\n"
    "def _open_text(package: str, resource: str):\n"
    "    return SimpleNamespace(client=hass_owner_ws_client)\n"
    "open_text = _open_text\n"
    "module = open_text('tests.helpers', 'client.txt')\n"
    "module.client()\n"
  )

  assert any("hass_owner_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_with_suffix_open_text_loader() -> None:
  """Detect fixtures returned via files().joinpath().with_suffix().open_text()."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_voice_assistant_ws_client)\n"
    "resource = SimpleNamespace(open_text=_open_text)\n"
    "def _with_suffix(_: str) -> SimpleNamespace:\n"
    "    return resource\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(with_suffix=_with_suffix)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client').with_suffix('.txt').open_text().client()\n"
  )

  assert any("hass_voice_assistant_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_with_name_open_text_loader() -> None:
  """Detect fixtures returned via files().joinpath().with_name().open_text()."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_client)\n"
    "resource = SimpleNamespace(open_text=_open_text)\n"
    "def _with_name(_: str) -> SimpleNamespace:\n"
    "    return resource\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(with_name=_with_name)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client').with_name('client.yaml').open_text().client()\n"
  )

  assert any("hass_client" in offender for offender in offenders)


def test_detects_importlib_resources_with_stem_open_text_loader() -> None:
  """Detect fixtures returned via files().joinpath().with_stem().open_text()."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_supervisor_client)\n"
    "resource = SimpleNamespace(open_text=_open_text)\n"
    "def _with_stem(_: str) -> SimpleNamespace:\n"
    "    return resource\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(with_stem=_with_stem)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client').with_stem('client').open_text().client()\n"
  )

  assert any("hass_supervisor_client" in offender for offender in offenders)


def test_detects_importlib_resources_with_segments_open_text_loader() -> None:
  """Detect fixtures returned via files().joinpath().with_segments().open_text."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_companion_ws_client)\n"
    "resource = SimpleNamespace(open_text=_open_text)\n"
    "def _with_segments(*segments: str) -> SimpleNamespace:\n"
    "    return resource\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(with_segments=_with_segments)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client').with_segments('data', 'client.txt').open_text().client()\n"
  )

  assert any("hass_companion_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_resolve_open_text_loader() -> None:
  """Detect fixtures returned via files().joinpath().resolve().open_text."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_supervisor_admin_ws_client)\n"
    "resource = SimpleNamespace(open_text=_open_text)\n"
    "def _resolve(strict: bool = False) -> SimpleNamespace:\n"
    "    return resource\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(resolve=_resolve)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client').resolve().open_text().client()\n"
  )

  assert any("hass_supervisor_admin_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_parent_joinpath_loader() -> None:
  """Detect fixtures returned via files().joinpath().parent.joinpath().open_text."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_supervisor_ws_client)\n"
    "def _inner_joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(open_text=_open_text)\n"
    "parent_resource = SimpleNamespace(joinpath=_inner_joinpath)\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(parent=parent_resource)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('helpers').parent.joinpath('client').open_text().client()\n"
  )

  assert any("hass_supervisor_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_parents_index_joinpath_loader() -> None:
  """Detect fixtures returned via files().joinpath().parents[0].joinpath()."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_companion_ws_client)\n"
    "def _inner_joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(open_text=_open_text)\n"
    "def _get_parent(index: int) -> SimpleNamespace:\n"
    "    return SimpleNamespace(joinpath=_inner_joinpath)\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    parent_seq = SimpleNamespace(__getitem__=_get_parent)\n"
    "    return SimpleNamespace(parents=parent_seq)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('helpers').parents[0].joinpath('client').open_text().client()\n"
  )

  assert any("hass_companion_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_parents_nested_joinpath_loader() -> None:
  """Detect fixtures returned via files().joinpath().parents[2].joinpath()."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_owner_ws_client)\n"
    "def _inner_joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(open_text=_open_text)\n"
    "def _get_parent(index: int) -> SimpleNamespace:\n"
    "    return SimpleNamespace(joinpath=_inner_joinpath)\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    parent_seq = SimpleNamespace(__getitem__=_get_parent)\n"
    "    return SimpleNamespace(parents=parent_seq)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('helpers').parents[2].joinpath('client').open_text().client()\n"
  )

  assert any("hass_owner_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_parents_with_segments_loader() -> None:
  """Detect fixtures returned via parents[index].with_segments().open_text."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_supervisor_admin_ws_client)\n"
    "def _inner_with_segments(*segments: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(open_text=_open_text)\n"
    "def _get_parent(index: int) -> SimpleNamespace:\n"
    "    return SimpleNamespace(with_segments=_inner_with_segments)\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    parent_seq = SimpleNamespace(__getitem__=_get_parent)\n"
    "    return SimpleNamespace(parents=parent_seq)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('helpers').parents[1].with_segments('client', 'payload.json').open_text().client()\n"
  )

  assert any("hass_supervisor_admin_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_parents_resolve_joinpath_loader() -> None:
  """Detect fixtures returned via parents[index].resolve().joinpath().open_text."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_voice_assistant_ws_client)\n"
    "def _inner_joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(open_text=_open_text)\n"
    "def _resolve(strict: bool = False) -> SimpleNamespace:\n"
    "    return SimpleNamespace(joinpath=_inner_joinpath)\n"
    "def _get_parent(index: int) -> SimpleNamespace:\n"
    "    return SimpleNamespace(resolve=_resolve)\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    parent_seq = SimpleNamespace(__getitem__=_get_parent)\n"
    "    return SimpleNamespace(parents=parent_seq)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('helpers').parents[0].resolve().joinpath('client').open_text().client()\n"
  )

  assert any("hass_voice_assistant_ws_client" in offender for offender in offenders)


def test_detects_importlib_resources_relative_to_open_text_loader() -> None:
  """Detect fixtures returned via files().joinpath().relative_to().open_text()."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "from types import SimpleNamespace\n"
    "def _open_text() -> SimpleNamespace:\n"
    "    return SimpleNamespace(client=hass_voice_assistant_client)\n"
    "resource = SimpleNamespace(open_text=_open_text)\n"
    "def _relative_to(_: str) -> SimpleNamespace:\n"
    "    return resource\n"
    "def _joinpath(name: str) -> SimpleNamespace:\n"
    "    return SimpleNamespace(relative_to=_relative_to)\n"
    "def get_files(package: str):\n"
    "    return SimpleNamespace(joinpath=_joinpath)\n"
    "files = get_files\n"
    "files('tests.helpers').joinpath('client').relative_to('tests.helpers').open_text().client()\n"
  )

  assert any("hass_voice_assistant_client" in offender for offender in offenders)


def test_detects_importlib_resources_contents_loader_chain() -> None:
  """Detect fixtures retrieved through importlib.resources.contents loaders."""

  offenders = _scan_source(
    "from importlib.resources import contents\n"
    "from importlib import import_module\n"
    "from types import SimpleNamespace\n"
    "def _load_module(name: str):\n"
    "    return SimpleNamespace(client=hass_voice_assistant_client)\n"
    "def _contents(package: str) -> tuple[str, ...]:\n"
    "    return ('helper',)\n"
    "import_module = _load_module\n"
    "contents = _contents\n"
    "for helper in contents('tests.helpers'):\n"
    "    module = import_module(f'tests.helpers.{helper}')\n"
    "    module.client()\n"
  )

  assert any("hass_voice_assistant_client" in offender for offender in offenders)


def test_detects_zipimporter_loaded_fixture() -> None:
  """Detect fixtures exposed through zipimporter module loaders."""

  offenders = _scan_source(
    "import zipimport\n"
    "importer = zipimport.zipimporter('helpers.zip')\n"
    "getattr(importer.load_module('tests.conftest'), 'hass_mobile_app_ws_client')()\n"
  )

  assert len(offenders) == 1
  assert "hass_mobile_app_ws_client" in offenders[0]


def test_detects_zipimporter_load_module_loader() -> None:
  """Detect fixtures returned through zipimporter.load_module loaders."""

  offenders = _scan_source(
    "import zipimport\n"
    "from types import SimpleNamespace\n"
    "def load_module(name: str):\n"
    "    return SimpleNamespace(client=hass_voice_assistant_client)\n"
    "def zip_loader(path: str):\n"
    "    return SimpleNamespace(load_module=load_module)\n"
    "zipimport.zipimporter = zip_loader\n"
    "module = zipimport.zipimporter('helpers.zip').load_module('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_voice_assistant_client" in offender for offender in offenders)


def test_detects_zipimporter_get_source_loader() -> None:
  """Detect fixtures returned through zipimporter.get_source loaders."""

  offenders = _scan_source(
    "import zipimport\n"
    "from types import SimpleNamespace\n"
    "def get_source(name: str):\n"
    "    return SimpleNamespace(client=hass_voice_assistant_ws_client)\n"
    "def zip_loader(path: str):\n"
    "    return SimpleNamespace(get_source=get_source)\n"
    "zipimport.zipimporter = zip_loader\n"
    "module = zipimport.zipimporter('helpers.zip').get_source('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_voice_assistant_ws_client" in offender for offender in offenders)


def test_detects_zipimporter_get_code_loader() -> None:
  """Detect fixtures returned through zipimporter.get_code loaders."""

  offenders = _scan_source(
    "import zipimport\n"
    "from types import SimpleNamespace\n"
    "def get_code(name: str):\n"
    "    return SimpleNamespace(client=hass_companion_ws_client)\n"
    "def zip_loader(path: str):\n"
    "    return SimpleNamespace(get_code=get_code)\n"
    "zipimport.zipimporter = zip_loader\n"
    "module = zipimport.zipimporter('helpers.zip').get_code('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_companion_ws_client" in offender for offender in offenders)


def test_detects_zipimporter_find_module_loader() -> None:
  """Detect fixtures returned through zipimporter.find_module loaders."""

  offenders = _scan_source(
    "import zipimport\n"
    "from types import SimpleNamespace\n"
    "def find_module(name: str):\n"
    "    return SimpleNamespace(client=hass_voice_assistant_ws_client)\n"
    "def zip_loader(path: str):\n"
    "    return SimpleNamespace(find_module=find_module)\n"
    "zipimport.zipimporter = zip_loader\n"
    "module = zipimport.zipimporter('helpers.zip').find_module('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_voice_assistant_ws_client" in offender for offender in offenders)


def test_detects_zipimporter_find_loader_loader() -> None:
  """Detect fixtures returned through zipimporter.find_loader loaders."""

  offenders = _scan_source(
    "import zipimport\n"
    "from types import SimpleNamespace\n"
    "def load_module(name: str):\n"
    "    return SimpleNamespace(client=hass_voice_assistant_client)\n"
    "def find_loader(name: str):\n"
    "    return SimpleNamespace(load_module=load_module)\n"
    "def zip_loader(path: str):\n"
    "    return SimpleNamespace(find_loader=find_loader)\n"
    "zipimport.zipimporter = zip_loader\n"
    "module = zipimport.zipimporter('helpers.zip').find_loader('tests.helpers').load_module('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_voice_assistant_client" in offender for offender in offenders)


def test_detects_zipimporter_find_spec_loader() -> None:
  """Detect fixtures returned through zipimporter.find_spec loaders."""

  offenders = _scan_source(
    "import zipimport\n"
    "from types import SimpleNamespace\n"
    "def create_module(spec):\n"
    "    return SimpleNamespace(client=hass_voice_assistant_ws_client)\n"
    "def find_spec(name: str):\n"
    "    loader = SimpleNamespace(create_module=create_module)\n"
    "    return SimpleNamespace(loader=loader)\n"
    "def zip_loader(path: str):\n"
    "    return SimpleNamespace(find_spec=find_spec)\n"
    "zipimport.zipimporter = zip_loader\n"
    "spec = zipimport.zipimporter('helpers.zip').find_spec('tests.helpers')\n"
    "module = spec.loader.create_module(spec)\n"
    "module.client()\n"
  )

  assert any("hass_voice_assistant_ws_client" in offender for offender in offenders)


def test_detects_find_spec_nested_loader_chain() -> None:
  """Detect fixtures returned via nested spec.loader chains."""

  offenders = _scan_source(
    "from importlib.util import find_spec\n"
    "from types import SimpleNamespace\n"
    "def _load_module(name: str):\n"
    "    return SimpleNamespace(client=hass_mobile_app_client)\n"
    "inner_loader = SimpleNamespace(load_module=_load_module)\n"
    "outer_loader = SimpleNamespace(loader=inner_loader)\n"
    "def _find_spec(name: str):\n"
    "    return SimpleNamespace(loader=outer_loader)\n"
    "find_spec = _find_spec\n"
    "module = find_spec('tests.helpers').loader.loader.load_module('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_mobile_app_client" in offender for offender in offenders)


def test_detects_find_spec_invalidate_caches_loader() -> None:
  """Detect fixtures returned after loader.invalidate_caches wrappers."""

  offenders = _scan_source(
    "from importlib.util import find_spec\n"
    "from types import SimpleNamespace\n"
    "def _load_module(name: str):\n"
    "    return SimpleNamespace(client=hass_supervisor_client)\n"
    "def _invalidate_caches() -> SimpleNamespace:\n"
    "    return SimpleNamespace(load_module=_load_module)\n"
    "loader = SimpleNamespace(invalidate_caches=_invalidate_caches)\n"
    "def _find_spec(name: str):\n"
    "    return SimpleNamespace(loader=loader)\n"
    "find_spec = _find_spec\n"
    "module = find_spec('tests.helpers').loader.invalidate_caches().load_module('tests.conftest')\n"
    "module.client()\n"
  )

  assert any("hass_supervisor_client" in offender for offender in offenders)


def test_detects_runpy_init_globals_fixture_alias() -> None:
  """Detect fixtures injected into runpy namespaces via init_globals."""

  offenders = _scan_source(
    "import runpy\n"
    "init_globals = {}\n"
    "init_globals['client'] = hass_client\n"
    "namespace = runpy.run_module('tests.helpers', init_globals=init_globals)\n"
    "namespace['client']()\n"
  )

  assert any(
    offender.startswith("inline.py:5") and "hass_client" in offender
    for offender in offenders
  )


def test_detects_runpy_run_path_fixture_alias() -> None:
  """Detect fixtures retrieved from runpy.run_path namespaces."""

  offenders = _scan_source(
    "import runpy\n"
    "namespace = runpy.run_path('tests/helpers.py')\n"
    "namespace['hass_owner_ws_client']()\n"
  )

  assert len(offenders) == 1
  assert "hass_owner_ws_client" in offenders[0]


def test_detects_pkgutil_get_importer_loader_chain() -> None:
  """Detect fixtures returned from pkgutil.get_importer importers."""

  offenders = _scan_source(
    "import pkgutil\n"
    "from types import SimpleNamespace\n"
    "class Loader:\n"
    "    def create_module(self, spec):\n"
    "        return SimpleNamespace(client=hass_client)\n"
    "class Importer:\n"
    "    def find_spec(self, name):\n"
    "        return SimpleNamespace(loader=Loader())\n"
    "def get_importer(path: str):\n"
    "    return Importer()\n"
    "pkgutil.get_importer = get_importer\n"
    "spec = pkgutil.get_importer('tests').find_spec('helpers')\n"
    "module = spec.loader.create_module(spec)\n"
    "module.client()\n"
  )

  assert any("hass_client" in offender for offender in offenders)


def test_detects_owner_websocket_fixture_invocation() -> None:
  """Detect direct invocations of the owner websocket fixture."""

  offenders = _scan_source("hass_owner_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_owner_ws_client" in offenders[0]


def test_detects_importlib_resources_getattr_loader() -> None:
  """Detect fixtures retrieved from importlib.resources attribute lookups."""

  offenders = _scan_source(
    "from importlib.resources import files\n"
    "client = getattr(files('tests.helpers'), 'hass_supervisor_ws_client')\n"
    "client()\n"
  )

  assert len(offenders) == 1
  assert "hass_supervisor_ws_client" in offenders[0]


def test_detects_import_module_factory() -> None:
  """Detect factories loading fixtures dynamically via importlib."""

  offenders = _scan_source(
    "from importlib import import_module\n"
    "module = import_module('tests.conftest')\n"
    "client = getattr(module, 'hass_client_admin')\n"
    "client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client_admin" in offenders[0]


def test_detects_import_module_direct_getattr_invocation() -> None:
  """Detect direct getattr invocations on importlib-loaded modules."""

  offenders = _scan_source(
    "from importlib import import_module\n"
    "getattr(import_module('tests.conftest'), 'hass_admin_ws_client')()\n"
  )

  assert len(offenders) == 1
  assert "hass_admin_ws_client" in offenders[0]


def test_detects_pkgutil_walk_packages_loader_chain() -> None:
  """Detect fixtures loaded through pkgutil.walk_packages helpers."""

  offenders = _scan_source(
    "from importlib import import_module\n"
    "from pkgutil import walk_packages\n"
    "for _, module_name, _ in walk_packages(['tests'], 'tests.'):\n"
    "    getattr(import_module(module_name), 'hass_client')()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_voice_assistant_http_fixture_invocation() -> None:
  """Detect direct invocations of the voice assistant HTTP fixture."""

  offenders = _scan_source("hass_voice_assistant_client()\n")

  assert len(offenders) == 1
  assert "hass_voice_assistant_client" in offenders[0]


def test_detects_voice_assistant_websocket_fixture_invocation() -> None:
  """Detect direct invocations of the voice assistant websocket fixture."""

  offenders = _scan_source("hass_voice_assistant_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_voice_assistant_ws_client" in offenders[0]


def test_detects_voice_assistant_prefix_fixture_invocation() -> None:
  """Detect new voice assistant fixtures exposed via prefix matching."""

  offenders = _scan_source("hass_voice_assistant_pipeline_ws_client()\n")

  assert len(offenders) == 1
  assert "hass_voice_assistant_pipeline_ws_client" in offenders[0]


def test_detects_function_returning_fixture_alias() -> None:
  """Detect helper functions that return forbidden fixtures."""

  offenders = _scan_source(
    "def build_client():\n    return hass_client\nbuild_client()()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_descriptor_factory_fixture() -> None:
  """Detect descriptor factories that yield forbidden fixtures."""

  offenders = _scan_source(
    "def descriptor_factory():\n"
    "    def getter(self):\n"
    "        return hass_ws_client\n"
    "    return property(getter)\n"
    "class Helper:\n"
    "    client = descriptor_factory()\n"
    "Helper().client()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_ws_client" in offender for offender in offenders)


def test_detects_setattr_descriptor_fixture_alias() -> None:
  """Detect descriptor builders that install fixtures via setattr."""

  offenders = _scan_source(
    "def install(cls):\n"
    "    setattr(cls, 'client', property(lambda self: hass_client))\n"
    "class Helper:\n"
    "    pass\n"
    "install(Helper)\n"
    "Helper().client()\n"
  )

  assert len(offenders) >= 2
  assert all("hass_client" in offender for offender in offenders)


def test_detects_getattr_forwarder_fixture() -> None:
  """Detect __getattr__ forwarders that expose forbidden fixtures."""

  offenders = _scan_source(
    "class Proxy:\n"
    "    def __getattr__(self, name):\n"
    "        return hass_client\n"
    "proxy = Proxy()\n"
    "proxy.client()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_client" in offender for offender in offenders)


def test_detects_getattribute_forwarder_fixture() -> None:
  """Detect __getattribute__ forwarders that expose forbidden fixtures."""

  offenders = _scan_source(
    "class Proxy:\n"
    "    def __getattribute__(self, name):\n"
    "        return hass_ws_client\n"
    "proxy = Proxy()\n"
    "proxy.client()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_ws_client" in offender for offender in offenders)


def test_detects_dataclass_field_fixture_alias() -> None:
  """Detect dataclass fields that default to forbidden fixtures."""

  offenders = _scan_source(
    "from dataclasses import dataclass, field\n"
    "@dataclass\n"
    "class Helper:\n"
    "    client: object = field(default_factory=lambda: hass_client_admin)\n"
    "Helper().client()\n"
  )

  assert len(offenders) == 2
  assert all("hass_client_admin" in offender for offender in offenders)


def test_detects_make_dataclass_fixture_alias() -> None:
  """Detect dataclasses.make_dataclass fields returning forbidden fixtures."""

  offenders = _scan_source(
    "from dataclasses import field, make_dataclass\n"
    "Helper = make_dataclass(\n"
    "    'Helper',\n"
    "    [('client', object, field(default_factory=lambda: hass_client))],\n"
    ")\n"
    "Helper().client()\n"
  )

  assert len(offenders) >= 2
  assert all("hass_client" in offender for offender in offenders)


def test_detects_contextmanager_fixture_wrapper() -> None:
  """Detect contextmanager helpers that yield forbidden fixtures."""

  offenders = _scan_source(
    "from contextlib import contextmanager\n"
    "@contextmanager\n"
    "def helper():\n"
    "    yield hass_client_admin\n"
    "with helper() as client:\n"
    "    client()\n"
  )

  assert len(offenders) == 1
  assert "hass_client_admin" in offenders[0]


def test_detects_asynccontextmanager_fixture_wrapper() -> None:
  """Detect asynccontextmanager helpers that yield forbidden fixtures."""

  offenders = _scan_source(
    "from contextlib import asynccontextmanager\n"
    "@asynccontextmanager\n"
    "async def helper():\n"
    "    yield hass_ws_client\n"
    "async def run():\n"
    "    async with helper() as client:\n"
    "        await client()\n"
  )

  assert len(offenders) == 1
  assert "hass_ws_client" in offenders[0]


def test_detects_class_getitem_fixture_proxy() -> None:
  """Detect __class_getitem__ helpers that expose forbidden fixtures."""

  offenders = _scan_source(
    "class Proxy:\n"
    "    def __class_getitem__(cls, item):\n"
    "        return hass_admin_ws_client\n"
    "Proxy['client']()\n"
  )

  assert len(offenders) == 1
  assert "hass_admin_ws_client" in offenders[0]


def test_detects_class_getitem_alias_proxy() -> None:
  """Detect aliases of __class_getitem__ helpers returning fixtures."""

  offenders = _scan_source(
    "class Proxy:\n"
    "    @classmethod\n"
    "    def __class_getitem__(cls, item):\n"
    "        return hass_client\n"
    "alias = Proxy\n"
    "alias['client']()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_class_getitem_getattr_proxy() -> None:
  """Detect getattr-based access to __class_getitem__ helpers."""

  offenders = _scan_source(
    "class Proxy:\n"
    "    def __class_getitem__(cls, item):\n"
    "        return hass_owner_ws_client\n"
    "module = type('module', (), {'Proxy': Proxy})\n"
    "proxy_cls = getattr(module, 'Proxy')\n"
    "proxy_cls['client']()\n"
  )

  assert len(offenders) >= 1
  assert any("hass_owner_ws_client" in offender for offender in offenders)


def test_detects_nullcontext_fixture_wrapper() -> None:
  """Detect nullcontext wrappers that forward forbidden fixtures."""

  offenders = _scan_source(
    "from contextlib import nullcontext\n"
    "with nullcontext(hass_client) as helper:\n"
    "    helper()\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_closing_fixture_wrapper() -> None:
  """Detect closing wrappers that forward forbidden fixtures."""

  offenders = _scan_source(
    "from contextlib import closing\n"
    "with closing(hass_client_admin) as helper:\n"
    "    helper()\n"
  )

  assert len(offenders) == 1
  assert "hass_client_admin" in offenders[0]


def test_detects_aclosing_fixture_wrapper() -> None:
  """Detect aclosing wrappers that forward forbidden fixtures."""

  offenders = _scan_source(
    "from contextlib import aclosing\n"
    "async def run():\n"
    "    async with aclosing(hass_voice_assistant_ws_client):\n"
    "        pass\n"
  )

  assert len(offenders) == 1
  assert "hass_voice_assistant_ws_client" in offenders[0]


def test_detects_task_group_fixture_invocation() -> None:
  """Detect TaskGroup helpers that schedule forbidden fixtures."""

  offenders = _scan_source(
    "import asyncio\n"
    "async def run():\n"
    "    async with asyncio.TaskGroup() as group:\n"
    "        group.create_task(hass_client())\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_task_group_starting_fixture_callable() -> None:
  """Detect TaskGroup helpers that start forbidden fixture callables."""

  offenders = _scan_source(
    "import asyncio\n"
    "async def run():\n"
    "    async with asyncio.TaskGroup() as group:\n"
    "        group.start_soon(hass_ws_client)\n"
  )

  assert len(offenders) == 1
  assert "hass_ws_client" in offenders[0]


def test_detects_async_exit_stack_async_context_wrapper() -> None:
  """Detect AsyncExitStack helpers that enter forbidden fixture contexts."""

  offenders = _scan_source(
    "from contextlib import AsyncExitStack, nullcontext\n"
    "async def run():\n"
    "    stack = AsyncExitStack()\n"
    "    await stack.enter_async_context(nullcontext(hass_ws_client))\n"
  )

  assert len(offenders) == 1
  assert "hass_ws_client" in offenders[0]


def test_detects_async_exit_stack_async_callback_wrapper() -> None:
  """Detect AsyncExitStack helpers that push forbidden fixture callbacks."""

  offenders = _scan_source(
    "from contextlib import AsyncExitStack\n"
    "async def run():\n"
    "    stack = AsyncExitStack()\n"
    "    stack.push_async_callback(hass_client)\n"
  )

  assert len(offenders) == 1
  assert "hass_client" in offenders[0]


def test_detects_async_exit_stack_async_exit_wrapper() -> None:
  """Detect AsyncExitStack helpers that push forbidden async exits."""

  offenders = _scan_source(
    "from contextlib import AsyncExitStack\n"
    "async def run():\n"
    "    stack = AsyncExitStack()\n"
    "    stack.push_async_exit(hass_owner_ws_client)\n"
  )

  assert len(offenders) == 1
  assert "hass_owner_ws_client" in offenders[0]


def test_detects_exitstack_fixture_alias() -> None:
  """Detect ExitStack helpers that alias forbidden fixtures."""

  offenders = _scan_source(
    "from contextlib import ExitStack\n"
    "import module\n"
    "with ExitStack() as stack:\n"
    "    helper = stack.enter_context(getattr(module, 'hass_supervisor_client'))\n"
    "helper()\n"
  )

  assert len(offenders) == 2
  assert all("hass_supervisor_client" in offender for offender in offenders)
  assert {offender.split(" - ")[0] for offender in offenders} == {
    "inline.py:4",
    "inline.py:5",
  }


def test_forbidden_fixture_invocations() -> None:
  """Fail when tests call fixtures like regular functions or helper wrappers."""

  offenders: list[str] = []

  for path in sorted(Path("tests").rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _FixtureUsageVisitor(path=path)
    visitor.visit(tree)
    offenders.extend(visitor.offenders)

  assert not offenders, "\n".join(offenders)
