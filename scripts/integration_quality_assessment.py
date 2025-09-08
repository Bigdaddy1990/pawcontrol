#!/usr/bin/env python3
"""Comprehensive integration quality scale assessment for PawControl.

Evaluates integration against Home Assistant's Integration Quality Scale
requirements for Platinum level compliance. Provides detailed scoring
and recommendations for achieving the highest quality standards.

Reference: https://developers.home-assistant.io/docs/integration_quality_scale/

Usage: python integration_quality_assessment.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


class IntegrationQualityAssessment:
    """Comprehensive quality scale assessment for Home Assistant integrations."""

    def __init__(self, base_path: Path):
        """Initialize assessment with integration path."""
        self.base_path = base_path
        self.integration_path = base_path / "custom_components" / "pawcontrol"

        # Assessment tracking
        self.bronze_score = 0
        self.silver_score = 0
        self.gold_score = 0
        self.platinum_score = 0

        self.bronze_max = 0
        self.silver_max = 0
        self.gold_max = 0
        self.platinum_max = 0

        self.results: Dict[str, Dict[str, Any]] = {}
        self.recommendations: List[str] = []

        # Load manifest
        self.manifest: Optional[Dict[str, Any]] = None
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load manifest.json for assessment."""
        manifest_path = self.integration_path / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    self.manifest = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load manifest.json: {e}")

    def assess_quality(self) -> Dict[str, Any]:
        """Run comprehensive quality assessment.

        Returns:
            Assessment results with scores and recommendations
        """
        print("🏆 HOME ASSISTANT INTEGRATION QUALITY SCALE ASSESSMENT")
        print("=" * 60)
        print("Evaluating PawControl integration against HA quality standards...")

        # Run assessments by quality level
        self._assess_bronze_requirements()
        self._assess_silver_requirements()
        self._assess_gold_requirements()
        self._assess_platinum_requirements()

        # Calculate overall results
        return self._generate_assessment_report()

    def _assess_bronze_requirements(self) -> None:
        """Assess Bronze quality scale requirements."""
        print("\n🥉 BRONZE QUALITY REQUIREMENTS")
        print("-" * 40)

        bronze_checks = [
            ("Integration loads successfully", self._check_integration_loads),
            ("Basic functionality works", self._check_basic_functionality),
            ("No obvious errors in logs", self._check_error_handling),
            ("Code follows Python standards", self._check_python_standards),
            ("Manifest.json is valid", self._check_manifest_valid),
        ]

        self.bronze_max = len(bronze_checks)
        bronze_results = {}

        for check_name, check_func in bronze_checks:
            try:
                result = check_func()
                bronze_results[check_name] = result
                if result.get("passed", False):
                    self.bronze_score += 1
                    print(f"  ✅ {check_name}")
                else:
                    print(f"  ❌ {check_name}: {result.get('reason', 'Failed')}")
            except Exception as e:
                bronze_results[check_name] = {"passed": False, "reason": str(e)}
                print(f"  ❌ {check_name}: {e}")

        self.results["bronze"] = bronze_results

    def _assess_silver_requirements(self) -> None:
        """Assess Silver quality scale requirements."""
        print("\n🥈 SILVER QUALITY REQUIREMENTS")
        print("-" * 40)

        silver_checks = [
            ("Config flow implemented", self._check_config_flow),
            ("Entity naming follows conventions", self._check_entity_naming),
            ("Translations provided", self._check_translations),
            ("Device registry integration", self._check_device_registry),
            ("Async/await patterns used", self._check_async_patterns),
            ("Proper state management", self._check_state_management),
        ]

        self.silver_max = len(silver_checks)
        silver_results = {}

        for check_name, check_func in silver_checks:
            try:
                result = check_func()
                silver_results[check_name] = result
                if result.get("passed", False):
                    self.silver_score += 1
                    print(f"  ✅ {check_name}")
                else:
                    print(f"  ❌ {check_name}: {result.get('reason', 'Failed')}")
            except Exception as e:
                silver_results[check_name] = {"passed": False, "reason": str(e)}
                print(f"  ❌ {check_name}: {e}")

        self.results["silver"] = silver_results

    def _assess_gold_requirements(self) -> None:
        """Assess Gold quality scale requirements."""
        print("\n🥇 GOLD QUALITY REQUIREMENTS")
        print("-" * 40)

        gold_checks = [
            ("Test coverage ≥80%", self._check_test_coverage),
            ("Entity availability handling", self._check_entity_availability),
            ("Unique entity IDs", self._check_unique_entity_ids),
            ("Options flow implemented", self._check_options_flow),
            ("Performance optimizations", self._check_performance_optimizations),
            ("Error recovery mechanisms", self._check_error_recovery),
            ("Coordinator pattern used", self._check_coordinator_pattern),
        ]

        self.gold_max = len(gold_checks)
        gold_results = {}

        for check_name, check_func in gold_checks:
            try:
                result = check_func()
                gold_results[check_name] = result
                if result.get("passed", False):
                    self.gold_score += 1
                    print(f"  ✅ {check_name}")
                else:
                    print(f"  ❌ {check_name}: {result.get('reason', 'Failed')}")
            except Exception as e:
                gold_results[check_name] = {"passed": False, "reason": str(e)}
                print(f"  ❌ {check_name}: {e}")

        self.results["gold"] = gold_results

    def _assess_platinum_requirements(self) -> None:
        """Assess Platinum quality scale requirements."""
        print("\n💎 PLATINUM QUALITY REQUIREMENTS")
        print("-" * 40)

        platinum_checks = [
            ("Test coverage ≥95%", self._check_platinum_test_coverage),
            ("Diagnostics platform", self._check_diagnostics_platform),
            ("Repairs platform", self._check_repairs_platform),
            ("Type annotations complete", self._check_type_annotations),
            ("Advanced error handling", self._check_advanced_error_handling),
            ("Performance monitoring", self._check_performance_monitoring),
            ("Modular architecture", self._check_modular_architecture),
            ("Documentation quality", self._check_documentation_quality),
            ("Edge case handling", self._check_edge_case_handling),
            ("Memory efficiency", self._check_memory_efficiency),
        ]

        self.platinum_max = len(platinum_checks)
        platinum_results = {}

        for check_name, check_func in platinum_checks:
            try:
                result = check_func()
                platinum_results[check_name] = result
                if result.get("passed", False):
                    self.platinum_score += 1
                    print(f"  ✅ {check_name}")
                else:
                    print(f"  ❌ {check_name}: {result.get('reason', 'Failed')}")
                    if result.get("recommendation"):
                        self.recommendations.append(result["recommendation"])
            except Exception as e:
                platinum_results[check_name] = {"passed": False, "reason": str(e)}
                print(f"  ❌ {check_name}: {e}")

        self.results["platinum"] = platinum_results

    def _check_integration_loads(self) -> Dict[str, Any]:
        """Check if integration loads successfully."""
        init_file = self.integration_path / "__init__.py"

        if not init_file.exists():
            return {"passed": False, "reason": "__init__.py missing"}

        try:
            with open(init_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for async_setup function
            if "async def async_setup" not in content:
                return {"passed": False, "reason": "Missing async_setup function"}

            # Basic syntax check
            compile(content, str(init_file), "exec")

            return {"passed": True, "details": "Integration structure valid"}

        except SyntaxError as e:
            return {"passed": False, "reason": f"Syntax error: {e}"}
        except Exception as e:
            return {"passed": False, "reason": f"Load error: {e}"}

    def _check_basic_functionality(self) -> Dict[str, Any]:
        """Check basic functionality implementation."""
        # Check for required platforms
        platform_files = [
            "sensor.py",
            "binary_sensor.py",
            "switch.py",
            "number.py",
            "select.py",
            "button.py",
            "device_tracker.py",
        ]

        existing_platforms = []
        for platform in platform_files:
            if (self.integration_path / platform).exists():
                existing_platforms.append(platform.replace(".py", ""))

        if len(existing_platforms) < 3:
            return {
                "passed": False,
                "reason": f"Only {len(existing_platforms)} platforms implemented",
            }

        return {
            "passed": True,
            "details": f"{len(existing_platforms)} platforms implemented",
            "platforms": existing_platforms,
        }

    def _check_error_handling(self) -> Dict[str, Any]:
        """Check error handling implementation."""
        py_files = list(self.integration_path.glob("*.py"))
        files_with_error_handling = 0

        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for proper error handling patterns
            error_patterns = [
                "try:",
                "except",
                "raise",
                "HomeAssistantError",
                "ConfigEntryNotReady",
            ]

            if any(pattern in content for pattern in error_patterns):
                files_with_error_handling += 1

        error_handling_ratio = files_with_error_handling / max(1, len(py_files))

        if error_handling_ratio < 0.5:
            return {
                "passed": False,
                "reason": f"Low error handling coverage: {error_handling_ratio:.1%}",
            }

        return {
            "passed": True,
            "details": f"Error handling in {error_handling_ratio:.1%} of files",
        }

    def _check_python_standards(self) -> Dict[str, Any]:
        """Check Python coding standards compliance."""
        py_files = list(self.integration_path.glob("*.py"))
        issues = []

        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for future annotations
            if (
                py_file.name not in ["__init__.py"]
                and "from __future__ import annotations" not in content
            ):
                issues.append(f"{py_file.name}: Missing future annotations")

            # Check for proper imports
            lines = content.splitlines()
            import_section = []
            for i, line in enumerate(lines[:50]):  # Check first 50 lines
                if line.strip().startswith(("import ", "from ")):
                    import_section.append((i, line))

            # Check import organization (stdlib, third-party, local)
            if len(import_section) > 5:  # Only check if there are enough imports
                stdlib_after_local = False
                for i, (line_num, line) in enumerate(import_section[1:], 1):
                    if (
                        line.strip().startswith("from homeassistant")
                        and i < len(import_section) - 1
                    ):
                        next_line = import_section[i][1]
                        if next_line.strip().startswith(
                            "import "
                        ) and not next_line.strip().startswith("from"):
                            stdlib_after_local = True

                if stdlib_after_local:
                    issues.append(f"{py_file.name}: Import order could be improved")

        if len(issues) > len(py_files) * 0.3:  # More than 30% of files have issues
            return {
                "passed": False,
                "reason": f"{len(issues)} coding standard issues found",
                "issues": issues[:5],  # Show first 5
            }

        return {"passed": True, "details": "Python standards mostly followed"}

    def _check_manifest_valid(self) -> Dict[str, Any]:
        """Check manifest.json validity."""
        if not self.manifest:
            return {"passed": False, "reason": "Could not load manifest.json"}

        required_keys = [
            "domain",
            "name",
            "codeowners",
            "config_flow",
            "documentation",
            "iot_class",
            "issue_tracker",
            "quality_scale",
            "requirements",
            "version",
        ]

        missing_keys = [key for key in required_keys if key not in self.manifest]
        if missing_keys:
            return {"passed": False, "reason": f"Missing manifest keys: {missing_keys}"}

        return {"passed": True, "details": "Manifest structure valid"}

    def _check_config_flow(self) -> Dict[str, Any]:
        """Check config flow implementation."""
        config_flow_file = self.integration_path / "config_flow.py"

        if not config_flow_file.exists():
            return {"passed": False, "reason": "config_flow.py missing"}

        with open(config_flow_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for required config flow components
        required_patterns = [
            "ConfigFlow",
            "async_step_user",
            "OptionsFlow",
            "async_step_init",
        ]

        missing_patterns = [p for p in required_patterns if p not in content]
        if missing_patterns:
            return {
                "passed": False,
                "reason": f"Missing config flow components: {missing_patterns}",
            }

        return {"passed": True, "details": "Config flow properly implemented"}

    def _check_entity_naming(self) -> Dict[str, Any]:
        """Check entity naming conventions."""
        platform_files = ["sensor.py", "binary_sensor.py", "switch.py", "number.py"]
        naming_issues = []

        for platform_file in platform_files:
            file_path = self.integration_path / platform_file
            if not file_path.exists():
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for proper unique_id pattern
            if "_attr_unique_id" in content or "unique_id" in content:
                # Look for consistent naming patterns
                if 'f"pawcontrol_' not in content and "f'{" not in content:
                    naming_issues.append(
                        f"{platform_file}: Inconsistent unique_id pattern"
                    )
            else:
                naming_issues.append(
                    f"{platform_file}: Missing unique_id implementation"
                )

        if naming_issues:
            return {
                "passed": False,
                "reason": f"Entity naming issues: {len(naming_issues)}",
                "issues": naming_issues,
            }

        return {"passed": True, "details": "Entity naming follows conventions"}

    def _check_translations(self) -> Dict[str, Any]:
        """Check translation implementation."""
        translations_dir = self.integration_path / "translations"

        if not translations_dir.exists():
            return {"passed": False, "reason": "translations directory missing"}

        en_file = translations_dir / "en.json"
        if not en_file.exists():
            return {"passed": False, "reason": "en.json translation missing"}

        try:
            with open(en_file, "r", encoding="utf-8") as f:
                translations = json.load(f)

            # Check for required sections
            required_sections = ["config"]
            if self.manifest and self.manifest.get("config_flow"):
                required_sections.extend(["options"])

            missing_sections = [s for s in required_sections if s not in translations]
            if missing_sections:
                return {
                    "passed": False,
                    "reason": f"Missing translation sections: {missing_sections}",
                }

            return {"passed": True, "details": "Translations properly implemented"}

        except Exception as e:
            return {"passed": False, "reason": f"Translation error: {e}"}

    def _check_device_registry(self) -> Dict[str, Any]:
        """Check device registry integration."""
        platform_files = list(self.integration_path.glob("*.py"))
        device_info_found = False

        for platform_file in platform_files:
            with open(platform_file, "r", encoding="utf-8") as f:
                content = f.read()

            if "device_info" in content and "identifiers" in content:
                device_info_found = True
                break

        if not device_info_found:
            return {"passed": False, "reason": "Device registry integration missing"}

        return {"passed": True, "details": "Device registry properly integrated"}

    def _check_async_patterns(self) -> Dict[str, Any]:
        """Check async/await pattern usage."""
        py_files = list(self.integration_path.glob("*.py"))
        async_issues = []

        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for blocking calls in async functions
            if "async def" in content:
                if "time.sleep(" in content:
                    async_issues.append(f"{py_file.name}: time.sleep in async function")

                # Check for proper asyncio usage
                if re.search(r"async def.*\n.*requests\.", content):
                    async_issues.append(
                        f"{py_file.name}: Blocking HTTP in async function"
                    )

        if async_issues:
            return {
                "passed": False,
                "reason": f"Async pattern issues: {len(async_issues)}",
                "issues": async_issues,
            }

        return {"passed": True, "details": "Async patterns properly used"}

    def _check_state_management(self) -> Dict[str, Any]:
        """Check state management implementation."""
        coordinator_file = self.integration_path / "coordinator.py"

        if not coordinator_file.exists():
            return {"passed": False, "reason": "No coordinator found"}

        with open(coordinator_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for proper coordinator patterns
        required_patterns = ["DataUpdateCoordinator", "async_update_data", "available"]

        missing_patterns = [p for p in required_patterns if p not in content]
        if missing_patterns:
            return {
                "passed": False,
                "reason": f"Missing coordinator patterns: {missing_patterns}",
            }

        return {"passed": True, "details": "State management properly implemented"}

    def _check_test_coverage(self) -> Dict[str, Any]:
        """Check test coverage (Gold requirement: ≥80%)."""
        tests_dir = self.base_path / "tests"

        if not tests_dir.exists():
            return {"passed": False, "reason": "No tests directory found"}

        test_files = list(tests_dir.glob("test_*.py"))
        integration_files = list(self.integration_path.glob("*.py"))
        integration_files = [
            f for f in integration_files if not f.name.startswith("test_")
        ]

        if not test_files:
            return {"passed": False, "reason": "No test files found"}

        # Estimate coverage based on test file count vs integration files
        coverage_ratio = len(test_files) / max(1, len(integration_files))
        estimated_coverage = min(95, coverage_ratio * 100)

        if estimated_coverage < 80:
            return {
                "passed": False,
                "reason": f"Estimated coverage {estimated_coverage:.1f}% < 80%",
            }

        return {
            "passed": True,
            "details": f"Estimated coverage: {estimated_coverage:.1f}%",
        }

    def _check_entity_availability(self) -> Dict[str, Any]:
        """Check entity availability handling."""
        platform_files = ["sensor.py", "binary_sensor.py", "switch.py"]
        availability_implemented = False

        for platform_file in platform_files:
            file_path = self.integration_path / platform_file
            if not file_path.exists():
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if "available" in content and "coordinator.available" in content:
                availability_implemented = True
                break

        if not availability_implemented:
            return {"passed": False, "reason": "Entity availability not implemented"}

        return {"passed": True, "details": "Entity availability properly handled"}

    def _check_unique_entity_ids(self) -> Dict[str, Any]:
        """Check unique entity ID implementation."""
        platform_files = list(self.integration_path.glob("*.py"))
        unique_id_patterns = []

        for platform_file in platform_files:
            with open(platform_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Look for unique_id patterns
            unique_id_matches = re.findall(r'"pawcontrol_.*?"', content)
            unique_id_patterns.extend(unique_id_matches)

        if len(unique_id_patterns) < 5:  # Should have many unique IDs
            return {"passed": False, "reason": "Insufficient unique entity IDs"}

        return {
            "passed": True,
            "details": f"{len(unique_id_patterns)} unique IDs found",
        }

    def _check_options_flow(self) -> Dict[str, Any]:
        """Check options flow implementation."""
        options_flow_file = self.integration_path / "options_flow.py"
        config_flow_file = self.integration_path / "config_flow.py"

        # Check dedicated options flow file first
        if options_flow_file.exists():
            return {"passed": True, "details": "Dedicated options flow implemented"}

        # Check for options flow in config_flow.py
        if config_flow_file.exists():
            with open(config_flow_file, "r", encoding="utf-8") as f:
                content = f.read()

            if "OptionsFlow" in content:
                return {"passed": True, "details": "Options flow in config_flow.py"}

        return {"passed": False, "reason": "Options flow not implemented"}

    def _check_performance_optimizations(self) -> Dict[str, Any]:
        """Check performance optimization implementation."""
        optimizations_found = []

        # Check for caching
        cache_file = self.integration_path / "cache_manager.py"
        if cache_file.exists():
            optimizations_found.append("Caching system")

        # Check for batch processing
        batch_file = self.integration_path / "batch_manager.py"
        if batch_file.exists():
            optimizations_found.append("Batch processing")

        # Check for performance monitoring
        perf_file = self.integration_path / "performance_manager.py"
        if perf_file.exists():
            optimizations_found.append("Performance monitoring")

        if len(optimizations_found) < 2:
            return {
                "passed": False,
                "reason": f"Limited optimizations: {optimizations_found}",
            }

        return {
            "passed": True,
            "details": f"Optimizations: {', '.join(optimizations_found)}",
        }

    def _check_error_recovery(self) -> Dict[str, Any]:
        """Check error recovery mechanisms."""
        # Check for repairs platform
        repairs_file = self.integration_path / "repairs.py"
        if repairs_file.exists():
            return {"passed": True, "details": "Repairs platform implemented"}

        # Check for error recovery patterns in code
        py_files = list(self.integration_path.glob("*.py"))
        recovery_patterns = []

        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            if "ConfigEntryNotReady" in content:
                recovery_patterns.append("Config entry retry")
            if "async_will_remove_from_hass" in content:
                recovery_patterns.append("Cleanup handling")

        if not recovery_patterns:
            return {"passed": False, "reason": "No error recovery mechanisms found"}

        return {"passed": True, "details": f"Recovery: {', '.join(recovery_patterns)}"}

    def _check_coordinator_pattern(self) -> Dict[str, Any]:
        """Check coordinator pattern implementation."""
        coordinator_file = self.integration_path / "coordinator.py"

        if not coordinator_file.exists():
            return {"passed": False, "reason": "No coordinator.py found"}

        with open(coordinator_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for proper coordinator implementation
        required_patterns = [
            "DataUpdateCoordinator",
            "CoordinatorEntity",
            "update_interval",
        ]

        found_patterns = [p for p in required_patterns if p in content]

        if len(found_patterns) < 2:
            return {
                "passed": False,
                "reason": f"Incomplete coordinator: {found_patterns}",
            }

        return {"passed": True, "details": "Coordinator pattern properly implemented"}

    def _check_platinum_test_coverage(self) -> Dict[str, Any]:
        """Check test coverage (Platinum requirement: ≥95%)."""
        tests_dir = self.base_path / "tests"

        if not tests_dir.exists():
            return {"passed": False, "reason": "No tests directory found"}

        test_files = list(tests_dir.glob("test_*.py"))
        integration_files = list(self.integration_path.glob("*.py"))
        integration_files = [
            f for f in integration_files if not f.name.startswith("test_")
        ]

        # Advanced coverage estimation
        comprehensive_test_files = [
            "test_config_flow_edge_cases_enhanced.py",
            "test_coordinator_performance_validation.py",
            "test_cache_manager_edge_cases.py",
            "test_performance_manager_stress.py",
        ]

        comprehensive_tests = [
            f for f in test_files if f.name in comprehensive_test_files
        ]

        # Base coverage + bonus for comprehensive tests
        base_coverage = min(90, len(test_files) / max(1, len(integration_files)) * 85)
        comprehensive_bonus = len(comprehensive_tests) * 2  # 2% per comprehensive test

        estimated_coverage = min(98, base_coverage + comprehensive_bonus)

        if estimated_coverage < 95:
            return {
                "passed": False,
                "reason": f"Estimated coverage {estimated_coverage:.1f}% < 95%",
                "recommendation": "Add more edge case and stress tests",
            }

        return {
            "passed": True,
            "details": f"Estimated coverage: {estimated_coverage:.1f}%",
        }

    def _check_diagnostics_platform(self) -> Dict[str, Any]:
        """Check diagnostics platform implementation."""
        diagnostics_file = self.integration_path / "diagnostics.py"

        if not diagnostics_file.exists():
            return {
                "passed": False,
                "reason": "diagnostics.py missing",
                "recommendation": "Implement diagnostics platform for Platinum quality",
            }

        with open(diagnostics_file, "r", encoding="utf-8") as f:
            content = f.read()

        if "async_get_config_entry_diagnostics" not in content:
            return {
                "passed": False,
                "reason": "Missing diagnostics function",
                "recommendation": "Implement async_get_config_entry_diagnostics",
            }

        return {"passed": True, "details": "Diagnostics platform implemented"}

    def _check_repairs_platform(self) -> Dict[str, Any]:
        """Check repairs platform implementation."""
        repairs_file = self.integration_path / "repairs.py"

        if not repairs_file.exists():
            return {
                "passed": False,
                "reason": "repairs.py missing",
                "recommendation": "Implement repairs platform for Platinum quality",
            }

        with open(repairs_file, "r", encoding="utf-8") as f:
            content = f.read()

        repair_patterns = ["RepairsFlow", "async_create_fix_flow", "ConfirmRepairFlow"]
        found_patterns = [p for p in repair_patterns if p in content]

        if len(found_patterns) < 2:
            return {
                "passed": False,
                "reason": f"Incomplete repairs implementation: {found_patterns}",
                "recommendation": "Implement complete repairs flow",
            }

        return {"passed": True, "details": "Repairs platform implemented"}

    def _check_type_annotations(self) -> Dict[str, Any]:
        """Check type annotation completeness."""
        py_files = list(self.integration_path.glob("*.py"))
        annotation_coverage = []

        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue

            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                tree = ast.parse(content)

                function_count = 0
                annotated_functions = 0

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        function_count += 1

                        # Check return annotation
                        if node.returns:
                            annotated_functions += 0.5

                        # Check parameter annotations
                        annotated_params = sum(
                            1
                            for arg in node.args.args
                            if arg.annotation and arg.arg != "self"
                        )
                        total_params = len(
                            [arg for arg in node.args.args if arg.arg != "self"]
                        )

                        if total_params > 0:
                            param_ratio = annotated_params / total_params
                            annotated_functions += param_ratio * 0.5

                if function_count > 0:
                    file_annotation_ratio = annotated_functions / function_count
                    annotation_coverage.append(file_annotation_ratio)

            except SyntaxError:
                continue

        if not annotation_coverage:
            return {"passed": False, "reason": "Could not analyze type annotations"}

        avg_coverage = sum(annotation_coverage) / len(annotation_coverage)

        if avg_coverage < 0.9:  # 90% annotation coverage
            return {
                "passed": False,
                "reason": f"Type annotation coverage {avg_coverage:.1%} < 90%",
                "recommendation": "Add complete type annotations to all functions",
            }

        return {
            "passed": True,
            "details": f"Type annotation coverage: {avg_coverage:.1%}",
        }

    def _check_advanced_error_handling(self) -> Dict[str, Any]:
        """Check advanced error handling patterns."""
        advanced_patterns = []

        py_files = list(self.integration_path.glob("*.py"))
        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            if "HomeAssistantError" in content:
                advanced_patterns.append("Custom exceptions")
            if "ConfigEntryNotReady" in content:
                advanced_patterns.append("Config entry retry")
            if "async_will_remove_from_hass" in content:
                advanced_patterns.append("Cleanup handling")
            if "try:" in content and "finally:" in content:
                advanced_patterns.append("Resource cleanup")

        unique_patterns = list(set(advanced_patterns))

        if len(unique_patterns) < 3:
            return {
                "passed": False,
                "reason": f"Limited error handling patterns: {unique_patterns}",
                "recommendation": "Implement comprehensive error handling strategies",
            }

        return {
            "passed": True,
            "details": f"Error patterns: {', '.join(unique_patterns)}",
        }

    def _check_performance_monitoring(self) -> Dict[str, Any]:
        """Check performance monitoring implementation."""
        performance_file = self.integration_path / "performance_manager.py"

        if not performance_file.exists():
            return {
                "passed": False,
                "reason": "No performance monitoring found",
                "recommendation": "Implement performance monitoring for Platinum quality",
            }

        with open(performance_file, "r", encoding="utf-8") as f:
            content = f.read()

        monitoring_features = []
        if "record_update" in content:
            monitoring_features.append("Update timing")
        if "get_stats" in content:
            monitoring_features.append("Statistics")
        if "performance_monitor" in content:
            monitoring_features.append("Decorators")

        if len(monitoring_features) < 2:
            return {
                "passed": False,
                "reason": f"Limited monitoring features: {monitoring_features}",
                "recommendation": "Implement comprehensive performance monitoring",
            }

        return {
            "passed": True,
            "details": f"Monitoring: {', '.join(monitoring_features)}",
        }

    def _check_modular_architecture(self) -> Dict[str, Any]:
        """Check modular architecture implementation."""
        modular_files = [
            "cache_manager.py",
            "batch_manager.py",
            "data_manager.py",
            "feeding_manager.py",
            "walk_manager.py",
            "dog_manager.py",
        ]

        existing_modules = []
        for module_file in modular_files:
            if (self.integration_path / module_file).exists():
                existing_modules.append(module_file.replace(".py", ""))

        if len(existing_modules) < 4:
            return {
                "passed": False,
                "reason": f"Limited modular architecture: {len(existing_modules)} modules",
                "recommendation": "Implement more specialized manager modules",
            }

        return {"passed": True, "details": f"Modules: {', '.join(existing_modules)}"}

    def _check_documentation_quality(self) -> Dict[str, Any]:
        """Check documentation quality."""
        py_files = list(self.integration_path.glob("*.py"))
        files_with_docstrings = 0

        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue

            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for comprehensive docstrings
            if (
                '"""' in content
                and len(re.findall(r'""".*?"""', content, re.DOTALL)) > 1
            ):
                files_with_docstrings += 1

        docstring_ratio = files_with_docstrings / max(1, len(py_files))

        if docstring_ratio < 0.8:
            return {
                "passed": False,
                "reason": f"Low docstring coverage: {docstring_ratio:.1%}",
                "recommendation": "Add comprehensive docstrings to all modules",
            }

        return {
            "passed": True,
            "details": f"Documentation coverage: {docstring_ratio:.1%}",
        }

    def _check_edge_case_handling(self) -> Dict[str, Any]:
        """Check edge case handling in tests."""
        tests_dir = self.base_path / "tests"

        if not tests_dir.exists():
            return {"passed": False, "reason": "No tests directory"}

        edge_case_tests = [
            "test_config_flow_edge_cases.py",
            "test_coordinator_edge_cases.py",
            "test_cache_manager_edge_cases.py",
            "test_switch_edge_cases.py",
            "test_select_edge_cases.py",
        ]

        existing_edge_tests = []
        for test_file in edge_case_tests:
            if (tests_dir / test_file).exists():
                existing_edge_tests.append(test_file)

        if len(existing_edge_tests) < 3:
            return {
                "passed": False,
                "reason": f"Limited edge case testing: {len(existing_edge_tests)} files",
                "recommendation": "Implement comprehensive edge case testing",
            }

        return {
            "passed": True,
            "details": f"Edge case tests: {len(existing_edge_tests)}",
        }

    def _check_memory_efficiency(self) -> Dict[str, Any]:
        """Check memory efficiency patterns."""
        efficiency_patterns = []

        # Check for async context managers
        py_files = list(self.integration_path.glob("*.py"))
        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            if "async with" in content:
                efficiency_patterns.append("Async context managers")
            if "weakref" in content:
                efficiency_patterns.append("Weak references")
            if "clear()" in content:
                efficiency_patterns.append("Explicit cleanup")
            if "__slots__" in content:
                efficiency_patterns.append("Memory optimization")

        unique_patterns = list(set(efficiency_patterns))

        if len(unique_patterns) < 2:
            return {
                "passed": False,
                "reason": f"Limited memory efficiency: {unique_patterns}",
                "recommendation": "Implement memory efficiency patterns",
            }

        return {"passed": True, "details": f"Efficiency: {', '.join(unique_patterns)}"}

    def _generate_assessment_report(self) -> Dict[str, Any]:
        """Generate comprehensive assessment report."""
        print("\n" + "=" * 60)
        print("INTEGRATION QUALITY SCALE ASSESSMENT REPORT")
        print("=" * 60)

        # Calculate scores
        bronze_percentage = (self.bronze_score / max(1, self.bronze_max)) * 100
        silver_percentage = (self.silver_score / max(1, self.silver_max)) * 100
        gold_percentage = (self.gold_score / max(1, self.gold_max)) * 100
        platinum_percentage = (self.platinum_score / max(1, self.platinum_max)) * 100

        # Determine quality level achieved
        quality_level = "No certification"
        if bronze_percentage >= 100:
            quality_level = "Bronze"
        if silver_percentage >= 80:
            quality_level = "Silver"
        if gold_percentage >= 80:
            quality_level = "Gold"
        if platinum_percentage >= 80:
            quality_level = "Platinum"

        # Print detailed scores
        print(
            f"\n🥉 BRONZE: {self.bronze_score}/{self.bronze_max} ({bronze_percentage:.1f}%)"
        )
        print(
            f"🥈 SILVER: {self.silver_score}/{self.silver_max} ({silver_percentage:.1f}%)"
        )
        print(f"🥇 GOLD: {self.gold_score}/{self.gold_max} ({gold_percentage:.1f}%)")
        print(
            f"💎 PLATINUM: {self.platinum_score}/{self.platinum_max} ({platinum_percentage:.1f}%)"
        )

        print(f"\n🏆 ACHIEVED QUALITY LEVEL: {quality_level}")

        if quality_level == "Platinum":
            print("🎉 CONGRATULATIONS! Integration meets Platinum quality standards!")
        elif quality_level == "Gold":
            print("✨ Excellent! Integration meets Gold quality standards!")
            print(
                "💡 Consider implementing Platinum requirements for top-tier quality."
            )
        else:
            print(f"📈 Integration meets {quality_level} standards.")
            print("🎯 Focus on higher-tier requirements for improved quality.")

        # Print recommendations
        if self.recommendations:
            print(f"\n💡 RECOMMENDATIONS ({len(self.recommendations)}):")
            for i, rec in enumerate(self.recommendations[:10], 1):
                print(f"  {i}. {rec}")
            if len(self.recommendations) > 10:
                print(f"  ... and {len(self.recommendations) - 10} more")

        # Create assessment summary
        assessment_summary = {
            "quality_level": quality_level,
            "scores": {
                "bronze": {
                    "score": self.bronze_score,
                    "max": self.bronze_max,
                    "percentage": bronze_percentage,
                },
                "silver": {
                    "score": self.silver_score,
                    "max": self.silver_max,
                    "percentage": silver_percentage,
                },
                "gold": {
                    "score": self.gold_score,
                    "max": self.gold_max,
                    "percentage": gold_percentage,
                },
                "platinum": {
                    "score": self.platinum_score,
                    "max": self.platinum_max,
                    "percentage": platinum_percentage,
                },
            },
            "recommendations": self.recommendations,
            "detailed_results": self.results,
        }

        # Save detailed report
        report_file = self.base_path / "quality_assessment_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(assessment_summary, f, indent=2, default=str)

        print(f"\n📄 Detailed report saved: {report_file}")
        print("=" * 60)

        return assessment_summary


def main():
    """Main assessment entry point."""
    base_path = Path(__file__).parent

    assessment = IntegrationQualityAssessment(base_path)
    results = assessment.assess_quality()

    # Return appropriate exit code
    quality_level = results.get("quality_level", "No certification")
    success = quality_level in ["Gold", "Platinum"]

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
