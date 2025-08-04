# 🐕 Paw Control - GPS-basierte Hundeintegration für Home Assistant

<div align="center">

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/BigDaddy1990/paw_control.svg)](https://github.com/BigDaddy1990/paw_control/releases)
[![Downloads](https://img.shields.io/github/downloads/BigDaddy1990/paw_control/total.svg)](https://github.com/BigDaddy1990/paw_control/releases)

**🛰️ Die smarteste GPS-Tracking Integration für Hundebesitzer**

Automatische Spaziergang-Erkennung • Live-GPS-Tracking • Intelligente Automatisierungen

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

</div>

---

## 🎯 **Was ist Paw Control?**

**Paw Control** ist die erste **GPS-basierte Home Assistant Integration**, die speziell für Hundebesitzer entwickelt wurde. Mit **automatischer Spaziergang-Erkennung**, **Live-Route-Tracking** und vielem mehr haben Sie die komplette Kontrolle über das Wohlbefinden Ihres Hundes.

### **🏆 GPS-Features:**
- 🛰️ **GPS-Tracking** mit automatischer Spaziergang-Erkennung
- 📏 **Live-Distanz & Geschwindigkeit** während Spaziergängen  
- 🎯 **Geofencing** mit Sicherheitszonen
- 📱 **Alle GPS-Tracker** unterstützt (Fressnapf, Tractive, Smartphone)
- 🤖 **Intelligente Automatisierungen** basierend auf GPS-Daten

---

## 🚀 **HACS Installation**

### **Schritt 1: Repository hinzufügen**
1. **HACS öffnen** in Home Assistant
2. **Integrationen** → **⋮** → **Benutzerdefinierte Repositories**
3. **Repository hinzufügen**:
   ```
   URL: https://github.com/BigDaddy1990/paw_control
   Kategorie: Integration
   ```

### **Schritt 2: Paw Control installieren**
1. **"Paw Control"** in HACS suchen
2. **"Installieren"** klicken
3. **Home Assistant neu starten**

### **Schritt 3: Integration konfigurieren**
1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**
2. **"Paw Control"** suchen und hinzufügen
3. **Setup-Assistent** folgen:
   ```yaml
   Hundename: Buddy
   GPS-Quelle: device_tracker.buddy_phone
   Auto-Tracking: Aktiviert
   Sicherheitszone: 100m
   ```

### **Schritt 4: GPS-Tracking aktivieren**
```yaml
# Automatisches Setup ausführen
service: paw_control.setup_automatic_gps
data:
  entity_id: sensor.buddy_status
  gps_source: "device_tracker.buddy_phone"
  auto_start_walk: true
  safe_zone_radius: 100
  track_route: true
```

**🎉 Fertig! GPS-Tracking läuft automatisch.**

---

## 📱 **Unterstützte GPS-Tracker**

### **🎯 Tractive GPS-Collar**
```yaml
# Native Home Assistant Integration
service: paw_control.setup_automatic_gps
data:
  gps_source: "device_tracker"
  gps_entity: device_tracker.buddy_tractive
```

### **📱 Smartphone (Empfohlen)**
```yaml
# Home Assistant Companion App
service: paw_control.setup_automatic_gps
data:
  gps_source: "device_tracker"
  gps_entity: device_tracker.owner_phone
```

### **🔧 DIY & Universal**
- **Webhooks**: Für jeden GPS-Tracker mit Internet
- **MQTT**: Für IoT-basierte GPS-Geräte
- **REST APIs**: Für kommerzielle GPS-Services
- **ESP32/Arduino**: Für selbstgebaute GPS-Tracker

---

## 🤖 **Beispiel-Automatisierungen**

### **🚶 Automatische Spaziergang-Benachrichtigungen**
```yaml
# Spaziergang gestartet
automation:
  - alias: "GPS: Spaziergang gestartet"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_on_walk
        to: 'on'
    action:
      - service: notify.mobile_app
        data:
          title: "🚶 Spaziergang gestartet!"
          message: "Buddy ist spazieren gegangen - GPS-Tracking aktiv"
```

### **🚨 Sicherheits-Automatisierungen**
```yaml
# Hund verlässt Sicherheitszone
automation:
  - alias: "GPS: Sicherheitszone verlassen"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_in_safe_zone
        to: 'off'
        for: "00:02:00"  # 2 Minuten außerhalb
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Buddy außerhalb Sicherheitszone!"
          message: "GPS-Tracker zeigt Position außerhalb des sicheren Bereichs"
```

---

## 💝 **Unterstützung**

### **🦴 Spenden Sie Hundekekse! 🦴**

paw_control ist kostenlos und Open Source. Unterstützen Sie die Entwicklung:

<div align="center">

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

**🏠 Spenden Sie eine Hundehütte oder Hundekekse! 🍪**

</div>

### **🌟 Andere Unterstützung**
- ⭐ **GitHub-Stern geben** - Zeigen Sie anderen, dass paw_control großartig ist
- 📢 **Weiterempfehlen** - Erzählen Sie anderen Hundebesitzern davon
- 🐛 **Bugs melden** - Helfen Sie bei der Verbesserung
- 💡 **Features vorschlagen** - Ihre GPS-Ideen sind willkommen!

---

## 📞 **Support & Community**

### **🆘 Hilfe benötigt?**
- 🐛 **[Bug Reports](https://github.com/BigDaddy1990/paw_control/issues)** - Probleme melden
- 💬 **[GitHub Discussions](https://github.com/BigDaddy1990/paw_control/discussions)** - Community-Support
- 📖 **[Dokumentation](https://github.com/BigDaddy1990/paw_control/wiki)** - Ausführliche Anleitungen
- 📧 **support@paw_control.de** - Direkter Support

---

<div align="center">

## 🐶 **Ready to Track Your Dog's Adventures?**

**Paw Control** - *DOG-Tracking made simple for dog lovers!*

### **🚀 Jetzt installieren:**

1. **HACS** → **Custom Repository** → `github.com/BigDaddy1990/paw_control`
2. **"Paw Control"** installieren
3. **GPS-Tracker** verbinden  
4. **Automatisches Tracking** genießen! 🎉

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

*🦴 Spenden Sie Hundekekse für die Entwicklung! 🦴*

---

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/BigDaddy1990/paw_control.svg?style=for-the-badge)](https://github.com/BigDaddy1990/paw_control/releases)
[![License](https://img.shields.io/github/license/BigDaddy1990/paw_control.svg?style=for-the-badge)](LICENSE)

**⭐ Geben Sie uns einen Stern, wenn Sie Paw Control lieben! ⭐**

</div>
