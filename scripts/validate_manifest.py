#!/usr/bin/env python3
"""Validate Paw Control manifest.json file."""

import json
from pathlib import Path
import sys


def validate_manifest():
  """Validate the manifest.json file."""  # noqa: E111
  manifest_path = Path("custom_components/pawcontrol/manifest.json")  # noqa: E111

  if not manifest_path.exists():  # noqa: E111
    print("❌ manifest.json not found!")
    return False

  try:  # noqa: E111
    with open(manifest_path) as f:
      manifest = json.load(f)  # noqa: E111
  except json.JSONDecodeError as e:  # noqa: E111
    print(f"❌ Invalid JSON in manifest.json: {e}")
    return False

  # Required fields  # noqa: E114
  required_fields = [  # noqa: E111
    "domain",
    "name",
    "version",
    "documentation",
    "requirements",
    "dependencies",
    "codeowners",
    "config_flow",
    "iot_class",
  ]

  errors = []  # noqa: E111

  for field in required_fields:  # noqa: E111
    if field not in manifest:
      errors.append(f"Missing required field: {field}")  # noqa: E111

  # Validate domain  # noqa: E114
  if manifest.get("domain") != "pawcontrol":  # noqa: E111
    errors.append(f"Invalid domain: {manifest.get('domain')} (expected: pawcontrol)")

  # Validate version format (x.y.z)  # noqa: E114
  version = manifest.get("version", "")  # noqa: E111
  if not version or len(version.split(".")) != 3:  # noqa: E111
    errors.append(f"Invalid version format: {version} (expected: x.y.z)")

  # Validate config_flow  # noqa: E114
  if not manifest.get("config_flow"):  # noqa: E111
    errors.append("config_flow must be true for UI configuration")

  # Validate iot_class  # noqa: E114
  valid_iot_classes = [  # noqa: E111
    "assumed_state",
    "cloud_polling",
    "cloud_push",
    "local_polling",
    "local_push",
    "calculated",
  ]

  if manifest.get("iot_class") not in valid_iot_classes:  # noqa: E111
    errors.append(f"Invalid iot_class: {manifest.get('iot_class')}")

  # Check for quality scale  # noqa: E114
  if "quality_scale" in manifest:  # noqa: E111
    valid_scales = ["internal", "silver", "gold", "platinum"]
    if manifest["quality_scale"] not in valid_scales:
      errors.append(f"Invalid quality_scale: {manifest['quality_scale']}")  # noqa: E111

  # Report results  # noqa: E114
  if errors:  # noqa: E111
    print("❌ Manifest validation failed:")
    for error in errors:
      print(f"  - {error}")  # noqa: E111
    return False

  print("✅ Manifest validation successful!")  # noqa: E111
  print(f"  Domain: {manifest['domain']}")  # noqa: E111
  print(f"  Name: {manifest['name']}")  # noqa: E111
  print(f"  Version: {manifest['version']}")  # noqa: E111
  print(f"  Config Flow: {manifest['config_flow']}")  # noqa: E111
  print(f"  IoT Class: {manifest['iot_class']}")  # noqa: E111

  return True  # noqa: E111


if __name__ == "__main__":
  if not validate_manifest():  # noqa: E111
    sys.exit(1)
