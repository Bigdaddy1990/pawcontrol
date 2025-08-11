#!/usr/bin/env python3
"""Validation script for Paw Control Home Assistant Integration."""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any
import ast


class IntegrationValidator:
    """Validate Paw Control integration."""

    def __init__(self, integration_path: str = "custom_components/pawcontrol"):
        """Initialize validator."""
        self.path = Path(integration_path)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def validate_all(self) -> bool:
        """Run all validation checks."""
        print("🔍 Starting Paw Control Integration Validation...\n")

        # Check if path exists
        if not self.path.exists():
            self.errors.append(f"Integration path not found: {self.path}")
            return False

        # Run all checks
        self.check_manifest()
        self.check_python_syntax()
        self.check_services_yaml()
        self.check_strings_json()
        self.check_imports()
        self.check_hacs_config()
        self.check_required_files()

        # Report results
        self.print_results()

        return len(self.errors) == 0

    def check_manifest(self) -> None:
        """Validate manifest.json."""
        manifest_path = self.path / "manifest.json"

        if not manifest_path.exists():
            self.errors.append("manifest.json not found")
            return

        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            # Check required fields
            required_fields = [
                "domain",
                "name",
                "version",
                "documentation",
                "issue_tracker",
                "codeowners",
                "config_flow",
                "iot_class",
                "integration_type",
            ]

            for field in required_fields:
                if field not in manifest:
                    self.errors.append(f"manifest.json missing required field: {field}")

            # Check recommended fields
            recommended_fields = ["quality_scale", "homekit"]
            for field in recommended_fields:
                if field not in manifest:
                    self.warnings.append(
                        f"manifest.json missing recommended field: {field}"
                    )

            # Validate version format
            if "version" in manifest:
                version = manifest["version"]
                if not self._validate_version(version):
                    self.warnings.append(f"Version format not semantic: {version}")

            self.info.append(
                f"✅ manifest.json valid - Version: {manifest.get('version', 'unknown')}"
            )

        except json.JSONDecodeError as e:
            self.errors.append(f"manifest.json invalid JSON: {e}")
        except Exception as e:
            self.errors.append(f"Error reading manifest.json: {e}")

    def check_python_syntax(self) -> None:
        """Check Python syntax for all .py files."""
        py_files = list(self.path.glob("**/*.py"))

        for py_file in py_files:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    source = f.read()

                # Compile to check syntax
                compile(source, py_file, "exec")

                # Parse AST to check for type hints
                tree = ast.parse(source)
                has_type_hints = self._check_type_hints(tree)

                if not has_type_hints:
                    self.warnings.append(
                        f"{py_file.name} lacks comprehensive type hints"
                    )

            except SyntaxError as e:
                self.errors.append(f"Syntax error in {py_file.name}: {e}")
            except Exception as e:
                self.errors.append(f"Error checking {py_file.name}: {e}")

        if not any("Syntax error" in err for err in self.errors):
            self.info.append(f"✅ Python syntax valid for {len(py_files)} files")

    def check_services_yaml(self) -> None:
        """Validate services.yaml."""
        services_path = self.path / "services.yaml"

        if not services_path.exists():
            self.warnings.append("services.yaml not found - Services may not have UI")
            return

        try:
            import yaml

            with open(services_path, "r") as f:
                services = yaml.safe_load(f)

            if services:
                service_count = len(services)
                self.info.append(
                    f"✅ services.yaml valid - {service_count} services defined"
                )

                # Check if all services have schemas
                for service_name, service_def in services.items():
                    if not service_def.get("fields"):
                        self.warnings.append(
                            f"Service '{service_name}' has no fields defined"
                        )

        except ImportError:
            self.warnings.append("PyYAML not installed - Cannot validate services.yaml")
        except Exception as e:
            self.errors.append(f"Error parsing services.yaml: {e}")

    def check_strings_json(self) -> None:
        """Validate strings.json."""
        strings_path = self.path / "strings.json"

        if not strings_path.exists():
            self.errors.append("strings.json not found - Required for config flow")
            return

        try:
            with open(strings_path, "r") as f:
                strings = json.load(f)

            # Check required sections
            required_sections = ["title", "config"]
            for section in required_sections:
                if section not in strings:
                    self.errors.append(
                        f"strings.json missing required section: {section}"
                    )

            self.info.append("✅ strings.json valid")

        except json.JSONDecodeError as e:
            self.errors.append(f"strings.json invalid JSON: {e}")
        except Exception as e:
            self.errors.append(f"Error reading strings.json: {e}")

    def check_imports(self) -> None:
        """Check if all imports are valid."""
        init_file = self.path / "__init__.py"

        if not init_file.exists():
            self.errors.append("__init__.py not found")
            return

        try:
            with open(init_file, "r") as f:
                source = f.read()

            tree = ast.parse(source)

            # Check for schema imports
            imports = [
                node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            ]
            has_schema_import = any(imp.module == ".schemas" for imp in imports)

            if has_schema_import:
                # Check if schemas.py exists
                schemas_path = self.path / "schemas.py"
                if not schemas_path.exists():
                    self.errors.append("schemas.py imported but not found")
                else:
                    self.info.append("✅ Service schema validation configured")

        except Exception as e:
            self.errors.append(f"Error checking imports: {e}")

    def check_hacs_config(self) -> None:
        """Check HACS configuration."""
        hacs_path = self.path.parent.parent / "hacs.json"

        if not hacs_path.exists():
            self.warnings.append("hacs.json not found - HACS installation may not work")
            return

        try:
            with open(hacs_path, "r") as f:
                hacs = json.load(f)

            required_fields = ["name", "render_readme"]
            for field in required_fields:
                if field not in hacs:
                    self.warnings.append(f"hacs.json missing field: {field}")

            self.info.append("✅ hacs.json valid")

        except Exception as e:
            self.warnings.append(f"Error reading hacs.json: {e}")

    def check_required_files(self) -> None:
        """Check for all required files."""
        required_files = [
            "__init__.py",
            "manifest.json",
            "config_flow.py",
            "const.py",
            "coordinator.py",
        ]

        missing_files = []
        for file_name in required_files:
            file_path = self.path / file_name
            if not file_path.exists():
                missing_files.append(file_name)

        if missing_files:
            self.errors.append(f"Missing required files: {', '.join(missing_files)}")
        else:
            self.info.append("✅ All required files present")

    def _validate_version(self, version: str) -> bool:
        """Validate semantic version format."""
        try:
            parts = version.split(".")
            return len(parts) == 3 and all(p.isdigit() for p in parts)
        except:
            return False

    def _check_type_hints(self, tree: ast.AST) -> bool:
        """Check if AST has type hints."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check return type
                if node.returns:
                    return True
                # Check parameter types
                for arg in node.args.args:
                    if arg.annotation:
                        return True
        return False

    def print_results(self) -> None:
        """Print validation results."""
        print("=" * 60)
        print("VALIDATION RESULTS")
        print("=" * 60)

        # Print info
        if self.info:
            print("\n📋 INFO:")
            for msg in self.info:
                print(f"  {msg}")

        # Print warnings
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for msg in self.warnings:
                print(f"  - {msg}")

        # Print errors
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for msg in self.errors:
                print(f"  - {msg}")

        # Summary
        print("\n" + "=" * 60)
        if not self.errors:
            print("✅ VALIDATION PASSED - Integration is ready!")
            if self.warnings:
                print(f"   ({len(self.warnings)} warnings to review)")
        else:
            print(f"❌ VALIDATION FAILED - {len(self.errors)} errors must be fixed")
        print("=" * 60)


def main():
    """Run validation."""
    # Get path from command line or use default
    if len(sys.argv) > 1:
        integration_path = sys.argv[1]
    else:
        # Try to find the integration
        if Path("custom_components/pawcontrol").exists():
            integration_path = "custom_components/pawcontrol"
        elif Path("pawcontrol").exists():
            integration_path = "pawcontrol"
        else:
            integration_path = "D:\\Downloads\\Clause\\custom_components\\pawcontrol"

    validator = IntegrationValidator(integration_path)
    success = validator.validate_all()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
