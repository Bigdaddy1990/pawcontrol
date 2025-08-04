# Definition aller Setup-Bereiche zur Modularisierung
SETUP_SCHEMA = {
    "dogs": {
        "type": "list",
        "description": "🐶 Hundedaten",
        "options": {
            "allow_guest": True,
            "max_dogs": 5
        }
    },
    "feeding": {
        "type": "multi_select",
        "description": "🍽️ Fütterungsarten",
        "options": ["Frühstück", "Mittagessen", "Abendessen", "Leckerli"]
    },
    "gps_tracking": {
        "type": "bool",
        "description": "🛰️ GPS-Tracking & Gassi-Protokollierung"
    },
    "gassi_trigger": {
        "type": "sensor_select",
        "description": "🚪 Türsensor / Hundeklappe zur Gassi-Erkennung"
    },
    "push_targets": {
        "type": "notify_target",
        "description": "🔔 Push-Empfänger (automatisch oder manuell)"
    },
    "health_tracking": {
        "type": "multi_bool",
        "description": "🧠 Gesundheitsdaten je Hund aktivieren",
        "options": ["Gewicht", "Medikamente", "Impfungen"]
    },
    
    "dog_count": {
        "type": "number",
        "description": "🐶 Anzahl eigener Hunde",
        "min": 1,
        "max": 5,
        "default": 1
    },
    "guest_dogs": {
        "type": "bool",
        "description": "🐾 Besuchshunde berücksichtigen?"
    },
    "dashboard_mode": {
    "type": "select",
    "description": "📊 Dashboard aktivieren?",
    "options": ["deaktiviert", "cards", "vollständig"],
    "default": "cards"
}
    "dogs_health_config": {
        "type": "dict",
        "description": "🧠 Gesundheitsmodul pro Hund aktivieren?",
        "required": False
    }
    "gassi_trigger_config": {
        "type": "dict",
        "description": "🐾 Gassi-Trigger pro Hund (gps, türsensor, manuell)",
        "required": False
    }
    "notifications_config": {
        "type": "dict",
        "description": "🔔 Push-Benachrichtigungen konfigurieren",
        "required": False
    },,,,
        "default": "cards"
    }
}
