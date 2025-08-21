# Paw Control - Smart Dog Monitoring for Home Assistant

![Paw Control Logo](https://img.shields.io/badge/Paw%20Control-Smart%20Dog%20Monitoring-blue?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEyIDJMMTMuMDkgOC4yNkwyMCA5TDEzLjA5IDE1Ljc0TDEyIDIyTDEwLjkxIDE1Ljc0TDQgOUwxMC45MSA4LjI2TDEyIDJaIiBmaWxsPSJjdXJyZW50Q29sb3IiLz4KPC9zdmc+)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/pawcontrol/pawcontrol-homeassistant.svg?style=for-the-badge)](https://github.com/pawcontrol/pawcontrol-homeassistant/releases)
[![License](https://img.shields.io/github/license/pawcontrol/pawcontrol-homeassistant.svg?style=for-the-badge)](LICENSE)

A comprehensive smart dog monitoring integration for Home Assistant that tracks feeding, walks, health, GPS location, and more. Turn your Home Assistant into the ultimate pet care command center!

## 🐕 Features

### 📱 **Complete Dog Monitoring**
- **Multi-Dog Support**: Monitor multiple dogs with individual configurations
- **Modular Design**: Enable only the features you need for each dog
- **Smart Notifications**: Intelligent alerts with priority management and quiet hours
- **Data Persistence**: Long-term storage with automatic cleanup and export capabilities

### 🍽️ **Feeding Tracking**
- Log meals, snacks, and treats with portion sizes
- Automatic feeding reminders based on schedule
- Daily nutrition tracking and calorie monitoring
- Schedule adherence monitoring with alerts
- Support for different food types (dry, wet, BARF, home-cooked)

### 🚶‍♂️ **Walk Monitoring**
- Manual or automatic walk tracking
- GPS route recording and analysis
- Duration, distance, and speed tracking
- Daily activity goals and progress
- Weather-based walk recommendations

### 📍 **GPS Location Tracking**
- Real-time location monitoring
- Geofencing with safe zone alerts
- Multiple GPS source support (smartphone, dedicated tracker, manual)
- Location history and route visualization
- Battery monitoring for GPS devices

### 🏥 **Health Monitoring**
- Weight tracking with trend analysis
- Medication reminders and logging
- Vet appointment scheduling
- Activity level monitoring
- Mood and behavior tracking
- Grooming schedule management

### 🔔 **Smart Notifications**
- Priority-based notification system
- Multiple delivery methods (persistent, mobile app, email, TTS)
- Quiet hours and do-not-disturb modes
- Rate limiting to prevent spam
- Customizable per-dog notification settings

## 📦 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/pawcontrol/pawcontrol-homeassistant`
6. Select "Integration" as the category
7. Click "Add"
8. Find "Paw Control" in the HACS store and install it
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/pawcontrol/pawcontrol-homeassistant/releases)
2. Extract the files
3. Copy the `custom_components/pawcontrol` folder to your Home Assistant `custom_components` directory
4. Restart Home Assistant

## ⚙️ Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"Paw Control"**
4. Follow the configuration wizard:
   - Set integration name and update interval
   - Add your dogs (name, ID, breed, age, weight, size)
   - Enable desired modules for each dog
   - Configure module-specific settings
   - Set up notification preferences

### Dog Configuration

Each dog can be configured with the following information:

```yaml
# Example dog configuration
dogs:
  - dog_id: "buddy"
    dog_name: "Buddy"
    dog_breed: "Golden Retriever"
    dog_age: 5
    dog_weight: 30.5
    dog_size: "large"
    modules:
      feeding: true
      walk: true
      gps: true
      health: true
      notifications: true
```

### Module Configuration

#### Feeding Module
- Daily food amount and meal schedule
- Portion sizes and calorie targets
- Food type and feeding mode
- Reminder intervals

#### Walk Module
- Daily walk targets (count, duration, distance)
- Walk detection mode (automatic/manual/hybrid)
- Weather preferences
- Reminder settings

#### GPS Module
- GPS data source configuration
- Tracking mode and accuracy settings
- Geofence radius and safe zones
- Update intervals and battery thresholds

#### Health Module
- Target weight and alert thresholds
- Medication and vet appointment reminders
- Grooming intervals
- Activity tracking settings

## 🎯 Usage

### Entities Created

For each dog, the integration creates numerous entities across different platforms:

#### Sensors
- `sensor.{dog_name}_last_feeding`
- `sensor.{dog_name}_daily_food_consumed`
- `sensor.{dog_name}_last_walk`
- `sensor.{dog_name}_daily_walk_distance`
- `sensor.{dog_name}_current_location`
- `sensor.{dog_name}_current_weight`
- `sensor.{dog_name}_health_score`

#### Binary Sensors
- `binary_sensor.{dog_name}_is_hungry`
- `binary_sensor.{dog_name}_needs_walk`
- `binary_sensor.{dog_name}_is_home`
- `binary_sensor.{dog_name}_health_alert`
- `binary_sensor.{dog_name}_attention_needed`

#### Buttons
- `button.{dog_name}_mark_fed`
- `button.{dog_name}_start_walk`
- `button.{dog_name}_log_weight`
- `button.{dog_name}_refresh_location`

#### Switches
- `switch.{dog_name}_feeding_alerts`
- `switch.{dog_name}_gps_tracking`
- `switch.{dog_name}_visitor_mode`

#### Numbers
- `number.{dog_name}_weight`
- `number.{dog_name}_daily_food_amount`
- `number.{dog_name}_walk_duration_target`

#### Selects
- `select.{dog_name}_food_type`
- `select.{dog_name}_activity_level`
- `select.{dog_name}_mood`

#### Device Tracker
- `device_tracker.{dog_name}_gps`

### Quick Actions

The integration provides convenient buttons for common actions:

- **Mark Fed**: Quickly log a feeding
- **Start/End Walk**: Track walk sessions
- **Log Weight**: Record weight measurements
- **Refresh Location**: Update GPS position
- **Test Notification**: Verify notification settings

## 🔧 Services

The integration provides comprehensive services for automation and advanced control:

### Feeding Services

```yaml
# Log a feeding
service: pawcontrol.feed_dog
data:
  dog_id: "buddy"
  meal_type: "dinner"
  portion_size: 200
  food_type: "dry_food"
  notes: "Normal dinner portion"
```

### Walk Services

```yaml
# Start a walk
service: pawcontrol.start_walk
data:
  dog_id: "buddy"
  label: "Morning walk"
  location: "Park"

# End a walk
service: pawcontrol.end_walk
data:
  dog_id: "buddy"
  distance: 2000
  duration: 45
  notes: "Great walk, lots of energy"
```

### Health Services

```yaml
# Log health data
service: pawcontrol.log_health
data:
  dog_id: "buddy"
  weight: 30.2
  mood: "happy"
  activity_level: "high"
  note: "Very active today"

# Log medication
service: pawcontrol.log_medication
data:
  dog_id: "buddy"
  medication_name: "Heartworm Prevention"
  dosage: "1 tablet"
  next_dose: "2024-01-15 08:00:00"
```

### Location Services

```yaml
# Update location manually
service: pawcontrol.update_location
data:
  dog_id: "buddy"
  latitude: 40.7128
  longitude: -74.0060
  accuracy: 5
  source: "manual"
```

### Utility Services

```yaml
# Set visitor mode
service: pawcontrol.set_visitor_mode
data:
  dog_id: "buddy"
  enabled: true
  visitor_name: "Pet Sitter"
  reduced_alerts: true

# Generate report
service: pawcontrol.generate_report
data:
  dog_id: "buddy"
  report_type: "weekly"
  format: "pdf"
  include_sections: ["feeding", "walks", "health"]

# Export data
service: pawcontrol.export_data
data:
  dog_id: "buddy"
  data_type: "all"
  format: "json"
  start_date: "2024-01-01"
  end_date: "2024-01-31"
```

## 🤖 Automation Examples

### Feeding Reminders

```yaml
automation:
  - alias: "Buddy Feeding Reminder"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_is_hungry
        to: "on"
    condition:
      - condition: time
        after: "07:00:00"
        before: "22:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "🍽️ Buddy is Hungry"
          message: "Time to feed Buddy!"
          data:
            actions:
              - action: "MARK_FED"
                title: "Mark as Fed"
```

### Walk Notifications

```yaml
automation:
  - alias: "Walk Reminder Based on Weather"
    trigger:
      - platform: time
        at: "18:00:00"
    condition:
      - condition: state
        entity_id: binary_sensor.buddy_needs_walk
        state: "on"
      - condition: numeric_state
        entity_id: weather.home
        attribute: temperature
        above: 5
        below: 30
    action:
      - service: pawcontrol.notify_test
        data:
          dog_id: "buddy"
          message: "Perfect weather for a walk!"
          priority: "normal"
```

### Health Monitoring

```yaml
automation:
  - alias: "Weight Change Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_weight_alert
        to: "on"
    action:
      - service: persistent_notification.create
        data:
          title: "⚠️ Weight Alert - Buddy"
          message: "Buddy's weight has changed significantly. Consider a vet consultation."
          notification_id: "buddy_weight_alert"
```

### GPS and Location

```yaml
automation:
  - alias: "Dog Left Home Alert"
    trigger:
      - platform: state
        entity_id: device_tracker.buddy_gps
        from: "home"
    action:
      - service: notify.family
        data:
          title: "🏠 Buddy Left Home"
          message: "Buddy has left the house at {{ now().strftime('%H:%M') }}"

  - alias: "Outside Safe Zone Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_in_safe_zone
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "🚨 URGENT: Buddy Outside Safe Zone"
          message: "Buddy is outside the designated safe zone!"
          data:
            priority: "high"
            persistent: true
```

### Daily Reports

```yaml
automation:
  - alias: "Daily Dog Report"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: pawcontrol.generate_report
        data:
          dog_id: "buddy"
          report_type: "daily"
          send_notification: true
```

## 📊 Dashboard Configuration

### Lovelace Card Examples

#### Dog Overview Card

```yaml
type: vertical-stack
cards:
  - type: picture-entity
    entity: device_tracker.buddy_gps
    image: /local/images/buddy.jpg
    name: Buddy
  - type: entities
    entities:
      - entity: sensor.buddy_last_feeding
        name: Last Fed
      - entity: sensor.buddy_last_walk
        name: Last Walk
      - entity: sensor.buddy_current_weight
        name: Weight
      - entity: binary_sensor.buddy_attention_needed
        name: Needs Attention
```

#### Quick Actions Card

```yaml
type: horizontal-stack
cards:
  - type: button
    tap_action:
      action: call-service
      service: button.press
      target:
        entity_id: button.buddy_mark_fed
    icon: mdi:food-drumstick
    name: Feed
  - type: button
    tap_action:
      action: call-service
      service: button.press
      target:
        entity_id: button.buddy_start_walk
    icon: mdi:walk
    name: Walk
  - type: button
    tap_action:
      action: call-service
      service: button.press
      target:
        entity_id: button.buddy_log_weight
    icon: mdi:scale
    name: Weigh
```

#### Health Monitoring Card

```yaml
type: entities
entities:
  - entity: sensor.buddy_health_score
    name: Health Score
  - entity: sensor.buddy_current_weight
    name: Current Weight
  - entity: binary_sensor.buddy_health_alert
    name: Health Alert
  - entity: binary_sensor.buddy_medication_due
    name: Medication Due
  - entity: sensor.buddy_next_vet_appointment
    name: Next Vet Visit
```

## 🔧 Advanced Configuration

### GPS Source Configuration

The integration supports multiple GPS sources:

#### Smartphone Integration

```yaml
# Use person entity as GPS source
gps_source: "person_entity"
person_entity: "person.dog_walker"
```

#### Dedicated GPS Tracker

```yaml
# Use device tracker from GPS collar
gps_source: "device_tracker"
device_tracker_entity: "device_tracker.buddy_gps_collar"
```

#### Manual Location Updates

```yaml
# Manual location updates via services
gps_source: "manual"
```

### Notification Customization

#### Per-Dog Notification Settings

```yaml
# Configure notifications for each dog
notifications:
  buddy:
    feeding_alerts: true
    walk_alerts: true
    health_alerts: true
    gps_alerts: true
    delivery_methods: ["persistent", "mobile_app"]
    quiet_hours_start: "22:00"
    quiet_hours_end: "07:00"
```

#### Global Notification Settings

```yaml
# Global notification configuration
global_notifications:
  enabled: true
  default_priority: "normal"
  mobile_app_service: "notify.mobile_app_iphone"
  email_service: "notify.email"
```

## 🔍 Troubleshooting

### Common Issues

#### GPS Not Updating

1. Check GPS source configuration
2. Verify device tracker entity is available
3. Ensure GPS module is enabled for the dog
4. Check update interval settings

```yaml
# Debug GPS issues
logger:
  logs:
    custom_components.pawcontrol.device_tracker: debug
    custom_components.pawcontrol.coordinator: debug
```

#### Notifications Not Working

1. Verify notification settings are enabled
2. Check quiet hours configuration
3. Ensure notification service is available
4. Test with the test notification service

```yaml
# Test notifications
service: pawcontrol.notify_test
data:
  dog_id: "buddy"
  message: "Test notification"
  priority: "urgent"
```

#### Data Not Persisting

1. Check Home Assistant storage permissions
2. Verify integration is properly configured
3. Review logs for storage errors
4. Restart Home Assistant if needed

### Debug Logging

Enable debug logging for troubleshooting:

```yaml
logger:
  default: warning
  logs:
    custom_components.pawcontrol: debug
```

### Data Recovery

Export data before making major changes:

```yaml
service: pawcontrol.export_data
data:
  dog_id: "buddy"
  data_type: "all"
  format: "json"
```

## 🛠️ Development

### Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure code quality (type hints, documentation)
5. Submit a pull request

### Development Setup

```bash
# Clone the repository
git clone https://github.com/pawcontrol/pawcontrol-homeassistant.git

# Install development dependencies
pip install -r requirements_dev.txt

# Run tests
pytest

# Run linting
pylint custom_components/pawcontrol/
black custom_components/pawcontrol/
```

### Code Quality Standards

This integration follows Home Assistant's Platinum quality standards:

- **Type Annotations**: Full type hints throughout
- **Async Operations**: All I/O operations are async
- **Error Handling**: Comprehensive exception handling
- **Documentation**: Docstrings for all public methods
- **Testing**: Unit tests for core functionality
- **Code Style**: Black formatting and pylint compliance

## 📚 API Reference

### Coordinator Methods

```python
# Get dog data
dog_data = coordinator.get_dog_data("buddy")

# Get module data
feeding_data = coordinator.get_module_data("buddy", "feeding")

# Refresh specific dog data
await coordinator.async_refresh_dog("buddy")
```

### Data Manager Methods

```python
# Log feeding
await data_manager.async_log_feeding("buddy", {
    "meal_type": "dinner",
    "portion_size": 200,
    "food_type": "dry_food"
})

# Start walk
walk_id = await data_manager.async_start_walk("buddy", {
    "label": "Morning walk"
})

# Log health data
await data_manager.async_log_health("buddy", {
    "weight": 30.5,
    "mood": "happy"
})
```

## 📈 Roadmap

### Upcoming Features

- **🎯 AI-Powered Insights**: Machine learning for behavior pattern recognition
- **📱 Mobile App**: Dedicated mobile application for quick actions
- **🔗 Third-Party Integrations**: Support for popular pet care apps and devices
- **📊 Advanced Analytics**: Detailed health and activity reports
- **👥 Multi-User Support**: Family member access and role management
- **🏥 Veterinary Integration**: Direct vet communication and record sharing

### Version History

- **v1.0.0**: Initial release with core functionality
- **v1.1.0**: Added advanced GPS features and notifications
- **v1.2.0**: Health monitoring enhancements
- **v1.3.0**: Multi-dog support and data export

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Support

- **Documentation**: [Full documentation](https://pawcontrol.github.io/docs)
- **Issues**: [GitHub Issues](https://github.com/pawcontrol/pawcontrol-homeassistant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/pawcontrol/pawcontrol-homeassistant/discussions)
- **Community**: [Home Assistant Community Forum](https://community.home-assistant.io/t/paw-control-smart-dog-monitoring)

## 🙏 Acknowledgments

- Home Assistant community for integration standards and examples
- All pet owners who provided feedback and feature requests
- Contributors who helped improve the codebase

---

**Made with ❤️ for dog lovers everywhere**

*Turn your Home Assistant into the ultimate pet care command center and never miss an important moment in your dog's life!*
