"""Example: How to update entity platforms to use serialization utils.

This document shows how to integrate the new serialize utilities
into existing entity platforms for JSON-safe state attributes.
"""

from datetime import datetime, timedelta
from typing import Any


# ❌ VORHER (Nicht JSON-serializable):
class OldSensorExample:
    """Old implementation without serialization."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity state attributes (BROKEN!)."""
        return {
            "last_update": datetime.now(),  # ❌ Not JSON-serializable!
            "duration": timedelta(minutes=30),  # ❌ Not JSON-serializable!
            "session_data": self._session,  # ❌ Dataclass not serializable!
        }


# ✅ NACHHER (JSON-serializable):
from custom_components.pawcontrol.utils.serialize import serialize_entity_attributes


class NewSensorExample:
    """New implementation with serialization."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity state attributes (FIXED!)."""
        raw_attrs = {
            "last_update": self._last_update,  # datetime
            "duration": self._duration,  # timedelta
            "session_data": self._session,  # dataclass
        }
        # ✅ Automatically converts to JSON-safe format
        return serialize_entity_attributes(raw_attrs)


# 📋 MIGRATION CHECKLIST für Entity Platforms:
#
# 1. Import serialize_entity_attributes:
#    from custom_components.pawcontrol.utils.serialize import serialize_entity_attributes  # noqa: E501
#
# 2. Update extra_state_attributes property:
#    - Sammle raw attributes in dict
#    - Return serialize_entity_attributes(raw_attrs)
#
# 3. Test in Home Assistant:
#    - Check Developer Tools > States
#    - Verify all attributes appear correctly
#    - Check diagnostics download works
#
# 4. Update existing entities:
#    ✓ sensor.py (PawControlSensor)
#    ✓ binary_sensor.py (All binary sensors)
#    ✓ device_tracker.py (GPS tracker)
#    ✓ switch.py, button.py, select.py, number.py, date.py, datetime.py, text.py


# 🎯 EXAMPLE: Walk Sensor Update

# ❌ OLD VERSION (sensor.py - Line ~150):
"""
class PawControlWalkDurationSensor(CoordinatorEntity):
    @property
    def extra_state_attributes(self):
        return {
            "started_at": self._walk_start,  # datetime - BROKEN!
            "duration_minutes": self._duration.total_seconds() / 60,  # Manual conversion
            "last_seen": self._last_seen,  # datetime - BROKEN!
        }
"""  # noqa: E501

# ✅ NEW VERSION (sensor.py - Updated):
"""
from ..utils.serialize import serialize_entity_attributes

class PawControlWalkDurationSensor(CoordinatorEntity):
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw_attrs = {
            "started_at": self._walk_start,  # datetime - auto-converted!
            "duration": self._duration,  # timedelta - auto-converted to seconds!
            "last_seen": self._last_seen,  # datetime - auto-converted!
        }
        return serialize_entity_attributes(raw_attrs)
"""


# 🔥 BENEFITS:

# 1. No more manual datetime.isoformat() calls
# 2. No more manual timedelta.total_seconds() calculations
# 3. Automatic recursive serialization of nested dicts
# 4. Consistent serialization across all entities
# 5. Diagnostics export always works
# 6. Frontend always receives valid JSON


# ⚠️ IMPORTANT NOTES:

# - Always use serialize_entity_attributes() as the last step
# - Don't serialize values before passing to serialize_entity_attributes()
# - The function handles None values automatically
# - Nested dicts and lists are processed recursively
# - Dataclasses are automatically converted to dicts


# 📝 TODO: Update these files:

TODO_FILES = [
    "custom_components/pawcontrol/sensor.py",
    "custom_components/pawcontrol/binary_sensor.py",
    "custom_components/pawcontrol/device_tracker.py",
    "custom_components/pawcontrol/switch.py",
    "custom_components/pawcontrol/button.py",
    "custom_components/pawcontrol/select.py",
    "custom_components/pawcontrol/number.py",
    "custom_components/pawcontrol/date.py",
    "custom_components/pawcontrol/datetime.py",
    "custom_components/pawcontrol/text.py",
]

# Estimated effort: ~30 minutes (5 min per file)
# Priority: MEDIUM (improves diagnostics reliability)
