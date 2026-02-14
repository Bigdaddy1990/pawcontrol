#!/bin/bash
# PawControl v1.0.1 Deployment Checklist
# Date: 2026-02-14
# Bug Fix Release - Critical cache memory leak fix

set -e  # Exit on error

echo "=================================================="
echo "PawControl v1.0.1 Deployment Checklist"
echo "=================================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track status
CHECKS_PASSED=0
CHECKS_FAILED=0

check_step() {
    local description=$1
    local command=$2
    
    echo -n "▶ $description... "
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((CHECKS_FAILED++))
        return 1
    fi
}

manual_check() {
    local description=$1
    echo -e "${YELLOW}⚠ MANUAL:${NC} $description"
}

echo "1. PRE-DEPLOYMENT VERIFICATION"
echo "────────────────────────────────────────────────"
echo ""

# Check Python version
check_step "Python 3.13+ available" "python3 --version | grep -qE 'Python 3\.(1[3-9]|[2-9][0-9])'"

# Check if in correct directory
check_step "In project root directory" "test -f custom_components/pawcontrol/manifest.json"

# Check version updated
check_step "manifest.json version is 1.0.1" "grep -q '\"version\": \"1.0.1\"' custom_components/pawcontrol/manifest.json"

echo ""
echo "2. CODE QUALITY CHECKS"
echo "────────────────────────────────────────────────"
echo ""

# Ruff checks
if command -v ruff &> /dev/null; then
    check_step "Ruff format check" "ruff format --check custom_components/pawcontrol"
    check_step "Ruff lint check" "ruff check custom_components/pawcontrol"
else
    manual_check "Install ruff: pip install ruff"
fi

# MyPy checks
if command -v mypy &> /dev/null; then
    check_step "MyPy strict type checking" "mypy --strict custom_components/pawcontrol"
else
    manual_check "Install mypy: pip install mypy"
fi

echo ""
echo "3. TEST SUITE"
echo "────────────────────────────────────────────────"
echo ""

# Pytest
if command -v pytest &> /dev/null; then
    check_step "Unit tests pass" "pytest tests/unit -q"
    check_step "Integration tests pass" "pytest tests/components/pawcontrol -q"
    check_step "Coverage ≥ 95%" "pytest --cov=custom_components/pawcontrol --cov-report=term | grep -q 'TOTAL.*9[5-9]%\|TOTAL.*100%'"
else
    manual_check "Install pytest: pip install pytest pytest-cov"
fi

echo ""
echo "4. HOME ASSISTANT VALIDATION"
echo "────────────────────────────────────────────────"
echo ""

# Hassfest validation
check_step "hassfest validation" "python -m scripts.hassfest --integration-path custom_components/pawcontrol"

# Manifest validation
check_step "Manifest structure valid" "python -m scripts.validate_manifest custom_components/pawcontrol"

echo ""
echo "5. BUG FIX VERIFICATION"
echo "────────────────────────────────────────────────"
echo ""

# Run custom verification script
if [ -f "scripts/verify_fixes.py" ]; then
    check_step "Bug fixes verified" "python scripts/verify_fixes.py"
else
    manual_check "Run: python scripts/verify_fixes.py"
fi

echo ""
echo "6. DOCUMENTATION"
echo "────────────────────────────────────────────────"
echo ""

check_step "Bug fix report exists" "test -f docs/BUG_FIX_REPORT_2026-02-14.md"
manual_check "Update CHANGELOG.md with v1.0.1 entry"
manual_check "Update README.md version references (if any)"

echo ""
echo "7. GIT OPERATIONS"
echo "────────────────────────────────────────────────"
echo ""

manual_check "Stage changes: git add custom_components/pawcontrol/__init__.py"
manual_check "Stage changes: git add custom_components/pawcontrol/const.py"
manual_check "Stage changes: git add custom_components/pawcontrol/manifest.json"
manual_check "Stage changes: git add docs/BUG_FIX_REPORT_2026-02-14.md"
manual_check "Stage changes: git add CHANGELOG.md"
manual_check "Stage changes: git add scripts/verify_fixes.py"

echo ""
echo "Commit message template:"
echo "────────────────────────────────────────────────"
cat << 'EOF'
Fix: Critical cache memory leak + type safety improvements (v1.0.1)

CRITICAL FIXES:
- Fix platform cache growing beyond max_size (100 entries)
  Prevents unbounded memory growth in long-running instances
  Location: __init__.py:378

- Fix duplicate pyright ignore comment in async_setup_entry
  Improves code quality and type checking clarity
  Location: __init__.py:448

- Fix missing type annotation on DOG_ID_PATTERN constant
  Ensures MyPy strict compliance
  Location: const.py:101

CHANGES:
- Enhanced platform cache with size enforcement before insertion
- Removed redundant type checker suppressions
- Strengthened type safety throughout constants module

DOCUMENTATION:
- Added comprehensive bug fix report
- Created verification script for automated testing

Closes #[issue_number]
EOF

echo ""
echo "────────────────────────────────────────────────"
manual_check "Review commit message and adjust as needed"
manual_check "Commit: git commit -m '...'"
manual_check "Tag release: git tag -a v1.0.1 -m 'Bug fix release'"
manual_check "Push: git push origin main --tags"

echo ""
echo "8. POST-DEPLOYMENT"
echo "────────────────────────────────────────────────"
echo ""

manual_check "Update GitHub release notes"
manual_check "Monitor cache size in diagnostics (should stay ≤ 100)"
manual_check "Monitor memory usage over 24h"
manual_check "Verify no performance regressions"

echo ""
echo "=================================================="
echo "DEPLOYMENT CHECKLIST SUMMARY"
echo "=================================================="
echo -e "${GREEN}Passed:${NC} $CHECKS_PASSED checks"
echo -e "${RED}Failed:${NC} $CHECKS_FAILED checks"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL AUTOMATED CHECKS PASSED${NC}"
    echo ""
    echo "Ready for deployment! Complete the manual steps above."
    exit 0
else
    echo -e "${RED}✗ SOME CHECKS FAILED${NC}"
    echo ""
    echo "Please fix the failed checks before deploying."
    exit 1
fi
