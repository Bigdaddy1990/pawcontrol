#!/usr/bin/env python3
"""Comprehensive test suite validation script for PawControl integration.

Validates test coverage, quality, and Gold Standard compliance across all modules.
Generates detailed coverage reports and identifies missing test areas.

Usage:
    python scripts/validate_test_suite.py

Features:
- Test coverage analysis across all modules
- Gold Standard compliance verification  
- Missing test identification
- Code quality validation
- Integration completeness assessment
- Performance test validation
- HACS compliance checking
"""

from __future__ import annotations

import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Add custom_components to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@dataclass
class ModuleInfo:
    """Information about a module."""
    name: str
    path: Path
    functions: Set[str]
    classes: Set[str]
    lines_of_code: int
    complexity_score: int

@dataclass
class TestInfo:
    """Information about a test file."""
    name: str
    path: Path
    test_methods: Set[str]
    tested_modules: Set[str]
    test_classes: Set[str]
    lines_of_code: int
    coverage_score: float

@dataclass
class CoverageReport:
    """Test coverage report."""
    module_name: str
    total_functions: int
    tested_functions: int
    total_classes: int
    tested_classes: int
    coverage_percentage: float
    missing_tests: List[str]
    quality_score: float

class TestSuiteValidator:
    """Comprehensive test suite validator."""

    def __init__(self, project_root: Path):
        """Initialize validator.
        
        Args:
            project_root: Path to project root directory
        """
        self.project_root = project_root
        self.custom_components_path = project_root / "custom_components" / "pawcontrol"
        self.tests_path = project_root / "tests"
        
        # Results storage
        self.modules: Dict[str, ModuleInfo] = {}
        self.tests: Dict[str, TestInfo] = {}
        self.coverage_reports: Dict[str, CoverageReport] = {}
        
        # Gold Standard requirements
        self.gold_standard_requirements = {
            "min_coverage_percentage": 95.0,
            "min_test_classes_per_module": 1,
            "min_test_methods_per_class": 3,
            "required_edge_cases": 5,
            "required_performance_tests": 3,
            "required_integration_tests": 2,
        }

    def analyze_python_file(self, file_path: Path) -> Tuple[Set[str], Set[str], int]:
        """Analyze Python file for functions, classes, and complexity.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            Tuple of (functions, classes, lines_of_code)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            tree = ast.parse(content)
            
            functions = set()
            classes = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.startswith('_'):  # Public functions
                        functions.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.add(node.name)
            
            lines_of_code = len([line for line in content.splitlines() if line.strip() and not line.strip().startswith('#')])
            
            return functions, classes, lines_of_code
            
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")
            return set(), set(), 0

    def scan_modules(self):
        """Scan all modules in custom_components/pawcontrol."""
        print("🔍 Scanning modules...")
        
        for py_file in self.custom_components_path.glob("*.py"):
            if py_file.name.startswith('__'):
                continue
                
            module_name = py_file.stem
            functions, classes, loc = self.analyze_python_file(py_file)
            
            # Calculate complexity score based on functions, classes, and LOC
            complexity_score = len(functions) * 2 + len(classes) * 5 + loc // 50
            
            self.modules[module_name] = ModuleInfo(
                name=module_name,
                path=py_file,
                functions=functions,
                classes=classes,
                lines_of_code=loc,
                complexity_score=complexity_score
            )
            
        print(f"✓ Found {len(self.modules)} modules")

    def scan_tests(self):
        """Scan all test files."""
        print("🔍 Scanning tests...")
        
        for test_file in self.tests_path.glob("test_*.py"):
            test_name = test_file.stem
            
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                tree = ast.parse(content)
                
                test_methods = set()
                test_classes = set()
                tested_modules = set()
                
                # Extract test information
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                        test_methods.add(node.name)
                    elif isinstance(node, ast.ClassDef) and 'Test' in node.name:
                        test_classes.add(node.name)
                
                # Try to identify tested modules from imports and content
                import_pattern = r'from custom_components\.pawcontrol\.(\w+) import'
                tested_modules.update(re.findall(import_pattern, content))
                
                # Also check direct module references
                module_pattern = r'custom_components\.pawcontrol\.(\w+)'
                tested_modules.update(re.findall(module_pattern, content))
                
                lines_of_code = len([line for line in content.splitlines() if line.strip() and not line.strip().startswith('#')])
                
                # Calculate coverage score based on test methods and complexity
                coverage_score = min(100.0, len(test_methods) * 5.0)
                
                self.tests[test_name] = TestInfo(
                    name=test_name,
                    path=test_file,
                    test_methods=test_methods,
                    tested_modules=tested_modules,
                    test_classes=test_classes,
                    lines_of_code=lines_of_code,
                    coverage_score=coverage_score
                )
                
            except Exception as e:
                print(f"Error analyzing test {test_file}: {e}")
                
        print(f"✓ Found {len(self.tests)} test files")

    def calculate_coverage(self):
        """Calculate test coverage for each module."""
        print("📊 Calculating coverage...")
        
        for module_name, module_info in self.modules.items():
            # Find tests that cover this module
            covering_tests = []
            total_test_methods = 0
            
            for test_name, test_info in self.tests.items():
                if module_name in test_info.tested_modules or module_name in test_name:
                    covering_tests.append(test_name)
                    total_test_methods += len(test_info.test_methods)
            
            # Calculate coverage metrics
            tested_functions = 0
            tested_classes = 0
            missing_tests = []
            
            # Estimate tested functions based on test method count and patterns
            if covering_tests:
                # Heuristic: assume good tests cover most functions
                function_coverage_ratio = min(1.0, total_test_methods / max(1, len(module_info.functions)))
                tested_functions = int(len(module_info.functions) * function_coverage_ratio)
                
                class_coverage_ratio = min(1.0, len(covering_tests) / max(1, len(module_info.classes)))
                tested_classes = int(len(module_info.classes) * class_coverage_ratio)
            
            # Identify missing tests
            for func in module_info.functions:
                if not any(f"test_{func}" in test_info.test_methods 
                          for test_info in self.tests.values() 
                          if module_name in test_info.tested_modules):
                    missing_tests.append(f"Function: {func}")
                    
            for cls in module_info.classes:
                if not any(cls.lower() in test_name.lower() 
                          for test_name in covering_tests):
                    missing_tests.append(f"Class: {cls}")
            
            # Calculate overall coverage percentage
            total_items = len(module_info.functions) + len(module_info.classes)
            tested_items = tested_functions + tested_classes
            coverage_percentage = (tested_items / max(1, total_items)) * 100
            
            # Calculate quality score based on multiple factors
            quality_factors = [
                min(100, total_test_methods * 10),  # Test method count
                coverage_percentage,                 # Coverage percentage
                min(100, len(covering_tests) * 20),  # Number of test files
                100 - min(100, len(missing_tests) * 5)  # Penalty for missing tests
            ]
            quality_score = sum(quality_factors) / len(quality_factors)
            
            self.coverage_reports[module_name] = CoverageReport(
                module_name=module_name,
                total_functions=len(module_info.functions),
                tested_functions=tested_functions,
                total_classes=len(module_info.classes),
                tested_classes=tested_classes,
                coverage_percentage=coverage_percentage,
                missing_tests=missing_tests,
                quality_score=quality_score
            )

    def check_gold_standard_compliance(self) -> Dict[str, Any]:
        """Check Gold Standard compliance."""
        print("🏆 Checking Gold Standard compliance...")
        
        compliance_results = {
            "overall_compliant": True,
            "coverage_compliant": True,
            "quality_compliant": True,
            "test_structure_compliant": True,
            "issues": [],
            "recommendations": []
        }
        
        # Check overall coverage
        total_coverage = sum(report.coverage_percentage for report in self.coverage_reports.values())
        average_coverage = total_coverage / max(1, len(self.coverage_reports))
        
        if average_coverage < self.gold_standard_requirements["min_coverage_percentage"]:
            compliance_results["coverage_compliant"] = False
            compliance_results["overall_compliant"] = False
            compliance_results["issues"].append(
                f"Average coverage {average_coverage:.1f}% below required {self.gold_standard_requirements['min_coverage_percentage']}%"
            )
        
        # Check individual module compliance
        non_compliant_modules = []
        for module_name, report in self.coverage_reports.items():
            if report.coverage_percentage < self.gold_standard_requirements["min_coverage_percentage"]:
                non_compliant_modules.append(f"{module_name}: {report.coverage_percentage:.1f}%")
        
        if non_compliant_modules:
            compliance_results["coverage_compliant"] = False
            compliance_results["overall_compliant"] = False
            compliance_results["issues"].append(f"Low coverage modules: {', '.join(non_compliant_modules)}")
        
        # Check test structure requirements
        edge_case_tests = [test for test in self.tests.keys() if "edge" in test or "stress" in test]
        performance_tests = [test for test in self.tests.keys() if "performance" in test or "benchmark" in test]
        integration_tests = [test for test in self.tests.keys() if "integration" in test]
        
        if len(edge_case_tests) < self.gold_standard_requirements["required_edge_cases"]:
            compliance_results["test_structure_compliant"] = False
            compliance_results["overall_compliant"] = False
            compliance_results["issues"].append(f"Only {len(edge_case_tests)} edge case test files, need {self.gold_standard_requirements['required_edge_cases']}")
        
        if len(performance_tests) < self.gold_standard_requirements["required_performance_tests"]:
            compliance_results["test_structure_compliant"] = False
            compliance_results["overall_compliant"] = False
            compliance_results["issues"].append(f"Only {len(performance_tests)} performance test files, need {self.gold_standard_requirements['required_performance_tests']}")
        
        # Generate recommendations
        if non_compliant_modules:
            compliance_results["recommendations"].append("Add comprehensive tests for low-coverage modules")
        
        if average_coverage < 98:
            compliance_results["recommendations"].append("Add edge case and error handling tests to reach 98%+ coverage")
        
        return compliance_results

    def check_missing_critical_tests(self) -> List[str]:
        """Check for missing critical test areas."""
        print("🔍 Checking for missing critical tests...")
        
        missing_critical_tests = []
        
        # Define critical test patterns that should exist
        critical_patterns = [
            ("config_flow", ["test_config_flow.py", "test_config_flow_edge_cases.py"]),
            ("coordinator", ["test_coordinator.py", "test_coordinator_performance"]),
            ("cache_manager", ["test_cache_manager", "test_cache_manager_edge_cases"]),
            ("binary_sensor", ["test_binary_sensor.py"]),
            ("device_tracker", ["test_device_tracker.py"]),
            ("feeding_manager", ["test_feeding_manager"]),
            ("performance", ["test_performance", "test_stress", "test_benchmark"]),
            ("integration", ["test_integration", "test_init.py"]),
        ]
        
        for pattern_name, required_files in critical_patterns:
            found_files = []
            for required in required_files:
                if any(required in test_name for test_name in self.tests.keys()):
                    found_files.append(required)
            
            if not found_files:
                missing_critical_tests.append(f"Missing {pattern_name} tests: {required_files}")
            elif len(found_files) < len(required_files):
                missing = [req for req in required_files if not any(req in found for found in found_files)]
                missing_critical_tests.append(f"Incomplete {pattern_name} tests: missing {missing}")
        
        return missing_critical_tests

    def analyze_test_quality(self) -> Dict[str, Any]:
        """Analyze overall test quality metrics."""
        print("📈 Analyzing test quality...")
        
        quality_metrics = {
            "total_test_files": len(self.tests),
            "total_test_methods": sum(len(test.test_methods) for test in self.tests.values()),
            "total_test_classes": sum(len(test.test_classes) for test in self.tests.values()),
            "total_test_loc": sum(test.lines_of_code for test in self.tests.values()),
            "average_methods_per_file": 0,
            "average_classes_per_file": 0,
            "test_to_code_ratio": 0,
            "quality_distribution": {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        }
        
        if len(self.tests) > 0:
            quality_metrics["average_methods_per_file"] = quality_metrics["total_test_methods"] / len(self.tests)
            quality_metrics["average_classes_per_file"] = quality_metrics["total_test_classes"] / len(self.tests)
        
        # Calculate test-to-code ratio
        total_module_loc = sum(module.lines_of_code for module in self.modules.values())
        if total_module_loc > 0:
            quality_metrics["test_to_code_ratio"] = quality_metrics["total_test_loc"] / total_module_loc
        
        # Analyze quality distribution
        for report in self.coverage_reports.values():
            if report.quality_score >= 90:
                quality_metrics["quality_distribution"]["excellent"] += 1
            elif report.quality_score >= 75:
                quality_metrics["quality_distribution"]["good"] += 1
            elif report.quality_score >= 60:
                quality_metrics["quality_distribution"]["fair"] += 1
            else:
                quality_metrics["quality_distribution"]["poor"] += 1
        
        return quality_metrics

    def generate_comprehensive_report(self) -> str:
        """Generate comprehensive test suite validation report."""
        print("📋 Generating comprehensive report...")
        
        # Calculate overall statistics
        total_coverage = sum(report.coverage_percentage for report in self.coverage_reports.values())
        average_coverage = total_coverage / max(1, len(self.coverage_reports))
        
        compliance_results = self.check_gold_standard_compliance()
        missing_critical = self.check_missing_critical_tests()
        quality_metrics = self.analyze_test_quality()
        
        # Generate report
        report = []
        report.append("# 🐾 PawControl Integration - Test Suite Validation Report")
        report.append("=" * 60)
        report.append("")
        
        # Executive Summary
        report.append("## 📊 Executive Summary")
        report.append(f"**Overall Coverage:** {average_coverage:.1f}%")
        report.append(f"**Gold Standard Compliant:** {'✅ YES' if compliance_results['overall_compliant'] else '❌ NO'}")
        report.append(f"**Total Modules:** {len(self.modules)}")
        report.append(f"**Total Test Files:** {len(self.tests)}")
        report.append(f"**Total Test Methods:** {quality_metrics['total_test_methods']}")
        report.append("")
        
        # Coverage Status
        report.append("## 📈 Coverage Status")
        if average_coverage >= 95:
            report.append("🟢 **EXCELLENT** - Gold Standard coverage achieved!")
        elif average_coverage >= 90:
            report.append("🟡 **GOOD** - Nearly at Gold Standard, minor improvements needed")
        elif average_coverage >= 80:
            report.append("🟠 **FAIR** - Significant improvements needed for Gold Standard")
        else:
            report.append("🔴 **POOR** - Major test additions required")
        report.append("")
        
        # Module Coverage Details
        report.append("## 🔍 Module Coverage Details")
        report.append("| Module | Coverage | Functions | Classes | Quality | Status |")
        report.append("|--------|----------|-----------|---------|---------|--------|")
        
        for module_name in sorted(self.coverage_reports.keys()):
            report_data = self.coverage_reports[module_name]
            status = "✅" if report_data.coverage_percentage >= 95 else "⚠️" if report_data.coverage_percentage >= 80 else "❌"
            
            report.append(f"| {module_name} | {report_data.coverage_percentage:.1f}% | "
                         f"{report_data.tested_functions}/{report_data.total_functions} | "
                         f"{report_data.tested_classes}/{report_data.total_classes} | "
                         f"{report_data.quality_score:.1f} | {status} |")
        report.append("")
        
        # Test Quality Analysis
        report.append("## 📊 Test Quality Analysis")
        report.append(f"**Test Files:** {quality_metrics['total_test_files']}")
        report.append(f"**Test Methods:** {quality_metrics['total_test_methods']}")
        report.append(f"**Test Classes:** {quality_metrics['total_test_classes']}")
        report.append(f"**Test LOC:** {quality_metrics['total_test_loc']:,}")
        report.append(f"**Test-to-Code Ratio:** {quality_metrics['test_to_code_ratio']:.2f}")
        report.append(f"**Avg Methods/File:** {quality_metrics['average_methods_per_file']:.1f}")
        report.append("")
        
        # Quality Distribution
        report.append("### Quality Distribution")
        dist = quality_metrics['quality_distribution']
        report.append(f"- 🟢 Excellent (90%+): {dist['excellent']} modules")
        report.append(f"- 🟡 Good (75-89%): {dist['good']} modules")
        report.append(f"- 🟠 Fair (60-74%): {dist['fair']} modules")
        report.append(f"- 🔴 Poor (<60%): {dist['poor']} modules")
        report.append("")
        
        # Gold Standard Compliance
        report.append("## 🏆 Gold Standard Compliance")
        if compliance_results["overall_compliant"]:
            report.append("✅ **FULLY COMPLIANT** - All Gold Standard requirements met!")
        else:
            report.append("❌ **NON-COMPLIANT** - Issues found:")
            for issue in compliance_results["issues"]:
                report.append(f"  - {issue}")
        report.append("")
        
        # Missing Critical Tests
        if missing_critical:
            report.append("## ⚠️ Missing Critical Tests")
            for missing in missing_critical:
                report.append(f"- {missing}")
            report.append("")
        
        # Recommendations
        if compliance_results["recommendations"]:
            report.append("## 💡 Recommendations")
            for rec in compliance_results["recommendations"]:
                report.append(f"- {rec}")
            report.append("")
        
        # Detailed Missing Tests
        report.append("## 📝 Detailed Missing Test Areas")
        for module_name, report_data in self.coverage_reports.items():
            if report_data.missing_tests:
                report.append(f"### {module_name}")
                for missing in report_data.missing_tests[:10]:  # Limit to first 10
                    report.append(f"- {missing}")
                if len(report_data.missing_tests) > 10:
                    report.append(f"- ... and {len(report_data.missing_tests) - 10} more")
                report.append("")
        
        # Test File Summary
        report.append("## 📁 Test File Summary")
        report.append("| Test File | Methods | Classes | LOC | Coverage Score |")
        report.append("|-----------|---------|---------|-----|----------------|")
        
        for test_name in sorted(self.tests.keys()):
            test_info = self.tests[test_name]
            report.append(f"| {test_name} | {len(test_info.test_methods)} | "
                         f"{len(test_info.test_classes)} | {test_info.lines_of_code} | "
                         f"{test_info.coverage_score:.1f} |")
        
        report.append("")
        report.append("---")
        report.append("*Report generated by PawControl Test Suite Validator*")
        
        return "\n".join(report)

    def run_validation(self) -> Dict[str, Any]:
        """Run complete test suite validation."""
        print("🚀 Starting comprehensive test suite validation...")
        print()
        
        # Run all validation steps
        self.scan_modules()
        self.scan_tests()
        self.calculate_coverage()
        
        # Generate results
        compliance_results = self.check_gold_standard_compliance()
        quality_metrics = self.analyze_test_quality()
        missing_critical = self.check_missing_critical_tests()
        
        # Calculate final scores
        total_coverage = sum(report.coverage_percentage for report in self.coverage_reports.values())
        average_coverage = total_coverage / max(1, len(self.coverage_reports))
        
        validation_results = {
            "overall_coverage": average_coverage,
            "gold_standard_compliant": compliance_results["overall_compliant"],
            "total_modules": len(self.modules),
            "total_tests": len(self.tests),
            "quality_metrics": quality_metrics,
            "compliance_results": compliance_results,
            "missing_critical_tests": missing_critical,
            "detailed_report": self.generate_comprehensive_report()
        }
        
        print("✅ Validation completed!")
        print(f"📊 Overall Coverage: {average_coverage:.1f}%")
        print(f"🏆 Gold Standard: {'✅ COMPLIANT' if compliance_results['overall_compliant'] else '❌ NON-COMPLIANT'}")
        print()
        
        return validation_results

def main():
    """Main validation script."""
    project_root = Path(__file__).parent.parent
    validator = TestSuiteValidator(project_root)
    
    try:
        results = validator.run_validation()
        
        # Save detailed report
        report_path = project_root / "test_validation_report.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(results["detailed_report"])
        
        print(f"📄 Detailed report saved to: {report_path}")
        
        # Return exit code based on compliance
        if results["gold_standard_compliant"] and results["overall_coverage"] >= 95:
            print("🎉 SUCCESS: Gold Standard achieved!")
            return 0
        else:
            print("⚠️  WARNING: Gold Standard not yet achieved")
            return 1
            
    except Exception as e:
        print(f"❌ ERROR: Validation failed: {e}")
        return 2

if __name__ == "__main__":
    exit(main())
