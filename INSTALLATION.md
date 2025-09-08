# 📦 Installation Guide - PawControl Integration

## 🚀 Quick Installation

### Method 1: HACS (Recommended)

1. **Install HACS** (if not already installed):
   - Follow [HACS Installation Guide](https://hacs.xyz/docs/installation/installation)

2. **Add PawControl Repository**:
   - HACS → Integrations → ⋮ Menu → Custom repositories
   - Repository: `https://github.com/BigDaddy1990/pawcontrol`
   - Category: Integration → Add

3. **Install Integration**:
   - Search "PawControl" in HACS Integrations
   - Download → Restart Home Assistant

4. **Configure Integration**:
   - Settings → Devices & Services → Add Integration
   - Search "PawControl" → Follow setup wizard

### Method 2: Manual Installation

1. **Download Integration**:
   ```bash
   cd /config/custom_components/
   wget https://github.com/BigDaddy1990/pawcontrol/archive/main.zip
   unzip main.zip
   mv pawcontrol-main pawcontrol
   ```

2. **Verify Structure**:
   ```
   /config/custom_components/pawcontrol/
   ├── __init__.py
   ├── manifest.json
   ├── config_flow.py
   └── [40+ other files]
   ```

3. **Restart Home Assistant**

4. **Add Integration**: Settings → Devices & Services → Add Integration → PawControl

## ⚙️ Setup Wizard

### Step 1: Basic Configuration
- **Dog Name**: Enter your dog's name (required)
- **Dog Breed**: Optional breed information
- **Age & Weight**: Physical characteristics for calculations

### Step 2: Module Selection
Choose which features to enable:

- **🍽️ Feeding Management**: Meal tracking and reminders
- **🗺️ GPS Tracking**: Location monitoring and walks
- **🏥 Health Monitoring**: Weight, medications, vet visits
- **🚪 Activity Tracking**: Door sensors and exercise
- **📱 Notifications**: Mobile alerts and automations
- **📊 Dashboard**: Auto-generated UI components

### Step 3: Hardware Integration (Optional)
- **Door Sensors**: Select entities for walk detection
- **GPS Sources**: Configure location tracking
- **Smart Scales**: Weight monitoring integration
- **Mobile Apps**: Notification targets

### Step 4: Notification Setup (Optional)
- **Mobile Apps**: Select notification targets
- **Person Entities**: Auto-detect who's home
- **Quiet Hours**: Configure do-not-disturb times
- **Alert Types**: Choose notification categories

## 🔧 Configuration Examples

### Basic Single Dog Setup
```yaml
# Minimal configuration - created via UI
Dog Name: "Buddy"
Modules: ["feeding", "health"]
Notifications: Mobile App
```

### Advanced Multi-Dog Setup
```yaml
# Multiple dogs with full features
Dog 1: "Buddy" - GPS + Feeding + Health
Dog 2: "Luna" - Feeding + Health only
GPS Source: Tractive Integration
Door Sensor: binary_sensor.front_door
Notifications: All family mobile apps
```

### GPS Integration Examples

#### Option 1: Device Tracker Integration
```yaml
# Use existing device tracker
GPS Source: device_tracker.buddy_tractive
Update Interval: 60 seconds
Geofence: 50 meter home radius
```

#### Option 2: Mobile App GPS
```yaml
# Use phone GPS when walking
GPS Source: Person Entity
Person: person.dog_walker
Accuracy Threshold: 10 meters
```

#### Option 3: MQTT GPS Feed
```yaml
# Custom GPS device via MQTT
GPS Source: MQTT
Topic: "pets/buddy/location"
Format: {"lat": 52.5, "lon": 13.4, "accuracy": 5}
```

## 📱 Dashboard Setup

### Automatic Dashboard Creation
PawControl can auto-generate beautiful dashboards:

1. **Enable in Setup**: Check "Create Dashboard" option
2. **Dashboard Created**: `/lovelace/pawcontrol-[dogname]`
3. **Mobile Optimized**: Responsive design for all devices

### Manual Dashboard Integration

#### Basic Status Card
```yaml
type: entities
title: Buddy Status
entities:
  - sensor.buddy_feeding_status
  - sensor.buddy_last_walk
  - sensor.buddy_health_score
  - binary_sensor.buddy_needs_feeding
```

#### GPS Map Card
```yaml
type: map
entities:
  - device_tracker.buddy_gps
hours_to_show: 24
aspect_ratio: 16:9
```

#### Quick Action Buttons
```yaml
type: horizontal-stack
cards:
  - type: button
    tap_action:
      action: call-service
      service: button.press
      target:
        entity_id: button.buddy_feed_breakfast
    name: Feed Breakfast
  - type: button
    tap_action:
      action: call-service
      service: button.press
      target:
        entity_id: button.buddy_start_walk
    name: Start Walk
```

## 🔔 Notification Configuration

### iOS Setup
1. **Install Home Assistant App**
2. **Enable Notifications**: Settings → Notifications → Allow
3. **Configure in PawControl**: Select mobile app service
4. **Test**: Use "Test Notification" button in integration

### Android Setup
1. **Install Home Assistant App**
2. **Grant Permissions**: Location + Notifications
3. **Battery Optimization**: Disable for HA app
4. **Configure in PawControl**: Select mobile app service

### Actionable Notification Examples

#### Feeding Reminder
```
Title: "🍽️ Feeding Time!"
Message: "Time to feed Buddy breakfast"
Actions: 
  - "Fed ✅" → Mark as complete
  - "10 min ⏰" → Snooze reminder
```

#### Walk Detection
```
Title: "🚪 Door Opened"
Message: "Did Buddy go outside?"
Actions:
  - "Yes, walking 🚶" → Start walk tracking
  - "No, still inside 🏠" → Dismiss
```

## 🧪 Testing Your Setup

### 1. Basic Functionality Test
- Check entity creation: Developer Tools → States
- Look for `sensor.buddy_*`, `binary_sensor.buddy_*`, etc.

### 2. Notification Test
- Use "Test Notification" button in integration settings
- Verify mobile app receives notification

### 3. GPS Test (if enabled)
- Check `device_tracker.buddy_gps` updates
- Verify location accuracy in Developer Tools

### 4. Feeding Test
- Press "Feed Breakfast" button
- Check `sensor.buddy_breakfast_count` increments
- Verify notification dismissal

## 🔍 Troubleshooting

### Integration Won't Load
**Symptoms**: PawControl not in integration list
**Solutions**:
1. Verify file structure: `/config/custom_components/pawcontrol/`
2. Check Home Assistant version: 2025.9.0+ required
3. Restart Home Assistant
4. Check logs: `grep pawcontrol /config/home-assistant.log`

### Entities Not Created
**Symptoms**: No `sensor.buddy_*` entities
**Solutions**:
1. Complete integration setup through UI
2. Enable modules in configuration
3. Restart Home Assistant
4. Check entity registry: Settings → Entities

### GPS Not Updating
**Symptoms**: `device_tracker.buddy_gps` shows "unavailable"
**Solutions**:
1. Verify GPS source configuration
2. Check mobile app location permissions
3. Test with manual location update
4. Check accuracy threshold settings

### Notifications Not Working
**Symptoms**: No mobile notifications received
**Solutions**:
1. Verify mobile app installation and permissions
2. Test Home Assistant notifications work generally
3. Check notification service configuration
4. Try persistent notifications as fallback

### Dashboard Not Appearing
**Symptoms**: Auto-generated dashboard missing
**Solutions**:
1. Verify dashboard creation was enabled in setup
2. Check Lovelace resources loaded
3. Clear browser cache
4. Create manual dashboard using provided examples

## 📊 Performance Optimization

### Large Installations (5+ Dogs)
- **Batch Updates**: Enabled automatically for 5+ dogs
- **Cache Tuning**: Increase cache size in advanced options
- **Update Intervals**: Consider longer GPS update intervals
- **Module Selection**: Enable only needed features per dog

### Low-Resource Systems
- **Disable Diagnostics**: Reduce logging overhead
- **Limit History**: Shorter data retention periods
- **Simple Dashboards**: Use basic cards instead of complex layouts
- **Reduce Polling**: Longer update intervals for non-critical data

## 🆘 Getting Help

### Self-Help Resources
1. **Check Logs**: Configuration → Logs → Filter "pawcontrol"
2. **Entity Registry**: Settings → Entities → Search "pawcontrol"
3. **Integration Info**: Settings → Devices & Services → PawControl
4. **Diagnostics**: Download diagnostic data from integration

### Community Support
- **GitHub Issues**: [Bug reports and feature requests](https://github.com/BigDaddy1990/pawcontrol/issues)
- **Home Assistant Forum**: [Community discussions](https://community.home-assistant.io/)
- **Discord**: Home Assistant community channels

### Bug Reports
When reporting issues, include:
1. **Home Assistant Version**
2. **PawControl Version**
3. **Configuration Details** (anonymized)
4. **Error Logs** (relevant portions)
5. **Steps to Reproduce**

## 🔄 Updates and Maintenance

### HACS Updates
- Automatic update notifications in HACS
- Review changelog before updating
- Backup configuration before major updates

### Manual Updates
```bash
cd /config/custom_components/pawcontrol/
git pull origin main
# Restart Home Assistant
```

### Configuration Backup
```yaml
# Include in Home Assistant backups automatically
# Manual backup of key data:
pawcontrol:
  dogs: [exported via integration]
  settings: [available in diagnostics]
```

---

**🎉 Congratulations!** You've successfully installed PawControl. Your smart dog management system is ready to help you provide the best care for your furry family members.

For advanced configuration options and automation examples, see our [Advanced Configuration Guide](CONFIGURATION.md).
