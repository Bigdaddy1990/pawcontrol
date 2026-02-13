# Getting Started with PawControl

Welcome to PawControl - your complete pet management solution for Home Assistant!

## What is PawControl?

PawControl is a Home Assistant integration that helps you monitor and manage your pets' activities, health, and location. Track walks, feeding schedules, GPS location, and health metrics all from your Home Assistant dashboard.

## Features at a Glance

✅ **GPS Tracking** - Real-time location monitoring with geofencing  
✅ **Walk Management** - Automatic walk detection and tracking  
✅ **Feeding Schedules** - Track meals and nutrition  
✅ **Health Monitoring** - Temperature, activity levels, and more  
✅ **Multi-Pet Support** - Manage multiple dogs simultaneously  
✅ **Weather Integration** - Weather-aware recommendations  
✅ **Automations** - Powerful automation capabilities  
✅ **Mobile App Support** - Full Home Assistant mobile app integration

## Installation

### Prerequisites

- Home Assistant 2025.9.0 or newer
- Python 3.13+
- Active internet connection
- PawControl-compatible device (collar, tracker, etc.)

### Method 1: HACS (Recommended)

1. **Open HACS** in your Home Assistant interface
2. Click on **"Integrations"**
3. Click the **"+"** button in the bottom right
4. Search for **"PawControl"**
5. Click **"Download"**
6. Restart Home Assistant

### Method 2: Manual Installation

1. Download the latest release from [GitHub](https://github.com/yourusername/pawcontrol)
2. Extract the `pawcontrol` folder to your `custom_components` directory:
   ```
   config/
   └── custom_components/
       └── pawcontrol/
           ├── __init__.py
           ├── manifest.json
           └── ... (other files)
   ```
3. Restart Home Assistant

## Initial Setup

### Step 1: Add the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"PawControl"**
4. Click to begin setup

### Step 2: Enter API Credentials

You'll need your PawControl API credentials:

- **API Endpoint**: Provided by your device manufacturer
- **API Token**: Found in your device's mobile app under Settings → API Access
- **Username/Password**: Your account credentials (if required)

**Example:**
```
API Endpoint: https://api.pawcontrol.example.com
API Token: eyJhbGciOiJIUzI1NiIs...
```

### Step 3: Configure Update Interval

Set how often PawControl fetches data:

- **Fast (30 seconds)**: More frequent updates, higher battery usage
- **Normal (2 minutes)**: Balanced - recommended for most users
- **Slow (5 minutes)**: Less frequent, conserves battery

**Recommendation:** Start with Normal (2 minutes) and adjust based on your needs.

### Step 4: Select Your Dogs

1. PawControl will auto-discover your registered devices
2. Select which dogs to add to Home Assistant
3. Customize dog names and settings
4. Enable modules for each dog:
   - ☑ GPS Tracking
   - ☑ Walk Detection
   - ☑ Feeding Tracker
   - ☑ Health Monitoring

### Step 5: Complete Setup

Click **"Submit"** and PawControl will:
- Connect to your devices
- Create entities for each dog
- Set up automations (if enabled)
- Begin tracking

## Understanding Your Entities

After setup, you'll see entities for each dog:

### Core Entities

**Device Tracker:**
- `device_tracker.buddy` - Current location

**Sensors:**
- `sensor.buddy_gps_latitude` - GPS latitude
- `sensor.buddy_gps_longitude` - GPS longitude
- `sensor.buddy_gps_accuracy` - Location accuracy (meters)
- `sensor.buddy_battery_level` - Device battery percentage
- `sensor.buddy_last_walk_duration` - Duration of last walk
- `sensor.buddy_last_walk_distance` - Distance of last walk
- `sensor.buddy_last_meal_time` - Time of last meal
- `sensor.buddy_daily_calories` - Calories consumed today

**Binary Sensors:**
- `binary_sensor.buddy_walk_in_progress` - Currently on walk
- `binary_sensor.buddy_in_safe_zone` - Inside geofence
- `binary_sensor.buddy_battery_low` - Battery below 20%

**Switches:**
- `switch.buddy_gps_tracking` - Enable/disable GPS
- `switch.buddy_walk_detection` - Enable/disable auto-walk detection

### Finding Your Entities

1. Go to **Settings** → **Devices & Services** → **PawControl**
2. Click on your dog's device
3. View all entities

Or search in the **Developer Tools** → **States** tab.

## Quick Start: Your First Automation

### Example 1: Notify When Walk Starts

```yaml
alias: "Buddy - Walk Started Notification"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_walk_in_progress
    to: "on"
action:
  - service: notify.mobile_app
    data:
      title: "🐕 Walk Started"
      message: "Buddy is on a walk!"
```

### Example 2: Low Battery Alert

```yaml
alias: "Buddy - Low Battery Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.buddy_battery_level
    below: 20
action:
  - service: notify.mobile_app
    data:
      title: "🔋 Low Battery"
      message: "Buddy's collar battery is at {{ states('sensor.buddy_battery_level') }}%"
      data:
        priority: high
```

### Example 3: Safe Zone Alert

```yaml
alias: "Buddy - Left Safe Zone"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_in_safe_zone
    to: "off"
action:
  - service: notify.mobile_app
    data:
      title: "⚠️ Alert"
      message: "Buddy has left the safe zone!"
      data:
        priority: critical
```

## Creating Your Dashboard

### Basic Lovelace Card

```yaml
type: entities
title: Buddy
entities:
  - entity: device_tracker.buddy
  - entity: sensor.buddy_battery_level
  - entity: binary_sensor.buddy_walk_in_progress
  - entity: sensor.buddy_last_walk_distance
  - entity: sensor.buddy_last_meal_time
```

### Map Card

```yaml
type: map
entities:
  - device_tracker.buddy
hours_to_show: 24
```

### Gauge Card for Battery

```yaml
type: gauge
entity: sensor.buddy_battery_level
min: 0
max: 100
severity:
  green: 50
  yellow: 30
  red: 0
```

## Common Tasks

### Changing Update Interval

1. Go to **Settings** → **Devices & Services** → **PawControl**
2. Click **"Configure"**
3. Adjust **Update Interval**
4. Click **"Submit"**

### Adding a New Dog

1. Register the new device in your PawControl app
2. Go to **Settings** → **Devices & Services** → **PawControl**
3. Click **"Configure"** → **"Add Dog"**
4. Select the new dog and configure modules

### Setting Up Geofencing

1. Go to **Settings** → **Devices & Services** → **PawControl**
2. Click **"Configure"** → **"Geofences"**
3. Click **"+ Add Zone"**
4. Define zone:
   - Name: "Home"
   - Latitude: 45.5231
   - Longitude: -122.6765
   - Radius: 100 (meters)
5. Click **"Save"**

### Viewing Walk History

1. Go to **History** in Home Assistant
2. Select `sensor.buddy_last_walk_distance`
3. View historical walk data
4. Export to CSV if needed

## Troubleshooting

### No Data Showing

**Check:**
1. API credentials are correct
2. Device has internet connection
3. Battery level is sufficient (>10%)
4. Integration is not disabled

**Fix:**
- Go to **Settings** → **Devices & Services** → **PawControl**
- Click **"..."** → **"Reload"**

### GPS Coordinates Not Updating

**Check:**
1. GPS module is enabled
2. Device has GPS signal (outdoors)
3. `switch.buddy_gps_tracking` is ON

**Fix:**
- Toggle GPS switch off/on
- Check device's GPS settings in mobile app

### High Battery Drain

**Solutions:**
1. Increase update interval (2min → 5min)
2. Disable continuous GPS tracking
3. Enable battery saver mode in mobile app

### Walk Not Detected

**Check:**
1. Walk detection is enabled
2. Minimum distance threshold (default: 0.1 km)
3. Minimum duration threshold (default: 5 min)

**Configure:**
- Go to **Settings** → **Devices & Services** → **PawControl**
- Click **"Configure"** → **"Walk Detection"**
- Adjust thresholds

## Getting Help

### Support Resources

- **Documentation**: [Read the Docs](https://pawcontrol.readthedocs.io)
- **Community Forum**: [Home Assistant Community](https://community.home-assistant.io)
- **GitHub Issues**: [Report Bugs](https://github.com/yourusername/pawcontrol/issues)
- **Discord**: [Join our server](https://discord.gg/pawcontrol)

### Logs and Diagnostics

Enable debug logging:

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.pawcontrol: debug
```

Download diagnostics:
1. Go to **Settings** → **Devices & Services** → **PawControl**
2. Click **"..."** → **"Download Diagnostics"**
3. Attach to support requests

### FAQ

**Q: How many dogs can I track?**  
A: Unlimited! PawControl supports as many dogs as you have devices for.

**Q: Does this work offline?**  
A: GPS tracking requires internet for real-time updates. Cached data is available offline.

**Q: Can I track cats?**  
A: Absolutely! PawControl works with any compatible tracking device.

**Q: Is my data private?**  
A: Yes! All data is stored locally in Home Assistant. See our [Privacy Policy](privacy.md).

**Q: How accurate is the GPS?**  
A: Typically 5-15 meters outdoors. Indoor accuracy may be reduced.

## Next Steps

Now that you're set up:

1. **Explore Blueprints**: Pre-made automations for common scenarios
2. **Customize Dashboard**: Create the perfect pet dashboard
3. **Set Up Notifications**: Never miss important events
4. **Join Community**: Share your setup and get ideas

Ready to take it further? Check out:
- [Advanced Configuration Guide](advanced_config.md)
- [Automation Examples](automation_examples.md)
- [Blueprint Library](blueprints.md)
- [API Reference](api_reference.md)

---

**Welcome to the PawControl family! 🐾**

If you find PawControl useful, please:
- ⭐ Star us on [GitHub](https://github.com/yourusername/pawcontrol)
- 💬 Share in the community
- 🐛 Report bugs to help improve
- 📖 Contribute to documentation

Happy pet monitoring! 🐕❤️
