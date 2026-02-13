# PawControl Blueprint Library

Ready-to-use automation blueprints for PawControl. Import and customize!

## How to Use Blueprints

1. Click the **"Import Blueprint"** button below each blueprint
2. Or go to **Settings** → **Automations & Scenes** → **Blueprints**
3. Click **"Import Blueprint"** and paste the URL
4. Create automation from blueprint
5. Customize the inputs

---

## Walk Monitoring Blueprints

### 1. Walk Start/End Notifications

Get notified when your dog starts and ends a walk.

```yaml
blueprint:
  name: PawControl - Walk Notifications
  description: Notify when dog starts/ends walk with duration and distance
  domain: automation
  input:
    dog_walk_sensor:
      name: Walk In Progress Sensor
      selector:
        entity:
          domain: binary_sensor
          device_class: motion
    distance_sensor:
      name: Walk Distance Sensor
      selector:
        entity:
          domain: sensor
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    dog_name:
      name: Dog Name
      selector:
        text:

trigger:
  - platform: state
    entity_id: !input dog_walk_sensor
    to: "on"
    id: "walk_start"
  - platform: state
    entity_id: !input dog_walk_sensor
    to: "off"
    id: "walk_end"

action:
  - choose:
      - conditions:
          - condition: trigger
            id: "walk_start"
        sequence:
          - service: !input notification_service
            data:
              title: "🐕 Walk Started"
              message: "{{ dog_name }} is on a walk!"
      
      - conditions:
          - condition: trigger
            id: "walk_end"
        sequence:
          - service: !input notification_service
            data:
              title: "✅ Walk Complete"
              message: >
                {{ dog_name }} walked 
                {{ states(distance_sensor) }} km
variables:
  dog_name: !input dog_name
  distance_sensor: !input distance_sensor
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/walk_notifications.yaml)

---

### 2. Walk Reminder Schedule

Daily walk reminders with snooze functionality.

```yaml
blueprint:
  name: PawControl - Walk Reminder
  description: Remind to walk dog at scheduled times
  domain: automation
  input:
    dog_walk_sensor:
      name: Walk In Progress Sensor
      selector:
        entity:
          domain: binary_sensor
    walk_times:
      name: Walk Times
      description: Times to remind (one per line)
      selector:
        object:
      default:
        - "08:00"
        - "18:00"
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    dog_name:
      name: Dog Name
      selector:
        text:
    minimum_hours_between_walks:
      name: Minimum Hours Since Last Walk
      description: Only remind if this many hours passed
      selector:
        number:
          min: 1
          max: 24
          unit_of_measurement: hours
      default: 6

trigger:
  - platform: time
    at: !input walk_times

condition:
  - condition: state
    entity_id: !input dog_walk_sensor
    state: "off"
  - condition: template
    value_template: >
      {{ (now() - states[dog_walk_sensor].last_changed).total_seconds() 
         > (minimum_hours_between_walks * 3600) }}

action:
  - service: !input notification_service
    data:
      title: "🐕 Walk Time!"
      message: "Time for {{ dog_name }}'s walk"
      data:
        actions:
          - action: "SNOOZE_WALK_{{ dog_name | upper }}"
            title: "Snooze 1 hour"

variables:
  dog_name: !input dog_name
  dog_walk_sensor: !input dog_walk_sensor
  minimum_hours_between_walks: !input minimum_hours_between_walks
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/walk_reminder.yaml)

---

## Safety & Security Blueprints

### 3. Geofence Escape Alert

Critical alert when dog leaves safe zone.

```yaml
blueprint:
  name: PawControl - Escape Alert
  description: Alert when dog leaves safe zone
  domain: automation
  input:
    safe_zone_sensor:
      name: Safe Zone Sensor
      selector:
        entity:
          domain: binary_sensor
    dog_tracker:
      name: Dog Device Tracker
      selector:
        entity:
          domain: device_tracker
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    dog_name:
      name: Dog Name
      selector:
        text:
    alert_delay:
      name: Alert Delay
      description: Wait this long before alerting (to avoid false alarms)
      selector:
        number:
          min: 0
          max: 10
          unit_of_measurement: minutes
      default: 2
    critical_priority:
      name: Use Critical Priority
      selector:
        boolean:
      default: true

trigger:
  - platform: state
    entity_id: !input safe_zone_sensor
    to: "off"
    for:
      minutes: !input alert_delay

action:
  - service: !input notification_service
    data:
      title: "🚨 ALERT: {{ dog_name }} Escaped!"
      message: >
        {{ dog_name }} has left the safe zone!
        Location: {{ state_attr(dog_tracker, 'latitude') }}, 
                  {{ state_attr(dog_tracker, 'longitude') }}
      data:
        priority: "{{ 'critical' if critical_priority else 'high' }}"
        ttl: 0
        url: >
          https://www.google.com/maps?q={{
            state_attr(dog_tracker, 'latitude')
          }},{{
            state_attr(dog_tracker, 'longitude')
          }}
  
  - condition: template
    value_template: "{{ critical_priority }}"
  
  - service: tts.google_translate_say
    data:
      entity_id: media_player.all
      message: "Alert! {{ dog_name }} has left the safe zone!"

variables:
  dog_name: !input dog_name
  dog_tracker: !input dog_tracker
  critical_priority: !input critical_priority
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/escape_alert.yaml)

---

### 4. Low Battery Alert

Alert when device battery is low.

```yaml
blueprint:
  name: PawControl - Low Battery Alert
  description: Alert when collar battery is low
  domain: automation
  input:
    battery_sensor:
      name: Battery Level Sensor
      selector:
        entity:
          domain: sensor
          device_class: battery
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    dog_name:
      name: Dog Name
      selector:
        text:
    battery_threshold:
      name: Battery Threshold
      description: Alert when battery drops below this percentage
      selector:
        number:
          min: 5
          max: 50
          unit_of_measurement: "%"
      default: 20
    repeat_hours:
      name: Repeat Alert Every (hours)
      selector:
        number:
          min: 1
          max: 24
          unit_of_measurement: hours
      default: 6

trigger:
  - platform: numeric_state
    entity_id: !input battery_sensor
    below: !input battery_threshold

condition:
  - condition: template
    value_template: >
      {{ (now() - this.attributes.get('last_triggered', now() - timedelta(days=1))).total_seconds() 
         > (repeat_hours * 3600) }}

action:
  - service: !input notification_service
    data:
      title: "🔋 Low Battery"
      message: >
        {{ dog_name }}'s collar battery is {{ states(battery_sensor) }}%
        Please charge soon!
      data:
        priority: high

variables:
  dog_name: !input dog_name
  battery_sensor: !input battery_sensor
  repeat_hours: !input repeat_hours
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/low_battery_alert.yaml)

---

## Health & Wellness Blueprints

### 5. Daily Activity Summary

End-of-day activity report.

```yaml
blueprint:
  name: PawControl - Daily Activity Summary
  description: Daily summary of walks and activity
  domain: automation
  input:
    walks_today_sensor:
      name: Walks Today Sensor
      selector:
        entity:
          domain: sensor
    distance_today_sensor:
      name: Total Distance Today Sensor
      selector:
        entity:
          domain: sensor
    walk_time_sensor:
      name: Total Walk Time Today Sensor
      selector:
        entity:
          domain: sensor
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    dog_name:
      name: Dog Name
      selector:
        text:
    summary_time:
      name: Summary Time
      selector:
        time:
      default: "21:00:00"

trigger:
  - platform: time
    at: !input summary_time

action:
  - service: !input notification_service
    data:
      title: "📊 {{ dog_name }}'s Daily Summary"
      message: >
        Today's activity:
        🚶 {{ states(walks_today_sensor) }} walks
        📏 {{ states(distance_today_sensor) }} km
        ⏱ {{ states(walk_time_sensor) }} minutes
        
        {% if states(walks_today_sensor) | int == 0 %}
        ⚠️ No walks today!
        {% elif states(distance_today_sensor) | float > 5 %}
        🏆 Great activity day!
        {% endif %}

variables:
  dog_name: !input dog_name
  walks_today_sensor: !input walks_today_sensor
  distance_today_sensor: !input distance_today_sensor
  walk_time_sensor: !input walk_time_sensor
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/daily_summary.yaml)

---

### 6. Weather-Based Walk Suggestion

Smart walk suggestions based on weather.

```yaml
blueprint:
  name: PawControl - Weather Walk Suggestion
  description: Suggest walks when weather is optimal
  domain: automation
  input:
    dog_walk_sensor:
      name: Walk In Progress Sensor
      selector:
        entity:
          domain: binary_sensor
    weather_entity:
      name: Weather Entity
      selector:
        entity:
          domain: weather
    temperature_sensor:
      name: Temperature Sensor
      selector:
        entity:
          domain: sensor
          device_class: temperature
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    dog_name:
      name: Dog Name
      selector:
        text:
    min_temp:
      name: Minimum Temperature
      selector:
        number:
          min: -20
          max: 40
          unit_of_measurement: "°C"
      default: 10
    max_temp:
      name: Maximum Temperature
      selector:
        number:
          min: -20
          max: 40
          unit_of_measurement: "°C"
      default: 28
    good_weather_conditions:
      name: Good Weather Conditions
      selector:
        select:
          options:
            - sunny
            - partlycloudy
            - cloudy
          multiple: true
      default:
        - sunny
        - partlycloudy

trigger:
  - platform: state
    entity_id: !input weather_entity
    to: !input good_weather_conditions
  - platform: numeric_state
    entity_id: !input temperature_sensor
    above: !input min_temp
    below: !input max_temp

condition:
  - condition: state
    entity_id: !input dog_walk_sensor
    state: "off"
  - condition: state
    entity_id: !input weather_entity
    state: !input good_weather_conditions
  - condition: numeric_state
    entity_id: !input temperature_sensor
    above: !input min_temp
    below: !input max_temp
  - condition: time
    after: "08:00:00"
    before: "20:00:00"
  - condition: template
    value_template: >
      {{ (now() - states[dog_walk_sensor].last_changed).total_seconds() > 14400 }}

action:
  - service: !input notification_service
    data:
      title: "☀️ Perfect Walk Weather!"
      message: >
        Great time for a walk with {{ dog_name }}!
        {{ states(weather_entity) | title }}, {{ states(temperature_sensor) }}°C

variables:
  dog_name: !input dog_name
  dog_walk_sensor: !input dog_walk_sensor
  weather_entity: !input weather_entity
  temperature_sensor: !input temperature_sensor
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/weather_walk_suggestion.yaml)

---

## Feeding Blueprints

### 7. Feeding Schedule Reminder

Never miss a meal time.

```yaml
blueprint:
  name: PawControl - Feeding Reminder
  description: Remind to feed dog at scheduled times
  domain: automation
  input:
    last_meal_sensor:
      name: Last Meal Time Sensor
      selector:
        entity:
          domain: sensor
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    dog_name:
      name: Dog Name
      selector:
        text:
    feeding_times:
      name: Feeding Times
      description: Times to feed (one per line)
      selector:
        object:
      default:
        - "07:00"
        - "18:00"
    minimum_hours_between_meals:
      name: Minimum Hours Between Meals
      selector:
        number:
          min: 1
          max: 24
          unit_of_measurement: hours
      default: 8

trigger:
  - platform: time
    at: !input feeding_times

condition:
  - condition: template
    value_template: >
      {{ (now() - states[last_meal_sensor].last_changed).total_seconds()
         > (minimum_hours_between_meals * 3600) }}

action:
  - service: !input notification_service
    data:
      title: "🍽️ Feeding Time"
      message: "Time to feed {{ dog_name }}!"
      data:
        actions:
          - action: "FED_{{ dog_name | upper }}"
            title: "Fed"
          - action: "SKIP_{{ dog_name | upper }}"
            title: "Skip"

variables:
  dog_name: !input dog_name
  last_meal_sensor: !input last_meal_sensor
  minimum_hours_between_meals: !input minimum_hours_between_meals
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/feeding_reminder.yaml)

---

## Multi-Dog Blueprints

### 8. All Dogs Home Check

Verify all dogs are home.

```yaml
blueprint:
  name: PawControl - All Dogs Home Check
  description: Verify all dogs are in safe zone at night
  domain: automation
  input:
    safe_zone_sensors:
      name: Safe Zone Sensors
      description: List of all dog safe zone sensors
      selector:
        entity:
          domain: binary_sensor
          multiple: true
    notification_service:
      name: Notification Service
      selector:
        target:
          entity:
            domain: notify
    check_time:
      name: Check Time
      selector:
        time:
      default: "22:00:00"

trigger:
  - platform: time
    at: !input check_time

action:
  - choose:
      - conditions:
          - condition: template
            value_template: >
              {{ expand(safe_zone_sensors) | selectattr('state', 'eq', 'on') | list | count
                 == expand(safe_zone_sensors) | list | count }}
        sequence:
          - service: !input notification_service
            data:
              title: "✅ All Dogs Home"
              message: "All dogs are in the safe zone"
    default:
      - service: !input notification_service
        data:
          title: "⚠️ Dogs Missing"
          message: >
            {% set missing = expand(safe_zone_sensors) 
                           | selectattr('state', 'eq', 'off') 
                           | map(attribute='name') 
                           | list %}
            {{ missing | join(', ') }} not in safe zone
          data:
            priority: high

variables:
  safe_zone_sensors: !input safe_zone_sensors
```

**Import:**  
[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/yourusername/pawcontrol/blob/main/blueprints/all_dogs_home.yaml)

---

## Using Blueprints

### Creating Automation from Blueprint

1. Go to **Settings** → **Automations & Scenes**
2. Click **"Create Automation"** → **"Start with a blueprint"**
3. Select PawControl blueprint
4. Fill in required inputs:
   - Select your dog's entities
   - Configure notification service
   - Set preferences
5. Click **"Save"**

### Customizing Blueprints

After creating automation from blueprint:
1. Click **"..."** → **"Edit in YAML"**
2. Modify as needed
3. Save changes

**Note:** Editing breaks connection to blueprint updates.

---

## Blueprint Best Practices

1. **Name Clearly**: Use descriptive automation names
2. **Test First**: Test with one dog before multi-dog
3. **Adjust Thresholds**: Customize for your dog's patterns
4. **Monitor Notifications**: Ensure not too many/few
5. **Document Changes**: Note customizations

---

## Contributing Blueprints

Have a great blueprint? Share it!

1. Fork the [GitHub repository](https://github.com/yourusername/pawcontrol)
2. Add blueprint to `blueprints/` directory
3. Submit pull request
4. Include description and usage example

---

## Community Blueprints

Browse community-contributed blueprints:
- [Community Forum](https://community.home-assistant.io/tag/pawcontrol)
- [GitHub Discussions](https://github.com/yourusername/pawcontrol/discussions)

---

**Next Steps:**
- [Automation Examples](automation_examples.md)
- [Advanced Configuration](advanced_config.md)
- [API Reference](api_reference.md)
