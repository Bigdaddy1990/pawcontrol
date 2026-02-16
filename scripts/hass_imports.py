"""Plugin for checking imports."""

from __future__ import annotations

from dataclasses import dataclass
import re

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter


@dataclass
class ObsoleteImportMatch:
  """Class for pattern matching."""  # noqa: E111

  constant: re.Pattern[str]  # noqa: E111
  reason: str  # noqa: E111


_OBSOLETE_IMPORT: dict[str, list[ObsoleteImportMatch]] = {
  "functools": [
    ObsoleteImportMatch(
      reason="replaced by propcache.api.cached_property",
      constant=re.compile(r"^cached_property$"),
    ),
  ],
  "homeassistant.components.light": [
    ObsoleteImportMatch(
      reason="replaced by ColorMode enum",
      constant=re.compile(r"^COLOR_MODE_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by color modes",
      constant=re.compile("^SUPPORT_(BRIGHTNESS|COLOR_TEMP|COLOR)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by LightEntityFeature enum",
      constant=re.compile("^SUPPORT_(EFFECT|FLASH|TRANSITION)$"),
    ),
  ],
  "homeassistant.components.media_player": [
    ObsoleteImportMatch(
      reason="replaced by MediaPlayerDeviceClass enum",
      constant=re.compile(r"^DEVICE_CLASS_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by MediaPlayerEntityFeature enum",
      constant=re.compile(r"^SUPPORT_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by MediaClass enum",
      constant=re.compile(r"^MEDIA_CLASS_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by MediaType enum",
      constant=re.compile(r"^MEDIA_TYPE_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by RepeatMode enum",
      constant=re.compile(r"^REPEAT_MODE(\w*)$"),
    ),
  ],
  "homeassistant.components.media_player.const": [
    ObsoleteImportMatch(
      reason="replaced by MediaPlayerEntityFeature enum",
      constant=re.compile(r"^SUPPORT_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by MediaClass enum",
      constant=re.compile(r"^MEDIA_CLASS_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by MediaType enum",
      constant=re.compile(r"^MEDIA_TYPE_(\w*)$"),
    ),
    ObsoleteImportMatch(
      reason="replaced by RepeatMode enum",
      constant=re.compile(r"^REPEAT_MODE(\w*)$"),
    ),
  ],
  "homeassistant.components.vacuum": [
    ObsoleteImportMatch(
      reason="replaced by VacuumEntityFeature enum",
      constant=re.compile(r"^SUPPORT_(\w*)$"),
    ),
  ],
  "homeassistant.config_entries": [
    ObsoleteImportMatch(
      reason="replaced by ConfigEntryDisabler enum",
      constant=re.compile(r"^DISABLED_(\w*)$"),
    ),
  ],
  "homeassistant.const": [
    ObsoleteImportMatch(
      reason="replaced by local constants",
      constant=re.compile(r"^CONF_UNIT_SYSTEM_(\w+)$"),
    ),
  ],
  "homeassistant.helpers.config_validation": [
    ObsoleteImportMatch(
      reason="should be imported from homeassistant/components/<platform>",
      constant=re.compile(r"^PLATFORM_SCHEMA(_BASE)?$"),
    ),
  ],
  "homeassistant.helpers.json": [
    ObsoleteImportMatch(
      reason="moved to homeassistant.util.json",
      constant=re.compile(
        r"^JSON_DECODE_EXCEPTIONS|JSON_ENCODE_EXCEPTIONS|json_loads$"
      ),
    ),
  ],
  "homeassistant.util.unit_system": [
    ObsoleteImportMatch(
      reason="replaced by US_CUSTOMARY_SYSTEM",
      constant=re.compile(r"^IMPERIAL_SYSTEM$"),
    ),
  ],
  "propcache": [
    ObsoleteImportMatch(
      reason="importing from propcache.api recommended",
      constant=re.compile(r"^(under_)?cached_property$"),
    ),
  ],
}

_IGNORE_ROOT_IMPORT = (
  "assist_pipeline",
  "automation",
  "bluetooth",
  "camera",
  "cast",
  "device_automation",
  "device_tracker",
  "ffmpeg",
  "ffmpeg_motion",
  "google_assistant",
  "hardware",
  "homeassistant",
  "homeassistant_hardware",
  "http",
  "manual",
  "plex",
  "recorder",
  "rest",
  "script",
  "sensor",
  "stream",
  "zha",
)


# Blacklist of imports that should be using the namespace
@dataclass
class NamespaceAlias:
  """Class for namespace imports."""  # noqa: E111

  alias: str  # noqa: E111
  names: set[str]  # function names  # noqa: E111


_FORCE_NAMESPACE_IMPORT: dict[str, NamespaceAlias] = {
  "homeassistant.helpers.area_registry": NamespaceAlias("ar", {"async_get"}),
  "homeassistant.helpers.category_registry": NamespaceAlias("cr", {"async_get"}),
  "homeassistant.helpers.device_registry": NamespaceAlias(
    "dr",
    {
      "async_get",
      "async_entries_for_config_entry",
    },
  ),
  "homeassistant.helpers.entity_registry": NamespaceAlias(
    "er",
    {
      "async_get",
      "async_entries_for_config_entry",
    },
  ),
  "homeassistant.helpers.floor_registry": NamespaceAlias("fr", {"async_get"}),
  "homeassistant.helpers.issue_registry": NamespaceAlias("ir", {"async_get"}),
  "homeassistant.helpers.label_registry": NamespaceAlias("lr", {"async_get"}),
}


class HassImportsFormatChecker(BaseChecker):
  """Checker for imports."""  # noqa: E111

  name = "hass_imports"  # noqa: E111
  priority = -1  # noqa: E111
  msgs = {  # noqa: E111
    "W7421": (
      "Relative import should be used",
      "hass-relative-import",
      "Used when absolute import should be replaced with relative import",
    ),
    "W7422": (
      "%s is deprecated, %s",
      "hass-deprecated-import",
      "Used when import is deprecated",
    ),
    "W7423": (
      "Absolute import should be used",
      "hass-absolute-import",
      "Used when relative import should be replaced with absolute import",
    ),
    "W7424": (
      "Import should be using the component root",
      "hass-component-root-import",
      "Used when an import from another component should be from the component root",
    ),
    "W7425": (
      "`%s` should not be imported directly. Please import `%s` as `%s` "
      "and use `%s.%s`",
      "hass-helper-namespace-import",
      "Used when a helper should be used via the namespace",
    ),
    "W7426": (
      "`%s` should be imported using an alias, such as `%s as %s`",
      "hass-import-constant-alias",
      "Used when a constant should be imported as an alias",
    ),
    "W7427": (
      "`%s` alias is unnecessary for `%s`",
      "hass-import-constant-unnecessary-alias",
      "Used when a constant alias is unnecessary",
    ),
  }
  options = ()  # noqa: E111

  def __init__(self, linter: PyLinter) -> None:  # noqa: E111
    """Initialize the HassImportsFormatChecker."""
    super().__init__(linter)
    self.current_package: str | None = None

  def visit_module(self, node: nodes.Module) -> None:  # noqa: E111
    """Determine current package."""
    if node.package:
      self.current_package = node.name  # noqa: E111
    else:
      # Strip name of the current module  # noqa: E114
      self.current_package = node.name[: node.name.rfind(".")]  # noqa: E111

  def visit_import(self, node: nodes.Import) -> None:  # noqa: E111
    """Check for improper `import _` invocations."""
    if self.current_package is None:
      return  # noqa: E111
    for module, _alias in node.names:
      if module.startswith(f"{self.current_package}."):  # noqa: E111
        self.add_message("hass-relative-import", node=node)
        continue
      if module.startswith("homeassistant.components.") and len(module.split(".")) > 3:  # noqa: E111
        if (
          self.current_package.startswith("tests.components.")
          and self.current_package.split(".")[2] == module.split(".")[2]
        ):
          # Ignore check if the component being tested matches  # noqa: E114
          # the component being imported from  # noqa: E114
          continue  # noqa: E111
        self.add_message("hass-component-root-import", node=node)

  def _visit_importfrom_relative(  # noqa: E111
    self, current_package: str, node: nodes.ImportFrom
  ) -> None:
    """Check for improper 'from ._ import _' invocations."""
    if not current_package.startswith((
      "homeassistant.components.",
      "tests.components.",
    )):
      return  # noqa: E111

    split_package = current_package.split(".")
    current_component = split_package[2]

    self._check_for_constant_alias(node, current_component, current_component)

    if node.level <= 1:
      # No need to check relative import  # noqa: E114
      return  # noqa: E111

    if not node.modname and len(split_package) == node.level + 1:
      for name in node.names:  # noqa: E111
        # Allow relative import to component root
        if name[0] != current_component:
          self.add_message("hass-absolute-import", node=node)  # noqa: E111
          return  # noqa: E111
      return  # noqa: E111
    if len(split_package) < node.level + 2:
      self.add_message("hass-absolute-import", node=node)  # noqa: E111

  def _check_for_constant_alias(  # noqa: E111
    self,
    node: nodes.ImportFrom,
    current_component: str | None,
    imported_component: str,
  ) -> bool:
    """Check for hass-import-constant-alias."""
    if current_component == imported_component:
      # Check for `from homeassistant.components.self import DOMAIN as XYZ`  # noqa: E114
      for name, alias in node.names:  # noqa: E111
        if name == "DOMAIN" and (alias is not None and alias != "DOMAIN"):
          self.add_message(  # noqa: E111
            "hass-import-constant-unnecessary-alias",
            node=node,
            args=(alias, "DOMAIN"),
          )
          return False  # noqa: E111
      return True  # noqa: E111

    # Check for `from homeassistant.components.other import DOMAIN`
    for name, alias in node.names:
      if name == "DOMAIN" and (alias is None or alias == "DOMAIN"):  # noqa: E111
        self.add_message(
          "hass-import-constant-alias",
          node=node,
          args=(
            "DOMAIN",
            "DOMAIN",
            f"{imported_component.upper()}_DOMAIN",
          ),
        )
        return False

    return True

  def _check_for_component_root_import(  # noqa: E111
    self,
    node: nodes.ImportFrom,
    current_component: str | None,
    imported_parts: list[str],
    imported_component: str,
  ) -> bool:
    """Check for hass-component-root-import."""
    if (
      current_component == imported_component
      or imported_component in _IGNORE_ROOT_IMPORT
    ):
      return True  # noqa: E111

    # Check for `from homeassistant.components.other.module import something`
    if len(imported_parts) > 3:
      self.add_message("hass-component-root-import", node=node)  # noqa: E111
      return False  # noqa: E111

    # Check for `from homeassistant.components.other import const`
    for name, _ in node.names:
      if name == "const":  # noqa: E111
        self.add_message("hass-component-root-import", node=node)
        return False

    return True

  def _check_for_relative_import(  # noqa: E111
    self,
    current_package: str,
    node: nodes.ImportFrom,
    current_component: str | None,
  ) -> bool:
    """Check for hass-relative-import."""
    if node.modname == current_package or node.modname.startswith(
      f"{current_package}."
    ):
      self.add_message("hass-relative-import", node=node)  # noqa: E111
      return False  # noqa: E111

    for root in ("homeassistant", "tests"):
      if current_package.startswith(f"{root}.components."):  # noqa: E111
        if node.modname == f"{root}.components":
          for name in node.names:  # noqa: E111
            if name[0] == current_component:
              self.add_message("hass-relative-import", node=node)  # noqa: E111
              return False  # noqa: E111
        elif node.modname.startswith(f"{root}.components.{current_component}."):
          self.add_message("hass-relative-import", node=node)  # noqa: E111
          return False  # noqa: E111

    return True

  def visit_importfrom(self, node: nodes.ImportFrom) -> None:  # noqa: E111
    """Check for improper 'from _ import _' invocations."""
    if not self.current_package:
      return  # noqa: E111
    if node.level is not None:
      self._visit_importfrom_relative(self.current_package, node)  # noqa: E111
      return  # noqa: E111

    # Cache current component
    current_component: str | None = None
    for root in ("homeassistant", "tests"):
      if self.current_package.startswith(f"{root}.components."):  # noqa: E111
        current_component = self.current_package.split(".")[2]

    # Checks for hass-relative-import
    if not self._check_for_relative_import(
      self.current_package, node, current_component
    ):
      return  # noqa: E111

    if node.modname.startswith("homeassistant.components."):
      imported_parts = node.modname.split(".")  # noqa: E111
      imported_component = imported_parts[2]  # noqa: E111

      # Checks for hass-component-root-import  # noqa: E114
      if not self._check_for_component_root_import(  # noqa: E111
        node, current_component, imported_parts, imported_component
      ):
        return

      # Checks for hass-import-constant-alias  # noqa: E114
      if not self._check_for_constant_alias(  # noqa: E111
        node, current_component, imported_component
      ):
        return

    # Checks for hass-deprecated-import
    if obsolete_imports := _OBSOLETE_IMPORT.get(node.modname):
      for name_tuple in node.names:  # noqa: E111
        for obsolete_import in obsolete_imports:
          if import_match := obsolete_import.constant.match(name_tuple[0]):  # noqa: E111
            self.add_message(
              "hass-deprecated-import",
              node=node,
              args=(import_match.string, obsolete_import.reason),
            )

    # Checks for hass-helper-namespace-import
    if namespace_alias := _FORCE_NAMESPACE_IMPORT.get(node.modname):
      for name in node.names:  # noqa: E111
        if name[0] in namespace_alias.names:
          self.add_message(  # noqa: E111
            "hass-helper-namespace-import",
            node=node,
            args=(
              name[0],
              node.modname,
              namespace_alias.alias,
              namespace_alias.alias,
              name[0],
            ),
          )


def register(linter: PyLinter) -> None:
  """Register the checker."""  # noqa: E111
  linter.register_checker(HassImportsFormatChecker(linter))  # noqa: E111
