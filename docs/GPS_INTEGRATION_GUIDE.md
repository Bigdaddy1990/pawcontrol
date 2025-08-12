# 🛰️ GPS-Tracker Integration Guide - PawTracker

**PawTracker** unterstützt **alle gängigen GPS-Tracker** mit automatischer Spaziergang-Erkennung und Live-Route-Tracking!

<div align="center">

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

**🦴 Spenden Sie Hundekekse für neue GPS-Tracker Integrationen! 🦴**

</div>

---

## 🎯 **Schnellstart: Ein-Klick GPS-Setup**

### **⚡ Automatische GPS-Konfiguration**
```yaml
# Der einfachste Weg: Ein Service-Call für alles!
service: pawtracker.setup_automatic_gps
data:
  entity_id: sensor.buddy_status
  gps_source: "device_tracker"  # Smartphone/Tractive/etc.
  gps_entity: device_tracker.buddy_phone
  auto_start_walk: true
  safe_zone_radius: 100
  track_route: true
  enable_notifications: true
```

**🎉 Das war's! Automatisches GPS-Tracking läuft jetzt.**

---

## 📱 **GPS-Tracker nach Typ**

### **🥇 1. Smartphone (Empfohlen für Besitzer)**

**Warum Smartphone?**
- ✅ **Immer dabei** wenn Sie mit Ihrem Hund spazieren gehen
- ✅ **Höchste Genauigkeit** durch moderne GPS-Chips
- ✅ **Kostenlos** - keine zusätzliche Hardware
- ✅ **Einfachste Integration** über Home Assistant App

#### **Setup: Home Assistant Companion App**
```yaml
# 1. HA Companion App installieren und GPS aktivieren
# 2. Automatisches Setup:
service: pawtracker.setup_automatic_gps
data:
  entity_id: sensor.buddy_status
  gps_source: "device_tracker"
  gps_entity: device_tracker.owner_phone  # Ihr Handy
  auto_start_walk: true
  movement_threshold: 50  # Meter
  safe_zone_radius: 100   # Zuhause-Bereich
```

---

### **🎯 2. Tractive GPS-Collar**

**Native Home Assistant Integration verfügbar!**

#### **Setup mit Tractive Device Tracker:**
```yaml
# 1. Tractive Integration in HA installieren
# 2. PawTracker automatisch konfigurieren:
service: pawtracker.setup_automatic_gps
data:
  entity_id: sensor.buddy_status
  gps_source: "device_tracker"
  gps_entity: device_tracker.buddy_tractive
  auto_start_walk: true
  track_activity_zones: true  # Tractive-spezifisch
```

---

### **🔧 3. DIY GPS-Tracker (ESP32/Arduino)**

**Für Bastler und Tech-Enthusiasten!**

#### **ESP32 mit GPS-Modul - Code-Beispiel:**
```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <TinyGPS++.h>
#include <ArduinoJson.h>

TinyGPSPlus gps;

void sendGPSToPawTracker(double lat, double lon, int accuracy, int battery) {
  HTTPClient http;
  http.begin("http://homeassistant:8123/api/webhook/buddy_diy_tracker_token");
  http.addHeader("Content-Type", "application/json");
  
  // JSON-Payload erstellen
  StaticJsonDocument<200> doc;
  doc["latitude"] = lat;
  doc["longitude"] = lon;
  doc["accuracy"] = accuracy;
  doc["battery"] = battery;
  doc["source"] = "ESP32_GPS";
  
  String payload;
  serializeJson(doc, payload);
  
  int httpResponseCode = http.POST(payload);
  
  if (httpResponseCode == 200) {
    Serial.println("GPS-Update erfolgreich gesendet!");
  }
  
  http.end();
}
```

---

### **🌐 4. Universal GPS-Integration**

**Für JEDEN GPS-Tracker mit Internet-Zugang!**

#### **Webhook-Integration (Universal)**
```yaml
# 1. Universal-Webhook erstellen
service: pawtracker.create_universal_webhook
data:
  entity_id: sensor.buddy_status
  webhook_name: "universal_gps"
  accepted_formats: ["json", "xml", "url_params"]
  security_token: true

# 2. Webhook-URL für Ihren GPS-Tracker:
# http://homeassistant:8123/api/webhook/buddy_universal_abc123
```

**Unterstützte Datenformate:**
```bash
# JSON Format (empfohlen)
POST /api/webhook/buddy_universal_abc123
Content-Type: application/json
{
  "lat": 52.5200,
  "lon": 13.4050,
  "acc": 5,
  "bat": 85,
  "time": "2025-07-27T10:30:00Z"
}

# URL Parameter Format
GET /api/webhook/buddy_universal_abc123?lat=52.5200&lon=13.4050&acc=5&bat=85
```

---

## 🚨 **Notfall & Sicherheit**

### **🆘 Notfall-GPS-Ortung**
```yaml
# Ein-Klick Notfall-Ortung
service: pawtracker.emergency_locate
data:
  entity_id: sensor.buddy_status
  priority: "high"           # Sofortige GPS-Abfrage
  notify_contacts: true      # Benachrichtigungen senden
  create_map_link: true      # Google Maps Link erstellen
```

### **🛡️ Geofencing & Sicherheitszonen**
```yaml
# Primäre Sicherheitszone (Zuhause)
service: pawtracker.set_safe_zone
data:
  entity_id: sensor.buddy_status
  zone_type: "home"
  latitude: 52.5200
  longitude: 13.4050
  radius: 100              # Meter
  enable_alerts: true
  alert_delay: 120         # 2 Minuten außerhalb = Alert
```

---

## 🔧 **Troubleshooting GPS-Probleme**

### **🛠️ GPS-Diagnose-Tools**
```yaml
# Umfassende GPS-Diagnose
service: pawtracker.diagnose_gps_system
data:
  entity_id: sensor.buddy_status
  run_connectivity_test: true
  check_accuracy_history: true
  test_webhook_endpoints: true
  generate_report: true
```

### **❌ Häufige Probleme & Lösungen:**

#### **Problem: Keine GPS-Updates**
```yaml
# GPS-Verbindung testen
service: pawtracker.test_gps_connection
data:
  entity_id: sensor.buddy_status
  send_test_update: true
  test_webhook: true

# Lösungsschritte:
# 1. Webhook-URL und Token prüfen
# 2. Internetverbindung des GPS-Trackers
# 3. Home Assistant Webhook-Logs checken
# 4. GPS-Tracker Akku und Status
```

#### **Problem: Ungenau GPS-Daten**
```yaml
# GPS-Genauigkeit optimieren
service: pawtracker.optimize_gps_accuracy
data:
  entity_id: sensor.buddy_status
  filter_low_accuracy: true      # Updates <20m Genauigkeit ignorieren
  use_smoothing: true            # GPS-Glättung aktivieren
  enable_kalman_filter: true     # Erweiterte Positionsfilterung
```

#### **Problem: Spaziergang wird nicht erkannt**
```yaml
# Auto-Detection Debug
service: pawtracker.debug_walk_detection
data:
  entity_id: sensor.buddy_status
  log_movement_threshold: true
  log_zone_calculations: true
  test_movement_simulation: true

# Threshold anpassen:
service: pawtracker.configure_auto_detection
data:
  entity_id: sensor.buddy_status
  movement_threshold: 30      # Reduzieren für sensiblere Erkennung
  safe_zone_radius: 150       # Vergrößern wenn zu sensitiv
```

---

## 💡 **Profi-Tipps für optimales GPS-Tracking**

### **🎯 Optimale GPS-Einstellungen:**
```yaml
# Für beste Genauigkeit (höherer Akkuverbrauch)
service: pawtracker.set_gps_profile
data:
  entity_id: sensor.buddy_status
  profile: "high_accuracy"
  update_interval: 30         # 30 Sekunden
  accuracy_threshold: 5       # Nur sehr genaue Updates
  enable_movement_smoothing: true

# Für Akku-Schonung (geringere Genauigkeit)
service: pawtracker.set_gps_profile
data:
  entity_id: sensor.buddy_status
  profile: "battery_saver"
  update_interval: 300        # 5 Minuten
  accuracy_threshold: 20      # Weniger genaue Updates OK
  enable_smart_updates: true   # Weniger Updates wenn Zuhause
```

### **📱 Mobile Optimierung:**
```yaml
# Smartphone GPS-Tracking optimieren
service: pawtracker.optimize_mobile_gps
data:
  entity_id: sensor.buddy_status
  background_updates: true
  location_high_accuracy: true
  battery_optimization: "ignore"  # HA App von Akku-Optimierung ausschließen
  sync_health_data: true
```

### **🔄 Multi-Source GPS (Redundanz):**
```yaml
# Mehrere GPS-Quellen für bessere Zuverlässigkeit
service: pawtracker.setup_multi_source_gps
data:
  entity_id: sensor.buddy_status
  primary_source: device_tracker.owner_phone
  backup_source: device_tracker.buddy_tractive
  tertiary_source: webhook.buddy_diy_tracker
  use_best_accuracy: true
  fallback_on_signal_loss: true
```

---

<div align="center">

## 🎉 **GPS-Tracking ist jetzt kinderleicht!**

**PawTracker** macht GPS-Tracking für Hunde so einfach wie nie zuvor:

### **✅ Was Sie bekommen:**
- 🛰️ **Automatische Spaziergang-Erkennung** ohne manuelles Starten
- 📍 **Live-GPS-Tracking** mit Route, Distanz, Geschwindigkeit
- 🔔 **Intelligente Benachrichtigungen** bei Zonenverlassen/Ankommen
- 📊 **Detaillierte Statistiken** über alle Spaziergänge
- 🚨 **Notfall-Ortung** für kritische Situationen

### **🚀 Schnellstart:**
1. **GPS-Tracker wählen** (Smartphone, Tractive, DIY)
2. **Ein Service-Call** für automatisches Setup
3. **Fertig!** GPS-Tracking läuft vollautomatisch

### **💝 Unterstützung:**

Gefällt Ihnen PawTracker? Unterstützen Sie die Entwicklung neuer GPS-Features!

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

**🦴 Spenden Sie Hundekekse für:**
- 🛰️ Neue GPS-Tracker Integrationen
- 📱 Mobile App mit GPS-Sync
- 🤖 KI-basierte GPS-Empfehlungen
- 🌍 Weltweite GPS-Unterstützung

---

**Das ist echtes GPS-Tracking wie es sein soll - vollautomatisch, intelligent und zuverlässig! 🐶🛰️**

</div>