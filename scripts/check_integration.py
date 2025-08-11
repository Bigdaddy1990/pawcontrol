#!/usr/bin/env python3
"""Final check script for Paw Control integration."""

import json
import os
import sys
from pathlib import Path


class IntegrationChecker:
    """Check Paw Control integration for completeness."""

    def __init__(self):
        self.base_path = Path("custom_components/pawcontrol")
        self.errors = []
        self.warnings = []
        self.successes = []

    def check_all(self):
        """Run all checks."""
        print("🔍 Checking Paw Control Integration...")
        print("=" * 50)

        self.check_structure()
        self.check_manifest()
        self.check_services()
        self.check_translations()
        self.check_platforms()
        self.check_helpers()
        self.check_imports()

        self.print_results()

        return len(self.errors) == 0

    def check_structure(self):
        """Check directory structure."""
        required_files = [
            "__init__.py",
            "manifest.json",
            "config_flow.py",
            "const.py",
            "coordinator.py",
            "services.yaml",
            "strings.json",
        ]

        for file in required_files:
            path = self.base_path / file
            if path.exists():
                self.successes.append(f"✓ {file} exists")
            else:
                self.errors.append(f"✗ Missing required file: {file}")

        # Check directories
        if (self.base_path / "translations").is_dir():
            self.successes.append("✓ translations directory exists")
        else:
            self.errors.append("✗ Missing translations directory")

        if (self.base_path / "helpers").is_dir():
            self.successes.append("✓ helpers directory exists")
        else:
            self.errors.append("✗ Missing helpers directory")

    def check_manifest(self):
        """Check manifest.json."""
        manifest_path = self.base_path / "manifest.json"

        if not manifest_path.exists():
            return

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)

            # Check required fields
            required = ["domain", "name", "version", "config_flow", "iot_class"]
            for field in required:
                if field in manifest:
                    self.successes.append(f"✓ Manifest has {field}")
                else:
                    self.errors.append(f"✗ Manifest missing {field}")

            # Check version format
            version = manifest.get("version", "")
            if len(version.split(".")) == 3:
                self.successes.append(f"✓ Version format correct: {version}")
            else:
                self.errors.append(f"✗ Invalid version format: {version}")

        except json.JSONDecodeError as e:
            self.errors.append(f"✗ Invalid JSON in manifest: {e}")

    def check_services(self):
        """Check services.yaml."""
        services_path = self.base_path / "services.yaml"

        if not services_path.exists():
            self.errors.append("✗ Missing services.yaml")
            return
        try:
            service_names = []
            with open(services_path) as f:
                for line in f:
                    stripped = line.strip()
                    if (
                        stripped
                        and not stripped.startswith("#")
                        and not line.startswith(" ")
                        and stripped.endswith(":")
                    ):
                        service_names.append(stripped[:-1])

            expected_services = [
                "daily_reset",
                "sync_setup",
                "notify_test",
                "start_walk",
                "end_walk",
                "walk_dog",
                "feed_dog",
                "log_health_data",
                "log_medication",
                "start_grooming_session",
                "play_with_dog",
                "start_training_session",
                "toggle_visitor_mode",
                "activate_emergency_mode",
                "generate_report",
                "export_health_data",
            ]

            for service in expected_services:
                if service in service_names:
                    self.successes.append(f"✓ Service defined: {service}")
                else:
                    self.warnings.append(f"⚠ Missing service: {service}")

        except Exception as e:
            self.errors.append(f"✗ Error reading services.yaml: {e}")

    def check_translations(self):
        """Check translation files."""
        trans_dir = self.base_path / "translations"

        for lang in ["en.json", "de.json"]:
            path = trans_dir / lang
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)
                    self.successes.append(f"✓ Translation {lang} valid")
                except json.JSONDecodeError:
                    self.errors.append(f"✗ Invalid JSON in {lang}")
            else:
                self.warnings.append(f"⚠ Missing translation: {lang}")

    def check_platforms(self):
        """Check platform files."""
        platforms = [
            "sensor.py",
            "binary_sensor.py",
            "button.py",
            "number.py",
            "select.py",
            "text.py",
            "switch.py",
        ]

        for platform in platforms:
            path = self.base_path / platform
            if path.exists():
                self.successes.append(f"✓ Platform exists: {platform}")

                # Check for async_setup_entry
                with open(path) as f:
                    content = f.read()
                    if "async_setup_entry" in content:
                        self.successes.append(f"  ✓ {platform} has async_setup_entry")
                    else:
                        self.errors.append(f"  ✗ {platform} missing async_setup_entry")
            else:
                self.errors.append(f"✗ Missing platform: {platform}")

    def check_helpers(self):
        """Check helper modules."""
        helpers = [
            "__init__.py",
            "setup_sync.py",
            "notification_router.py",
            "scheduler.py",
            "gps_logic.py",
        ]

        helpers_dir = self.base_path / "helpers"
        for helper in helpers:
            path = helpers_dir / helper
            if path.exists():
                self.successes.append(f"✓ Helper exists: {helper}")
            else:
                self.errors.append(f"✗ Missing helper: {helper}")

    def check_imports(self):
        """Check for common import issues."""
        python_files = list(self.base_path.glob("**/*.py"))

        for file in python_files:
            with open(file) as f:
                content = f.read()

            # Check for missing imports
            if "from .const import" in content:
                if not (self.base_path / "const.py").exists():
                    self.errors.append(f"✗ {file.name} imports missing const.py")

            # Check for circular imports
            if file.name == "__init__.py" and "from .sensor import" in content:
                self.warnings.append(f"⚠ Potential circular import in {file.name}")

    def print_results(self):
        """Print check results."""
        print("\n📊 RESULTS")
        print("=" * 50)

        if self.successes:
            print("\n✅ SUCCESSES:")
            for success in self.successes[:10]:  # Show first 10
                print(f"  {success}")
            if len(self.successes) > 10:
                print(f"  ... and {len(self.successes) - 10} more")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")

        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"  {error}")
        else:
            print("\n🎉 NO ERRORS FOUND!")

        print("\n" + "=" * 50)
        print(
            f"Total: {len(self.successes)} ✓ | {len(self.warnings)} ⚠ | {len(self.errors)} ✗"
        )

        if not self.errors:
            print("\n✨ Integration is ready for installation!")
        else:
            print("\n⚠️  Please fix errors before installation.")


if __name__ == "__main__":
    checker = IntegrationChecker()
    if not checker.check_all():
        sys.exit(1)
