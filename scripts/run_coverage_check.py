#!/usr/bin/env python3
"""Quick test runner for coverage validation."""

import sys
from pathlib import Path

# Add current path to sys.path for imports
current_path = Path(__file__).parent
sys.path.insert(0, str(current_path))

try:
    from test_coverage_validation import TestCoverageValidator
    
    base_path = Path(__file__).parent
    validator = TestCoverageValidator(base_path)
    
    print("Starting test coverage validation...")
    success = validator.validate_coverage()
    
    if success:
        print("\n✅ SUCCESS: Test coverage validation passed")
    else:
        print("\n❌ FAILED: Test coverage validation failed")
        
except Exception as e:
    print(f"Error running validation: {e}")
    import traceback
    traceback.print_exc()
