#!/usr/bin/env python3
"""Comprehensive hassfest and HACS validation for PawControl integration.

Validates integration against Home Assistant's hassfest tool requirements
and HACS distribution standards for Gold Standard compliance.

Usage: python hassfest_hacs_validation.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

class HassfestHACSValidator:
    """Validates integration against hassfest and HACS requirements."""

    def __init__(self, base_path: Path):
        """Initialize validator with integration path."""
        self.base_path = base_path
        self.integration_path = base_path / "custom_components" / "pawcontrol"

        # Validation tracking
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

        # Manifest data
        self.manifest: Optional[Dict[str, Any]] = None
        self.load_manifest()

    def load_manifest(self) -> None:
        """Load and validate manifest.json."""
        manifest_path = self.integration_path / "manifest.json"

        if not manifest_path.exists():
            self.errors.append("manifest.json not found")
            return

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                self.manifest = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in manifest.json: {e}")
        except Exception as e:
            self.errors.append(f"Could not read manifest.json: {e}")

    def validate_all(self) -> bool:
        """Run all validation checks.

        Returns:
            True if all validations pass
        """
        print("🔍 HASSFEST & HACS VALIDATION")
        print("=" * 50)

        if not self.manifest:
            print("❌ Cannot proceed without valid manifest.json")
            return False

        checks = [
            ("Manifest Structure", self.validate_manifest_structure),
            ("File Structure", self.validate_file_structure),
            ("Code Quality", self.validate_code_quality),
            ("Dependencies", self.validate_dependencies),
            ("Translations", self.validate_translations),
            ("Services", self.validate_services),
            ("Discovery", self.validate_discovery_protocols),
            ("HACS Requirements", self.validate_hacs_requirements),
            ("Quality Scale", self.validate_quality_scale),
            ("Documentation", self.validate_documentation),
        ]

        for check_name, check_func in checks:
            print(f"\n📋 {check_name}...")
            try:
                check_func()
                print(f"  ✅ {check_name} passed")
            except Exception as e:
                self.errors.append(f"{check_name}: {e}")
                print(f"  ❌ {check_name} failed: {e}")

        # Print summary
        self._print_validation_summary()

        return len(self.errors) == 0

    def validate_manifest_structure(self) -> None:
        """Validate manifest.json structure and content."""
        required_keys = [
            "domain", "name", "codeowners", "config_flow", "documentation",
            "iot_class", "issue_tracker", "quality_scale", "requirements", "version"
        ]

        for key in required_keys:
            if key not in self.manifest:
                raise ValueError(f"Missing required key: {key}")

        # Validate specific field formats
        domain = self.manifest.get("domain", "")
        if not re.match(r"^[a-z_][a-z0-9_]*$", domain):
            raise ValueError(f"Invalid domain format: {domain}")

        version = self.manifest.get("version", "")
        if not re.match(r"^\d+\.\d+\.\d+$", version):
            self.warnings.append(f"Version should use semantic versioning: {version}")

        # Validate quality scale
        quality_scale = self.manifest.get("quality_scale", "")
        valid_scales = ["bronze", "silver", "gold", "platinum"]
        if quality_scale not in valid_scales:
            raise ValueError(f"Invalid quality_scale: {quality_scale}")

        # Validate codeowners format
        codeowners = self.manifest.get("codeowners", [])
        if not isinstance(codeowners, list) or not codeowners:
            raise ValueError("codeowners must be a non-empty list")

        for owner in codeowners:
            if not owner.startswith("@"):
                raise ValueError(f"Codeowner must start with @: {owner}")

        # Validate URLs
        urls_to_check = ["documentation", "issue_tracker"]
        for url_key in urls_to_check:
            url = self.manifest.get(url_key, "")
            if url and not url.startswith(("http://", "https://")):
                raise ValueError(f"Invalid URL for {url_key}: {url}")

        self.info.append("Manifest structure validation passed")

    def validate_file_structure(self) -> None:
        """Validate required file structure."""
        required_files = [
            "__init__.py",
            "manifest.json",
            "config_flow.py",
            "const.py",
            "strings.json",
            "translations/en.json",
        ]

        for file_path in required_files:
            full_path = self.integration_path / file_path
            if not full_path.exists():
                raise FileNotFoundError(f"Required file missing: {file_path}")

        # Check for platform files mentioned in manifest
        config_flow = self.manifest.get("config_flow", False)
        if config_flow and not (self.integration_path / "config_flow.py").exists():
            raise FileNotFoundError("config_flow.py required when config_flow: true")

        # Validate Python files are valid
        py_files = list(self.integration_path.glob("*.py"))
        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Basic syntax check
                compile(content, str(py_file), 'exec')

            except SyntaxError as e:
                raise SyntaxError(f"Syntax error in {py_file.name}: {e}")
            except UnicodeDecodeError:
                raise ValueError(f"File {py_file.name} must be UTF-8 encoded")

        self.info.append("File structure validation passed")

    def validate_code_quality(self) -> None:
        """Validate code quality standards."""
        py_files = list(self.integration_path.glob("*.py"))

        for py_file in py_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()

            # Check for future annotations
            if py_file.name != "__init__.py":
                if "from __future__ import annotations" not in content:
                    self.warnings.append(f"{py_file.name}: Missing future annotations import")

            # Check for proper async usage
            if "async def" in content and "time.sleep(" in content:
                raise ValueError(f"{py_file.name}: Uses time.sleep in async function")

            # Check for deprecated APIs
            deprecated_patterns = [
                (r"async_get_registry", "Use async_get instead"),
                (r"hass\.loop", "Don't access event loop directly"),
                (r"SUPPORT_", "Use new feature constants"),
            ]

            for line_num, line in enumerate(lines, 1):
                for pattern, suggestion in deprecated_patterns:
                    if re.search(pattern, line):
                        self.warnings.append(
                            f"{py_file.name}:{line_num}: Deprecated API - {suggestion}"
                        )

            # Check for proper logging
            if "logging" in content and "_LOGGER = " not in content:
                self.warnings.append(f"{py_file.name}: Should use module-level logger")

        self.info.append("Code quality validation passed")

    def validate_dependencies(self) -> None:
        """Validate dependencies and requirements."""
        dependencies = self.manifest.get("dependencies", [])
        requirements = self.manifest.get("requirements", [])

        # Validate dependencies format
        if not isinstance(dependencies, list):
            raise ValueError("dependencies must be a list")

        # Check for circular dependencies
        domain = self.manifest.get("domain", "")
        if domain in dependencies:
            raise ValueError("Domain cannot depend on itself")

        # Validate requirements format
        if not isinstance(requirements, list):
            raise ValueError("requirements must be a list")

        for req in requirements:
            if not isinstance(req, str):
                raise ValueError(f"Invalid requirement format: {req}")

            # Check for version specifiers
            if not re.match(r"^[a-zA-Z0-9_-]+([><=!]+[0-9.]+)?$", req):
                self.warnings.append(f"Unusual requirement format: {req}")

        # Check after_dependencies
        after_deps = self.manifest.get("after_dependencies", [])
        if after_deps and not isinstance(after_deps, list):
            raise ValueError("after_dependencies must be a list")

        self.info.append("Dependencies validation passed")

    def validate_translations(self) -> None:
        """Validate translation files."""
        translations_dir = self.integration_path / "translations"

        if not translations_dir.exists():
            raise FileNotFoundError("translations directory missing")

        # Check for English translation (required)
        en_file = translations_dir / "en.json"
        if not en_file.exists():
            raise FileNotFoundError("English translation file missing")

        # Validate translation structure
        try:
            with open(en_file, 'r', encoding='utf-8') as f:
                en_translations = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in en.json: {e}")

        # Check required sections
        required_sections = ["config"]
        config_flow = self.manifest.get("config_flow", False)
        if config_flow:
            required_sections.extend(["options", "abort", "error"])

        for section in required_sections:
            if section not in en_translations:
                self.warnings.append(f"Missing translation section: {section}")

        # Validate strings.json consistency
        strings_file = self.integration_path / "strings.json"
        if strings_file.exists():
            try:
                with open(strings_file, 'r', encoding='utf-8') as f:
                    strings_data = json.load(f)

                # Basic consistency check
                if "config" in both:= (en_translations, strings_data):
                    en_config_keys = set(en_translations.get("config", {}).keys())
                    strings_config_keys = set(strings_data.get("config", {}).keys())

                    if en_config_keys != strings_config_keys:
                        self.warnings.append("strings.json and en.json config keys don't match")

            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in strings.json: {e}")

        self.info.append("Translations validation passed")

    def validate_services(self) -> None:
        """Validate services configuration."""
        services_yaml = self.integration_path / "services.yaml"
        services_py = self.integration_path / "services.py"

        # If services.py exists, services.yaml should also exist
        if services_py.exists() and not services_yaml.exists():
            self.warnings.append("services.py exists but services.yaml missing")

        if services_yaml.exists():
            try:
                import yaml
                with open(services_yaml, 'r', encoding='utf-8') as f:
                    services_data = yaml.safe_load(f) or {}

                # Validate service structure
                for service_name, service_config in services_data.items():
                    if not isinstance(service_config, dict):
                        raise ValueError(f"Invalid service config for {service_name}")

                    # Check required fields
                    if "description" not in service_config:
                        self.warnings.append(f"Service {service_name} missing description")

            except ImportError:
                self.warnings.append("PyYAML not available for services validation")
            except Exception as e:
                raise ValueError(f"Error validating services.yaml: {e}")

        self.info.append("Services validation passed")

    def validate_discovery_protocols(self) -> None:
        """Validate discovery protocol configurations."""
        discovery_protocols = ["dhcp", "homekit", "mqtt", "ssdp", "usb", "zeroconf"]

        for protocol in discovery_protocols:
            if protocol in self.manifest:
                protocol_config = self.manifest[protocol]

                if not isinstance(protocol_config, list):
                    raise ValueError(f"{protocol} configuration must be a list")

                for item in protocol_config:
                    if not isinstance(item, dict):
                        raise ValueError(f"Invalid {protocol} item: must be dict")

                # Protocol-specific validation
                if protocol == "dhcp":
                    for item in protocol_config:
                        required_keys = ["hostname", "macaddress"]
                        for key in required_keys:
                            if key not in item:
                                raise ValueError(f"DHCP item missing {key}")

                elif protocol == "zeroconf":
                    for item in protocol_config:
                        if "type" not in item:
                            raise ValueError("Zeroconf item missing type")

        self.info.append("Discovery protocols validation passed")

    def validate_hacs_requirements(self) -> None:
        """Validate HACS distribution requirements."""
        # Check for HACS configuration file
        hacs_json = self.base_path / "hacs.json"
        if not hacs_json.exists():
            self.warnings.append("hacs.json missing - required for HACS distribution")
            return

        try:
            with open(hacs_json, 'r', encoding='utf-8') as f:
                hacs_config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in hacs.json: {e}")

        # Validate HACS configuration
        required_hacs_keys = ["name"]
        for key in required_hacs_keys:
            if key not in hacs_config:
                self.warnings.append(f"HACS config missing {key}")

        # Check for README
        readme_files = ["README.md", "readme.md", "README.rst"]
        if not any((self.base_path / readme).exists() for readme in readme_files):
            self.warnings.append("README file missing")

        # Check for proper repository structure
        required_dirs = ["custom_components"]
        for dir_name in required_dirs:
            if not (self.base_path / dir_name).exists():
                raise FileNotFoundError(f"Required directory missing: {dir_name}")

        # Validate integration name matches directory
        domain = self.manifest.get("domain", "")
        integration_dir = self.base_path / "custom_components" / domain
        if not integration_dir.exists():
            raise FileNotFoundError(f"Integration directory {domain} not found")

        self.info.append("HACS requirements validation passed")

    def validate_quality_scale(self) -> None:
        """Validate quality scale requirements."""
        quality_scale = self.manifest.get("quality_scale", "")

        if quality_scale == "platinum":
            # Platinum requirements
            platinum_requirements = [
                ("diagnostics.py", "Diagnostics platform required"),
                ("repairs.py", "Repairs platform required"),
            ]

            for file_name, description in platinum_requirements:
                if not (self.integration_path / file_name).exists():
                    self.warnings.append(f"Platinum quality: {description}")

            # Check for proper async usage
            init_file = self.integration_path / "__init__.py"
            if init_file.exists():
                with open(init_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                if "async def async_setup" not in content:
                    self.warnings.append("Platinum quality: async_setup should be async")

        elif quality_scale == "gold":
            # Gold requirements
            required_files = ["config_flow.py"]
            for file_name in required_files:
                if not (self.integration_path / file_name).exists():
                    self.warnings.append(f"Gold quality: {file_name} required")

        self.info.append(f"Quality scale ({quality_scale}) validation passed")

    def validate_documentation(self) -> None:
        """Validate documentation requirements."""
        # Check documentation URL
        doc_url = self.manifest.get("documentation", "")
        if not doc_url:
            self.warnings.append("Documentation URL missing")
        elif not doc_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid documentation URL: {doc_url}")

        # Check issue tracker URL
        issue_url = self.manifest.get("issue_tracker", "")
        if not issue_url:
            self.warnings.append("Issue tracker URL missing")
        elif not issue_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid issue tracker URL: {issue_url}")

        # Check for inline documentation
        py_files = list(self.integration_path.glob("*.py"))
        files_with_docstrings = 0

        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue

            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check for module docstring
            if '"""' in content[:500]:  # Docstring should be near top
                files_with_docstrings += 1

        docstring_ratio = files_with_docstrings / max(1, len(py_files))
        if docstring_ratio < 0.8:  # At least 80% should have docstrings
            self.warnings.append(f"Low docstring coverage: {docstring_ratio:.1%}")

        self.info.append("Documentation validation passed")

    def _print_validation_summary(self) -> None:
        """Print comprehensive validation summary."""
        print("\n" + "=" * 50)
        print("HASSFEST & HACS VALIDATION SUMMARY")
        print("=" * 50)

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  • {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings[:10]:  # Show first 10
                print(f"  • {warning}")
            if len(self.warnings) > 10:
                print(f"  ... and {len(self.warnings) - 10} more")

        if self.info:
            print(f"\n✅ PASSED CHECKS ({len(self.info)}):")
            for info in self.info:
                print(f"  • {info}")

        print("\n" + "=" * 50)

        if not self.errors:
            print("🎉 HASSFEST & HACS VALIDATION PASSED!")
            print("✅ Integration meets distribution standards")
        else:
            print("❌ VALIDATION FAILED")
            print("🔧 Fix errors before distribution")

        print("=" * 50)


def main():
    """Main validation entry point."""
    base_path = Path(__file__).parent

    validator = HassfestHACSValidator(base_path)
    success = validator.validate_all()

    # Return appropriate exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
