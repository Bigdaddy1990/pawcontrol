# 🤝 Contributing to Paw Control

Vielen Dank für Ihr Interesse, zu **Paw Control** beizutragen! Diese Anleitung hilft Ihnen dabei, erfolgreich zu diesem Projekt beizutragen.

---

## 🎯 **Warum zu Paw Control beitragen?**

Paw Control ist **die erste umfassende GPS-basierte Hundeintegration** für Home Assistant. Ihre Beiträge helfen Tausenden von Hundebesitzern dabei, ihre vierbeinigen Freunde besser zu verstehen und zu versorgen.

### **🐕 Ihr Impact:**
- **🛰️ GPS-Technologie** für Hunde zugänglicher machen
- **📱 Smart-Home Features** für Tierbesitzer entwickeln
- **🌍 Globale Community** von Hundeliebhabern unterstützen
- **🏥 Tiergesundheit** durch Technologie verbessern

---

## 🚀 **Erste Schritte**

### **Development Environment einrichten**

1. **Repository forken und klonen**
```bash
git clone https://github.com/yourusername/paw_control.git
cd paw_control
```

2. **Development Environment einrichten**
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\Scripts\activate     # Windows

pip install -r requirements_dev.txt
```

3. **Pre-commit Hooks installieren**
```bash
pre-commit install
```

---

## 🛠️ **Development Workflow**

### **Branch-Strategie**
```
main                    # Stabile Releases (v1.0.0, v1.1.0, ...)
├── develop             # Development Branch
├── feature/gps-xyz     # GPS-Features
├── feature/mobile-app  # Mobile Features  
├── feature/health-ai   # Gesundheits-KI
├── bugfix/gps-timeout  # GPS-Bugfixes
└── docs/gps-guide      # Dokumentations-Updates
```

### **Code Standards**

#### **🐍 Python Code-Qualität**
```python
# Beispiel für guten paw_control Code
async def update_gps_position(
    hass: HomeAssistant,
    entity_id: str,
    latitude: float,
    longitude: float,
    accuracy: Optional[float] = None,
    source: str = "unknown"
) -> bool:
    """Update GPS position and trigger walk analysis.
    
    Args:
        hass: Home Assistant instance
        entity_id: Target entity ID
        latitude: GPS latitude coordinate
        longitude: GPS longitude coordinate
        accuracy: GPS accuracy in meters
        source: GPS data source identifier
        
    Returns:
        bool: True if update successful
        
    Raises:
        ServiceNotFound: If GPS service not available
        InvalidCoordinates: If coordinates out of range
    """
    # Input validation
    if not (-90 <= latitude <= 90):
        raise InvalidCoordinates(f"Invalid latitude: {latitude}")
    
    # Service call mit error handling
    try:
        await hass.services.async_call(
            DOMAIN,
            "update_gps_simple",
            {
                "entity_id": entity_id,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
                "source_info": source,
            }
        )
        return True
    except ServiceNotFound:
        _LOGGER.error("GPS service not available")
        return False
```

---

## 🎯 **Contribution-Bereiche**

### **🛰️ GPS & Tracking (High Priority)**

Wir suchen besonders Beiträge in diesen Bereichen:

#### **GPS-Tracker Integrationen**
```python
# Beispiel: Neue GPS-Tracker Integration
class FressnapfGPSTracker:
    """Integration für Fressnapf GPS-Tracker."""
    
    async def setup_webhook(self, hass: HomeAssistant) -> str:
        """Setup webhook für Fressnapf GPS updates."""
        # Implementation für Fressnapf-spezifische API
        pass
    
    async def process_gps_data(self, webhook_data: dict) -> GPSPosition:
        """Verarbeite GPS-Daten von Fressnapf."""
        # Fressnapf-spezifische Datenverarbeitung
        pass
```

#### **Mobile Optimierungen**
- **Responsive GPS-Karten** für Mobile Dashboards
- **Offline GPS-Caching** für schlechte Internetverbindung
- **Battery-optimierte GPS-Updates** für Smartphones
- **Touch-optimierte GPS-Controls**

---

## 🔄 **Pull Request Process**

### **1. Vorbereitung**
```bash
# Feature Branch erstellen
git checkout develop
git pull origin develop
git checkout -b feature/amazing-gps-feature

# Änderungen implementieren
# Tests hinzufügen
# Dokumentation aktualisieren
```

### **2. Code Quality Checks**
```bash
# Code formatieren
black custom_components/pawcontrol/
isort custom_components/pawcontrol/

# Linting
pylint custom_components/pawcontrol/
flake8 custom_components/pawcontrol/

# Type checking
mypy custom_components/pawcontrol/

# Tests ausführen
pytest tests/ -v --cov=custom_components/pawcontrol
```

---

## 💝 **Unterstützung für neue GPS-Features:**

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

**🦴 Spenden Sie Hundekekse für:**
- 🛰️ Neue GPS-Tracker Integrationen
- 📱 Mobile App Entwicklung  
- 🤖 KI-basierte GPS-Empfehlungen
- 🌍 Weltweite GPS-Unterstützung

---

## 📄 **Lizenz**

Durch Beiträge zu diesem Projekt stimmen Sie zu, dass Ihre Beiträge unter der **MIT-Lizenz** lizenziert werden.

---

<div align="center">

## 🐶 **Happy Coding for Happy Dogs!**

**Paw Control** - *Code with ❤️ for our four-legged friends*

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

*🦴 Spenden Sie Hundekekse für die Entwicklung! 🦴*

---

**⭐ Geben Sie uns einen Stern, wenn Sie Paw Control entwickeln möchten! ⭐**

</div>
