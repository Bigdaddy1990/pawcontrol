# 🐾 Paw Control - Smart Dog Management for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-blue.svg)](https://github.com/BigDaddy1990/pawcontrol)
[![GitHub Release](https://img.shields.io/github/release/BigDaddy1990/pawcontrol.svg?style=for-the-badge)](https://github.com/BigDaddy1990/pawcontrol/releases)
[![Downloads](https://img.shields.io/github/downloads/BigDaddy1990/pawcontrol/total.svg?style=for-the-badge)](https://github.com/BigDaddy1990/pawcontrol/releases)

## 🎯 Features

Paw Control is a comprehensive Home Assistant integration for managing your dogs' daily activities, health, and well-being.

### Core Features

- 🚶 **Walk Tracking** - Automatic detection via door sensors/GPS, duration & distance tracking
- 🍽️ **Feeding Management** - Meal scheduling, portion control, overfeeding protection  
- 🏥 **Health Monitoring** - Weight tracking, medication reminders, vet appointments
- ✂️ **Grooming Schedule** - Track grooming sessions, set intervals
- 🎓 **Training Sessions** - Log training progress and topics
- 📍 **GPS Tracking** - Real-time location, geofencing, auto walk detection
- 🔔 **Smart Notifications** - Presence-based routing, quiet hours, actionable alerts
- 📊 **Reports & Statistics** - Daily/weekly summaries, health trends
- 🐕‍🦺 **Multi-Dog Support** - Manage unlimited dogs independently
- 👥 **Visitor Mode** - Special mode for dog-sitting scenarios

### Smart Automation

- Automatic walk detection via door sensors
- GPS-based walk start/end
- Presence-aware notifications
- Daily counter resets
- Scheduled reminders
- Activity-based calorie calculation

## 📦 Installation

### HACS Installation (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots menu and select "Custom repositories"
4. Add this repository URL: `https://github.com/yourusername/pawcontrol`
5. Select "Integration" as the category
6. Click "Add"
7. Search for "Paw Control" and install it
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Extract the `custom_components/pawcontrol` folder
3. Copy it to your Home Assistant's `config/custom_components/` directory
4. Restart Home Assistant

## ⚙️ Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **Paw Control**
4. Follow the configuration wizard:
   - Enter number of dogs
   - Configure each dog (name, breed, age, weight)
   - Select modules to enable
   - Configure data sources (optional)
   - Set up notifications
   - Configure system settings

### Configuration Options

#### Dog Configuration
- **Name**: Your dog's name
- **Breed**: Dog breed (optional)
- **Age**: Age in years
- **Weight**: Weight in kg
- **Size**: Small/Medium/Large/XLarge

#### Modules (per dog)
- Walk Tracking
- Feeding Management
- Health Tracking
- GPS Tracking
- Notifications
- Dashboard
- Grooming
- Medication
- Training

#### Data Sources (optional)
- **Door Sensor**: For automatic walk detection
- **Person Entities**: For presence-based notifications
- **Device Trackers**: For GPS tracking
- **Calendar**: For appointments and events
- **Weather**: For weather-aware features

## 📱 Dashboard

Paw Control provides ready-to-use dashboard cards compatible with Mushroom cards.

### Example Dashboard Configuration

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-template-card
    primary: "🐕 {{ states('sensor.pawcontrol_rex_last_walk') }}"
    secondary: Last Walk
    icon: mdi:dog-side
    
  - type: custom:mushroom-template-card
    primary: "{{ states('sensor.pawcontrol_rex_feeding_dinner') }} meals"
    secondary: Dinner Today
    icon: mdi:food
    
  - type: button
    entity: button.pawcontrol_rex_start_walk
    name: Start Walk
    icon: mdi:walk
```

## 🔧 Services

Paw Control provides extensive services for automation:

### Walk Management
- `pawcontrol.start_walk` - Start tracking a walk
- `pawcontrol.end_walk` - End walk tracking
- `pawcontrol.walk_dog` - Quick walk log

### Feeding
- `pawcontrol.feed_dog` - Record feeding

### Health
- `pawcontrol.log_health_data` - Log health information
- `pawcontrol.log_medication` - Record medication
- `pawcontrol.start_grooming_session` - Log grooming

### Activities
- `pawcontrol.play_with_dog` - Log play session
- `pawcontrol.start_training_session` - Log training

### System
- `pawcontrol.daily_reset` - Reset daily counters
- `pawcontrol.generate_report` - Generate activity report
- `pawcontrol.export_health_data` - Export health data

## 📊 Entities

Each dog gets a comprehensive set of entities:

### Sensors
- Last walk/feeding/grooming timestamps
- Walk duration & distance
- Feeding counters per meal
- Weight & weight trend
- Activity level & calories burned
- Days since grooming

### Binary Sensors
- Needs walk
- Is hungry
- Needs grooming
- Walk in progress
- Is home (GPS)

### Controls
- Number inputs for portions, intervals
- Select inputs for food type, grooming type
- Text inputs for notes
- Switches for module enable/disable

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## 📞 Support

- [Issue Tracker](https://github.com/BigDaddy1990/pawcontrol/issues)
- [Discussions](https://github.com/BigDadddy1990/pawcontrol/discussions)

---

<div align="center">

## 🐶 **Made with ❤️ for Dog Lovers using Home Assistant**

**Paw Control** - *Weil jeder Hund das Beste verdient hat!*

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

*🦴 Spenden Sie Hundekekse für die Entwicklung! 🦴*

---
