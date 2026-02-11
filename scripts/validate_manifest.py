#!/usr/bin/env python3
"""Validate Paw Control manifest.json file."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def validate_manifest():
    """Validate the manifest.json file."""
    manifest_path = Path("custom_components/pawcontrol/manifest.json")

    if not manifest_path.exists():
        print("❌ manifest.json not found!")
        return False

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in manifest.json: {e}")
        return False

    # Required fields
    required_fields = [
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

    errors = []

    for field in required_fields:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")

    # Validate domain
    if manifest.get("domain") != "pawcontrol":
        errors.append(
            f"Invalid domain: {manifest.get('domain')} (expected: pawcontrol)"
        )

    # Validate version format (x.y.z)
    version = manifest.get("version", "")
    if not version or len(version.split(".")) != 3:
        errors.append(f"Invalid version format: {version} (expected: x.y.z)")

    # Validate config_flow
    if not manifest.get("config_flow"):
        errors.append("config_flow must be true for UI configuration")

    # Validate iot_class
    valid_iot_classes = [
        "assumed_state",
        "cloud_polling",
        "cloud_push",
        "local_polling",
        "local_push",
        "calculated",
    ]

    if manifest.get("iot_class") not in valid_iot_classes:
        errors.append(f"Invalid iot_class: {manifest.get('iot_class')}")

    # Check for quality scale
    if "quality_scale" in manifest:
        valid_scales = ["internal", "silver", "gold", "platinum"]
        if manifest["quality_scale"] not in valid_scales:
            errors.append(f"Invalid quality_scale: {manifest['quality_scale']}")

    # Report results
    if errors:
        print("❌ Manifest validation failed:")
        for error in errors:
            print(f"  - {error}")
        return False

    print("✅ Manifest validation successful!")
    print(f"  Domain: {manifest['domain']}")
    print(f"  Name: {manifest['name']}")
    print(f"  Version: {manifest['version']}")
    print(f"  Config Flow: {manifest['config_flow']}")
    print(f"  IoT Class: {manifest['iot_class']}")

    return True


if __name__ == "__main__":
    if not validate_manifest():
        sys.exit(1)
