#!/usr/bin/env python3
"""Complete system check for Paw Control integration."""

import json
import os
import sys
from pathlib import Path

def check_integration():
    """Complete integration check with detailed analysis."""
    base = Path("custom_components/pawcontrol")
    errors = []
    warnings = []
    
    print("=" * 60)
    print("PAW CONTROL - VOLLSTÄNDIGE SYSTEMPRÜFUNG")
    print("=" * 60)
    
    # 1. Check critical files
    print("\n1️⃣ KRITISCHE DATEIEN:")
    critical = {
        "__init__.py": False,
        "manifest.json": False,
        "config_flow.py": False,
        "const.py": False,
        "coordinator.py": False,
        "services.yaml": False,
        "strings.json": False,
        "sensor.py": False,
        "binary_sensor.py": False,
        "button.py": False,
        "number.py": False,
        "select.py": False,
        "text.py": False,
        "switch.py": False,
    }
    
    for file in critical:
        path = base / file
        if path.exists():
            critical[file] = True
            print(f"  ✅ {file}")
        else:
            errors.append(f"Missing: {file}")
            print(f"  ❌ {file}")
    
    # 2. Check helpers
    print("\n2️⃣ HELPER MODULE:")
    helpers = ["__init__.py", "setup_sync.py", "notification_router.py", "scheduler.py", "gps_logic.py"]
    for helper in helpers:
        path = base / "helpers" / helper
        if path.exists():
            print(f"  ✅ helpers/{helper}")
        else:
            errors.append(f"Missing helper: {helper}")
            print(f"  ❌ helpers/{helper}")
    
    # 3. Check manifest validity
    print("\n3️⃣ MANIFEST VALIDIERUNG:")
    try:
        with open(base / "manifest.json") as f:
            manifest = json.load(f)
        
        required = ["domain", "name", "version", "config_flow", "iot_class", "requirements", "dependencies", "codeowners"]
        for field in required:
            if field in manifest:
                print(f"  ✅ {field}: {manifest.get(field)}")
            else:
                errors.append(f"Manifest missing: {field}")
                print(f"  ❌ Missing: {field}")
                
    except Exception as e:
        errors.append(f"Manifest error: {e}")
        print(f"  ❌ Error: {e}")
    
    # 4. Check coordinator methods
    print("\n4️⃣ COORDINATOR METHODEN:")
    coord_path = base / "coordinator.py"
    if coord_path.exists():
        with open(coord_path) as f:
            content = f.read()
        
        required_methods = [
            "reset_daily_counters",
            "start_walk",
            "end_walk",
            "log_walk",
            "feed_dog",
            "log_health_data",
            "log_medication",
            "start_grooming",
            "log_play_session",
            "log_training",
            "set_visitor_mode",
            "activate_emergency_mode",
        ]
        
        for method in required_methods:
            if f"async def {method}" in content:
                print(f"  ✅ {method}()")
            else:
                errors.append(f"Missing method: {method}")
                print(f"  ❌ {method}()")
    
    # 5. Check services.yaml
    print("\n5️⃣ SERVICES:")
    services_path = base / "services.yaml"
    if services_path.exists():
        try:
            with open(services_path) as f:
                services = yaml.safe_load(f)
            
            expected = [
                "daily_reset", "start_walk", "end_walk", "feed_dog",
                "log_medication", "generate_report"
            ]
            
            for service in expected[:3]:  # Show first 3
                if service in services:
                    print(f"  ✅ {service}")
                else:
                    warnings.append(f"Missing service: {service}")
                    print(f"  ⚠️ {service}")
            
            total = len(services.keys()) if services else 0
            print(f"  📊 Total: {total} services defined")
            
        except Exception as e:
            errors.append(f"Services error: {e}")
    
    # 6. Check imports
    print("\n6️⃣ IMPORT-PRÜFUNG:")
    init_path = base / "__init__.py"
    if init_path.exists():
        with open(init_path) as f:
            content = f.read()
        
        imports = [
            ("from .coordinator import", "PawControlCoordinator"),
            ("from .report_generator import", "ReportGenerator"),
            ("from .helpers.setup_sync import", "SetupSync"),
            ("from .helpers.notification_router import", "NotificationRouter"),
        ]
        
        for imp, cls in imports:
            if imp in content and cls in content:
                print(f"  ✅ {cls}")
            else:
                errors.append(f"Import issue: {cls}")
                print(f"  ❌ {cls}")
    
    # 7. Final summary
    print("\n" + "=" * 60)
    print("📊 ZUSAMMENFASSUNG:")
    print("=" * 60)
    
    total_files = sum(1 for v in critical.values() if v)
    print(f"✅ Dateien vorhanden: {total_files}/{len(critical)}")
    print(f"⚠️  Warnungen: {len(warnings)}")
    print(f"❌ Fehler: {len(errors)}")
    
    if errors:
        print("\n❌ KRITISCHE FEHLER:")
        for error in errors[:5]:  # Show first 5
            print(f"  • {error}")
        if len(errors) > 5:
            print(f"  ... und {len(errors) - 5} weitere")
        print("\n⚠️  INSTALLATION NICHT EMPFOHLEN")
        return False
    else:
        print("\n✅ INTEGRATION IST BEREIT!")
        print("\n🚀 INSTALLATION:")
        print("  1. Kopieren: cp -r custom_components/pawcontrol /config/custom_components/")
        print("  2. Home Assistant neu starten")
        print("  3. Integration hinzufügen via UI")
        return True

if __name__ == "__main__":
    if not check_integration():
        sys.exit(1)
