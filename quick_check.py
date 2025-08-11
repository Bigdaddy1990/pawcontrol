#!/usr/bin/env python3
"""Quick validation script to check if Paw Control is ready."""

import json
import os
import sys
from pathlib import Path

def quick_check():
    """Quick check if integration is ready."""
    base = Path("custom_components/pawcontrol")
    
    print("🔍 QUICK CHECK - PAW CONTROL")
    print("=" * 40)
    
    critical_files = {
        "__init__.py": "Main integration",
        "manifest.json": "Integration manifest",
        "config_flow.py": "UI configuration",
        "const.py": "Constants",
        "coordinator.py": "Data coordinator",
        "services.yaml": "Service definitions",
        "sensor.py": "Sensor platform",
        "binary_sensor.py": "Binary sensor platform",
    }
    
    missing = []
    for file, desc in critical_files.items():
        path = base / file
        if path.exists():
            print(f"✅ {file:<20} - {desc}")
        else:
            print(f"❌ {file:<20} - {desc}")
            missing.append(file)
    
    # Check manifest validity
    try:
        with open(base / "manifest.json") as f:
            manifest = json.load(f)
            print(f"\n📦 Integration: {manifest.get('name', 'Unknown')}")
            print(f"📌 Version: {manifest.get('version', 'Unknown')}")
            print(f"🔧 Domain: {manifest.get('domain', 'Unknown')}")
    except:
        print("\n⚠️  Manifest invalid or missing")
    
    # Summary
    print("\n" + "=" * 40)
    if not missing:
        print("✅ READY FOR INSTALLATION")
        print("\nNext steps:")
        print("1. Copy to: /config/custom_components/")
        print("2. Restart Home Assistant")
        print("3. Add integration via UI")
        return True
    else:
        print(f"❌ MISSING {len(missing)} CRITICAL FILES")
        print("Cannot install until fixed.")
        return False

if __name__ == "__main__":
    if not quick_check():
        sys.exit(1)
