"""Lightweight hassfest shim for offline validation.

The real Home Assistant hassfest utility validates integration manifests,
translations, and metadata. This shim provides a minimal subset so the
repository can run guard checks without pulling in the full Home Assistant
package. It validates manifest structure, required keys, and translation
presence for the PawControl integration.
"""

from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Iterable
import json
from pathlib import Path
import sys
from typing import Any

QUALITY_SCALE_LEVELS = {"internal", "bronze", "silver", "gold", "platinum"}
REQUIRED_KEYS = {
  "domain",
  "name",
  "version",
  "documentation",
  "issue_tracker",
  "requirements",
  "codeowners",
  "config_flow",
  "integration_type",
  "quality_scale",
  "loggers",
  "iot_class",
}
REQUIRED_LIST_KEYS = {"requirements", "codeowners", "loggers"}
IOT_CLASS_VALUES = {
  "assumed_state",
  "cloud_polling",
  "cloud_push",
  "local_polling",
  "local_push",
}


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
  manifest_text = manifest_path.read_text(encoding="utf-8")  # noqa: E111
  manifest = json.loads(manifest_text)  # noqa: E111
  if not isinstance(manifest, dict):  # noqa: E111
    msg = "manifest.json must contain a JSON object"
    raise ValueError(msg)
  return manifest  # noqa: E111


def _validate_manifest(manifest_path: Path) -> list[str]:
  errors: list[str] = []  # noqa: E111
  if not manifest_path.is_file():  # noqa: E111
    return ["manifest.json is missing"]

  try:  # noqa: E111
    manifest = _load_manifest(manifest_path)
  except (json.JSONDecodeError, ValueError) as exc:  # noqa: E111
    errors.append(f"invalid manifest.json: {exc}")
    return errors

  missing_keys = sorted(REQUIRED_KEYS - manifest.keys())  # noqa: E111
  if missing_keys:  # noqa: E111
    errors.append(
      f"manifest.json is missing required keys: {', '.join(missing_keys)}",
    )

  for key in REQUIRED_LIST_KEYS:  # noqa: E111
    value = manifest.get(key)
    if not isinstance(value, list) or not value:
      errors.append(f"manifest.{key} must be a non-empty list")  # noqa: E111

  if not isinstance(manifest.get("config_flow"), bool):  # noqa: E111
    errors.append("manifest.config_flow must be a boolean")

  domain = manifest.get("domain")  # noqa: E111
  expected_domain = manifest_path.parent.name  # noqa: E111
  if domain != expected_domain:  # noqa: E111
    errors.append(
      f"manifest.domain '{domain}' does not match integration folder '{expected_domain}'",  # noqa: E501
    )

  quality_scale = manifest.get("quality_scale")  # noqa: E111
  if quality_scale not in QUALITY_SCALE_LEVELS:  # noqa: E111
    errors.append(
      "manifest.quality_scale must be one of: "
      + ", ".join(sorted(QUALITY_SCALE_LEVELS)),
    )

  loggers = manifest.get("loggers")  # noqa: E111
  if isinstance(loggers, list):  # noqa: E111
    expected_logger = f"custom_components.{expected_domain}"
    if expected_logger not in loggers:
      errors.append(  # noqa: E111
        f"manifest.loggers must include 'custom_components.{expected_domain}'",
      )

  supported_by = manifest.get("supported_by")  # noqa: E111
  if supported_by is not None and (  # noqa: E111
    not isinstance(supported_by, str) or not supported_by
  ):
    errors.append("manifest.supported_by must be null or a non-empty string")

  iot_class = manifest.get("iot_class")  # noqa: E111
  if iot_class not in IOT_CLASS_VALUES:  # noqa: E111
    errors.append(
      "manifest.iot_class must be one of: " + ", ".join(sorted(IOT_CLASS_VALUES)),
    )

  return errors  # noqa: E111


def _validate_translations(integration_path: Path) -> list[str]:
  errors: list[str] = []  # noqa: E111
  translations_dir = integration_path / "translations"  # noqa: E111
  strings_path = integration_path / "strings.json"  # noqa: E111

  if not translations_dir.is_dir():  # noqa: E111
    errors.append("translations directory is missing")
  if not strings_path.is_file():  # noqa: E111
    errors.append("strings.json is missing")

  def _load_object(path: Path) -> dict[str, Any] | None:  # noqa: E111
    try:
      loaded = json.loads(path.read_text(encoding="utf-8"))  # noqa: E111
    except json.JSONDecodeError:
      errors.append(f"{path.name} is not valid JSON")  # noqa: E111
      return None  # noqa: E111
    if not isinstance(loaded, dict):
      errors.append(f"{path.name} must contain a JSON object")  # noqa: E111
      return None  # noqa: E111
    return loaded

  if strings_path.is_file():  # noqa: E111
    _load_object(strings_path)

  if translations_dir.is_dir():  # noqa: E111
    english_translation = translations_dir / "en.json"
    if not english_translation.is_file():
      errors.append("translations/en.json is missing")  # noqa: E111
    else:
      _load_object(english_translation)  # noqa: E111

  return errors  # noqa: E111


def run(argv: Iterable[str] | None = None) -> int:
  parser = ArgumentParser(description="Validate Home Assistant integration metadata")  # noqa: E111
  parser.add_argument(  # noqa: E111
    "--integration-path",
    type=Path,
    required=True,
    help="Path to the integration directory (e.g. custom_components/pawcontrol)",
  )
  args = parser.parse_args(list(argv) if argv is not None else None)  # noqa: E111

  integration_path = args.integration_path  # noqa: E111
  manifest_path = integration_path / "manifest.json"  # noqa: E111

  errors = _validate_manifest(manifest_path)  # noqa: E111
  errors.extend(_validate_translations(integration_path))  # noqa: E111

  if errors:  # noqa: E111
    for error in errors:
      print(f"ERROR: {error}", file=sys.stderr)  # noqa: E111
    return 1

  print(f"hassfest stub: validated {integration_path}")  # noqa: E111
  return 0  # noqa: E111


def main() -> int:
  return run()  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
